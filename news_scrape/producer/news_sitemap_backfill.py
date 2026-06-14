"""One-time historical news backfill by crawling site XML sitemaps (date-targeted).

For each site it walks the sitemap index, descends only into sub-sitemaps that
were updated within/after the window (and aren't taxonomy/author/coin pages),
collects article URLs whose <lastmod> falls in the date window, then fetches +
extracts each via the existing scraper WITHOUT NER (ingest-only) and stores them
in news_metadata (ner="" / ner_counted=False). NER is a separate pass later.

Run inside the worker container:

    docker compose exec airflow-worker python -m producer.news_sitemap_backfill

Config is the constants below. Intentionally a one-off script.
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mongo.mongo_client import MongoService
from producer.news_scraper import async_extract_data_from_url

# --- config ---------------------------------------------------------------
SITEMAPS = {
    "decrypt": "https://decrypt.co/sitemap_index.xml",
    "crypto.news": "https://crypto.news/sitemap_index.xml",
    "cryptoslate": "https://cryptoslate.com/sitemap_index.xml",
    "beincrypto": "https://beincrypto.com/sitemap_index.xml",
}
START_DATE = datetime(2026, 6, 1, tzinfo=timezone.utc)    # inclusive
END_DATE = datetime(2026, 6, 13, tzinfo=timezone.utc)     # exclusive -> through Jun 12
MAX_PER_DAY = 200                                          # total across all sites, per calendar day
FETCH_CONCURRENCY = int(os.getenv("SITEMAP_FETCH_CONCURRENCY", "4"))
MAX_SITEMAP_DEPTH = 3
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# sub-sitemaps whose loc contains any of these are skipped (not article posts)
DENY_KEYWORDS = (
    "category", "author", "post_tag", "tag-sitemap", "glossary", "convert",
    "exchange", "currency", "coverage", "bonus", "page-sitemap", "event",
    "term", "web-story", "podcast",
)


def parse_dt(text):
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def in_window(dt):
    return dt is not None and START_DATE <= dt < END_DATE


def is_article_sitemap(loc: str) -> bool:
    loc = loc.lower()
    return not any(k in loc for k in DENY_KEYWORDS)


async def fetch_xml(client, url):
    try:
        r = await client.get(url)
        r.raise_for_status()
        return r.text
    except httpx.HTTPError as e:
        print(f"  ! sitemap fetch failed {url}: {e}")
        return None


async def collect_urls(client, sitemap_url, depth=0):
    """Recursively walk a sitemap, returning [(url, lastmod_dt), ...] in window."""
    if depth > MAX_SITEMAP_DEPTH:
        return []
    xml = await fetch_xml(client, sitemap_url)
    if not xml:
        return []
    soup = BeautifulSoup(xml, "xml")

    sub = soup.find_all("sitemap")
    if sub:  # this is a sitemap index -> recurse into relevant children
        results = []
        for sm in sub:
            loc = sm.find("loc")
            if not loc:
                continue
            loc_text = loc.text.strip()
            if not is_article_sitemap(loc_text):
                continue
            lm_tag = sm.find("lastmod")
            lastmod = parse_dt(lm_tag.text if lm_tag else None)
            if lastmod is not None and lastmod < START_DATE:
                continue  # sub-sitemap not touched since before the window
            results.extend(await collect_urls(client, loc_text, depth + 1))
        return results

    # urlset -> collect article URLs whose own lastmod is in the window
    results = []
    for u in soup.find_all("url"):
        loc = u.find("loc")
        if not loc:
            continue
        lm_tag = u.find("lastmod")
        lastmod = parse_dt(lm_tag.text if lm_tag else None)
        if in_window(lastmod):
            results.append((loc.text.strip(), lastmod))
    return results


async def store_article(mongo, sem, url, lastmod, per_day_stored, counters):
    async with sem:
        try:
            data = await async_extract_data_from_url(url, run_ner=False)
        except Exception as e:
            counters["fetch_fail"] += 1
            print(f"  ! fetch failed {url}: {e}")
            return

        pub = data.get("published_time")
        if not isinstance(pub, datetime):
            pub = lastmod  # fall back to sitemap date if page had none
        if pub is not None and pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        if not in_window(pub):
            counters["out_of_window"] += 1
            return

        data["published_time"] = pub
        data["ner"] = ""
        data["ner_counted"] = False
        await mongo.insert_news_metadata(data)
        per_day_stored[pub.strftime("%Y-%m-%d")] += 1
        counters["stored"] += 1


async def backfill():
    mongo = MongoService()
    try:
        existing = set(await mongo.get_existing_news_urls())
        print(f"{len(existing)} existing URLs in DB (for dedup).")
        print(
            f"Window {START_DATE.date()} .. {END_DATE.date()} (exclusive), "
            f"max {MAX_PER_DAY}/day total."
        )

        # 1) discover candidates from every site's sitemap
        candidates = []  # (url, lastmod)
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": UA}
        ) as client:
            for site, sm in SITEMAPS.items():
                found = await collect_urls(client, sm)
                print(f"  {site}: {len(found)} in-window URLs")
                candidates.extend(found)

        # 2) dedup + per-day cap (by sitemap lastmod), newest first
        per_day_sel = defaultdict(int)
        seen = set()
        selected = []
        for url, lastmod in sorted(candidates, key=lambda x: x[1], reverse=True):
            if url in existing or url in seen:
                continue
            day = lastmod.strftime("%Y-%m-%d")
            if per_day_sel[day] >= MAX_PER_DAY:
                continue
            seen.add(url)
            per_day_sel[day] += 1
            selected.append((url, lastmod))
        print(f"Selected {len(selected)} candidates to fetch "
              f"(concurrency {FETCH_CONCURRENCY}).")

        # 3) fetch + extract (no NER) + store
        sem = asyncio.Semaphore(FETCH_CONCURRENCY)
        counters = defaultdict(int)
        per_day_stored = defaultdict(int)
        await asyncio.gather(
            *[
                store_article(mongo, sem, url, lastmod, per_day_stored, counters)
                for url, lastmod in selected
            ]
        )

        print("\n=== Backfill summary ===")
        print(f"Candidates selected : {len(selected)}")
        print(f"Stored              : {counters['stored']}")
        print(f"Fetch failed        : {counters['fetch_fail']}")
        print(f"Out of window       : {counters['out_of_window']}")
        for day in sorted(per_day_stored):
            print(f"  {day}: {per_day_stored[day]}")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(backfill())
