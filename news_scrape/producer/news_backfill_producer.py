"""One-time historical news backfill via the CryptoCompare News API.

Fetches crypto news articles for a fixed date window and stores them in the
`news_metadata` collection using the same schema as the live scraper, but
WITHOUT running NER (ner="" / ner_counted=False). NER is handled by a separate
pass later.

Run inside the worker container (it has httpx, Mongo access, and the API key):

    docker compose exec airflow-worker python -m producer.news_backfill_producer

Config is the three constants below. This is intentionally a one-off script.
"""

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mongo.mongo_client import MongoService

API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")
NEWS_URL = "https://min-api.cryptocompare.com/data/v2/news/"

# --- backfill window (UTC) ---------------------------------------------------
START_DATE = datetime(2026, 6, 8, tzinfo=timezone.utc)   # inclusive
END_DATE = datetime(2026, 6, 13, tzinfo=timezone.utc)    # exclusive -> covers through Jun 12
MAX_PER_DAY = 100
PAGE_PAUSE_SECONDS = 0.25

START_TS = int(START_DATE.timestamp())
END_TS = int(END_DATE.timestamp())


def to_metadata(item: dict) -> dict:
    """Map a CryptoCompare news item into the news_metadata schema."""
    published_on = int(item["published_on"])
    source_info = item.get("source_info") or {}
    return {
        "url": item.get("url", ""),
        "domain_name": source_info.get("name") or item.get("source", ""),
        "title": item.get("title", ""),
        "content": item.get("body", ""),
        "published_time": datetime.fromtimestamp(published_on, tz=timezone.utc),
        "description": "",
        "tags": item.get("tags", ""),
        "article_keywords": item.get("categories", ""),
        "last_modified": "",
        "author": "",
        "crawl_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "image_url": item.get("imageurl", ""),
        "ner": "",            # NER not run here; separate pass fills this
        "ner_counted": False,
    }


async def fetch_page(client: httpx.AsyncClient, l_ts: int) -> list[dict]:
    """Return up to ~50 news items published before l_ts (newest first)."""
    params = {"lang": "EN", "lTs": l_ts, "api_key": API_KEY}
    resp = await client.get(NEWS_URL, params=params)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("Type") == 100:
        return payload.get("Data", []) or []
    # Type != 100 means an API-level error (rate limit, bad key, etc.)
    raise RuntimeError(f"CryptoCompare API error: {payload.get('Message')}")


async def backfill() -> None:
    if not API_KEY:
        print("ERROR: CRYPTOCOMPARE_API_KEY is not set.")
        return

    mongo = MongoService()
    try:
        existing = set(await mongo.get_existing_news_urls())
        print(f"Found {len(existing)} existing URLs in DB (for dedup).")
        print(
            f"Backfilling {START_DATE.date()} .. {(END_DATE).date()} (exclusive), "
            f"max {MAX_PER_DAY}/day."
        )

        per_day = defaultdict(int)
        stored = 0
        skipped_dup = 0
        skipped_cap = 0
        pages = 0
        l_ts = END_TS
        prev_l_ts = None

        async with httpx.AsyncClient(timeout=20.0) as client:
            while True:
                try:
                    items = await fetch_page(client, l_ts)
                except (httpx.HTTPError, RuntimeError) as e:
                    print(f"Stopping: request failed: {e}")
                    break

                if not items:
                    print("Stopping: no more items returned.")
                    break

                pages += 1
                page_min_ts = min(int(it["published_on"]) for it in items)

                for it in items:
                    pub = int(it["published_on"])
                    if pub >= END_TS or pub < START_TS:
                        continue  # outside the window

                    url = it.get("url", "")
                    if not url or url in existing:
                        skipped_dup += 1
                        continue

                    day = datetime.fromtimestamp(pub, tz=timezone.utc).strftime("%Y-%m-%d")
                    if per_day[day] >= MAX_PER_DAY:
                        skipped_cap += 1
                        continue

                    await mongo.insert_news_metadata(to_metadata(it))
                    existing.add(url)
                    per_day[day] += 1
                    stored += 1

                # Reached articles older than the window -> done.
                if page_min_ts < START_TS:
                    print("Reached start of window.")
                    break

                next_l_ts = page_min_ts - 1
                if prev_l_ts is not None and next_l_ts >= l_ts:
                    print("Stopping: pagination not advancing.")
                    break
                prev_l_ts = l_ts
                l_ts = next_l_ts
                await asyncio.sleep(PAGE_PAUSE_SECONDS)

        print("\n=== Backfill summary ===")
        print(f"Pages fetched : {pages}")
        print(f"Stored        : {stored}")
        print(f"Skipped (dup) : {skipped_dup}")
        print(f"Skipped (cap) : {skipped_cap}")
        for day in sorted(per_day):
            print(f"  {day}: {per_day[day]}")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(backfill())
