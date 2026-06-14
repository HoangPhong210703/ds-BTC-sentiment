import json
import logging
import os
from typing import Any

from bs4 import BeautifulSoup

from mongo.mongo_client import MongoService

logger = logging.getLogger("producer")

mongo_client = MongoService()


class ContentProcessor:
    """
    Class for content processing: check for sponsored content, remove noise texts,...
    """

    def remove_noise(self, text: str) -> str:
        """Remove all noise texts -> texts that are irrelevant the main content, including disclaimer, advertisement,..."""
        while "--" in text:
            text = text[text.index("--") + 2 :]
        if ". Visit" in text:
            text = text[: text.index(". Visit")]
        if ". visit" in text:
            text = text[: text.index(". visit")]
        while "-0-" in text:
            text = text[: text.index("-0-")]
        while "References\n" in text:
            text = text[: text.index("References\n")]
        while "Featured image from" in text:
            text = text[: text.index("Featured image from")]
        while "Subscribe to" in text:
            text = text[: text.index("Subscribe to")]
        while "To learn more" in text:
            text = text[: text.index("To learn more")]
        while "Learn more about" in text:
            text = text[: text.index("Learn more about")]
        while "More information can be found" in text:
            text = text[: text.index("More information can be found")]
        while "For more information" in text:
            text = text[: text.index("For more information")]
        while "View source version" in text:
            text = text[: text.index("View source version")]
        while "Check price action" in text:
            text = text[: text.index("Check price action")]
        while "Don't Miss a Beat" in text:
            text = text[: text.index("Don't Miss a Beat")]
        while "Read more:" in text:
            text = text[: text.index("Read more:")]
        while "Read Also" in text:
            text = text[: text.index("Read Also")]
        while "Also Read:" in text:
            text = text[: text.index("Also Read:")]
        while "Follow Us on" in text:
            text = text[: text.index("Follow Us on")]
        while "Disclosure" in text[1000:]:
            text = text[: text.index("Disclosure")]
        while "Related" in text:
            text = text[: text.index("Related")]
        while "Read More" in text:
            text = text[: text.index("Read More")]
        while "Join Our" in text:
            text = text[: text.index("Join Our")]
        while "PlayDoge" in text:
            text = text[: text.index("PlayDoge")]
        while "Frequently Asked Questions" in text:
            text = text[: text.index("Frequently Asked Questions")]
        while "Recommended Articles" in text:
            text = text[: text.index("Recommended Articles")]
        while "More" in text:
            text = text[: text.index("More")]
        while "Trusted" in text:
            text = text[: text.index("Trusted")]
        while "Advertisement\n" in text:
            text = text[: text.index("Advertisement\n")]
        while "Maximize your Cointribune" in text:
            text = text[: text.index("Maximize your Cointribune")]
        while "Follow us on Google News" in text:
            text = text[: text.index("Follow us on Google News")]
        return text

    def is_sponsored_content(self, content: str):
        """
        Filtering out sponsored posts from the content.

        Args:
            txt: content as string
        Returns:
            boolean: True if the content is a sponsored post.
        """
        if "This content is sponsored" in content:
            return True
        elif "The above article is sponsored content" in content:
            return True
        elif "This is a paid release" in content:
            return True
        elif "This article is sponsored content" in content:
            return True
        elif "This is a paid post" in content:
            return True
        elif "This is a sponsored press release" in content:
            return True
        elif "This is a sponsored article" in content:
            return True
        elif "Press release sponsored by our commercial partners." in content:
            return True
        elif "This content is provided by a third party" in content:
            return True
        elif "This article is a SPONSORED" in content:
            return True
        elif "For more information" in content:
            return True
        elif "This is a sponsored post" in content:
            return True
        elif "This content is a sponsored article" in content:
            return True
        elif "The below article is Sponsored Content" in content:
            return True
        else:
            return False

    def is_sponsored_tags(self, tag_list: str):
        """
        Check if the content contains any tags indicating that this is a sponsored post
        Args:
            tag_list (str): The tags

        Returns:
            bool: True if the content contains any tags indicating that this is a sponsored post, False otherwise
        """
        if "sponsor" in tag_list.lower():
            return True
        elif "advertisement" in tag_list.lower():
            return True
        elif "partnered" in tag_list.lower():
            return True
        else:
            return False


async def get_existing_urls() -> list[str]:
    """
    Get a list of existing urls in DB to prevent duplicated urls when scraping

    Output:
    list of urls
    """

    url_list: list[str] = []
    url_list = await mongo_client.get_existing_news_urls()
    return url_list


async def urls_from_webpage() -> list[str]:
    """
    Get all urls from rss feeds that are not existed in the database.

    Output:
        urls: a list of urls from rss feeds
    """
    from bs4 import BeautifulSoup

    from scraper.scraper_service import AsyncWebScraper

    scraper = AsyncWebScraper()
    urls: list[str] = []

    existing_urls = await get_existing_urls()  # storing all existing urls into a list
    print(f"found {len(existing_urls)} existing urls in DB")
    # Reduced to 5 reliable feeds for now to keep per-run load (and worker memory)
    # low. The full 30-feed list is kept below, commented, for easy restore.
    feeds = [
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://cryptoslate.com/feed/",
        "https://crypto.news/feed/",
        "https://beincrypto.com/feed/",
        # --- full list (re-enable when memory/throughput allows) ---
        # "https://99bitcoins.com/rss",
        # "https://feeds.bloomberg.com/crypto/news.rss",
        # "https://cryptodnes.bg/en/feed",
        # "https://ambcrypto.com/feed/",
        # "https://coingape.com/feed/",
        # "https://www.cryptotimes.io/feed/",
        # "https://blockworks.co/feed",
        # "https://zycrypto.com/feed/",
        # "https://dailyhodl.com/feed/",
        # "https://bitcoinist.com/feed/",
        # "https://finbold.com/feed/",
        # "https://u.today/rss",
        # "https://www.newsbtc.com/feed/",
        # "https://insidebitcoins.com/feed",
        # "https://cryptomufasa.com/feed/",
        # "https://cryptobriefing.com/feed/",
        # "https://www.thecoinrepublic.com/feed/",
        # "https://en.bitcoinsistemi.com/feed/",
        # "https://crypto-economy.com/feed/",
        # "https://www.cointribune.com/en/feed/",
        # "https://cryptonews.com/rss/",
        # "https://dailycoin.com/feed/",
        # "https://en.cryptonomist.ch/feed/",
        # "https://coinpaprika.com/news/feed/",
        # "https://www.cryptopolitan.com/rss",
    ]

    # Cap new articles taken per feed per run (keeps memory/runtime bounded).
    max_per_feed = int(os.getenv("MAX_ARTICLES_PER_FEED", "10"))

    for url in feeds:
        try:
            res = await scraper.fetch(url)
            logger.info(f"Fetched {url} with status code {scraper.status_code}")
            soup = BeautifulSoup(res, "xml")
            taken = 0
            for item in soup.find_all("item"):
                if taken >= max_per_feed:
                    break
                links = item.findAll("link")
                for link in links:
                    if (
                        link.text not in existing_urls and "/videos/" not in link.text
                    ):  # Handling cases when it is a url to a video or a podcast for some websites
                        urls.append(link.text)
                        taken += 1
        except RuntimeError:
            continue
    logger.info("Number of new urls in this session: " + str(len(urls)))
    return urls


def deep_find(d: Any, target_key: str) -> Any:
    """
    Helper function to recursively search for a specific key in a nested dictionary.
    Args:
        d (dict): The dictionary to search in.
        target_key (str): The key to search for.
    """
    if isinstance(d, dict):
        if target_key in d:
            return d[target_key]
        for _, value in d.items():
            result = deep_find(value, target_key)
            if result is not None:
                return result
    elif isinstance(d, list):
        for item in d:
            result = deep_find(item, target_key)
            if result is not None:
                return result
    return None


def extract_meta_content(
    soup: BeautifulSoup,
    property_name: str,
    attr: str = "property",
    default: str = "",
) -> Any:
    """Async helper function to extract value from meta tag and a specific attribute"""
    # TODO: fix pyright message
    try:
        return soup.find("meta", attrs={attr: property_name})["content"]
    except Exception:
        return default


def extract_json_ld_data(soup: BeautifulSoup) -> list[dict[Any, Any] | None]:
    """Extract JSON-LD data from the page. Several websites use this format to add structured data to their pages. See: https://json-ld.org/"""

    try:
        return [
            json.loads(x.string, strict=False)
            for x in soup.find_all("script", type="application/ld+json")
        ]
    except Exception:
        return []


async def async_extract_data_from_url(url: str, run_ner: bool = True) -> dict[str, Any]:
    from datetime import datetime
    from urllib.parse import urlparse

    import trafilatura
    from bs4 import BeautifulSoup

    from scraper.scraper_service import AsyncWebScraper

    scraper = AsyncWebScraper()

    doc = await scraper.fetch(url)

    # Ensure response processing is non-blocking
    response_text = doc.split("CONTENT END", 1)[0]

    parsed = urlparse(url)
    domain_name = parsed.hostname

    soup = BeautifulSoup(response_text, "html.parser")
    for div in soup.find_all("div", attrs={"class": "news-tab-content"}):
        div.decompose()
    extract: Any = trafilatura.bare_extraction(soup.prettify())
    json_ld_data: list[dict[Any, Any] | None] = extract_json_ld_data(soup)

    # Metadata extraction
    try:
        upload_date = (
            extract_meta_content(soup, "article:published_time")
            or extract_meta_content(soup, "published", "name")
            or (
                json_ld_data[0].get("@graph", [{}])[0].get("datePublished", "")
                if json_ld_data
                else ""
            )
            or (json_ld_data[0].get("publishedAt", "") if json_ld_data else "")
            or (json_ld_data[0].get("datePublished", "") if json_ld_data else "")
        )

    except Exception:
        upload_date = ""
    try:
        description = extract_meta_content(soup, "og:description") or (
            json_ld_data[2].get("description", "") if len(json_ld_data) > 2 else ""
        )
    except Exception:
        description = ""
    try:
        image_url = extract_meta_content(soup, "og:image")
        if image_url == "":
            image_url = extract_meta_content(soup, "twitter:image")
    except Exception:
        image_url = ""
    try:
        last_modified = extract_meta_content(soup, "article:modified_time")
    except Exception:
        last_modified = ""
    try:
        author = extract_meta_content(soup, "author") or extract_meta_content(
            soup, "author", "name"
        )
    except Exception:
        author = ""
    try:
        tags = deep_find(json_ld_data[0], "articleSection")
        article_keywords = deep_find(json_ld_data[0], "keywords")
    except Exception:
        tags = []
        article_keywords = []

    title = ""
    content = ""
    if isinstance(extract, dict):
        title = extract.get("title", "")
        content = extract.get("text", "")
    else:
        title = getattr(extract, "title", "")
        content = getattr(extract, "text", "")

    crawl_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

    # tokens_mentioned = await async_gliner_extractor.retrieve_tokens_found(content)
    entities = []
    if run_ner and content and isinstance(content, str):
        from ner_model.gliner_model_service import GlinerModelService

        gliner_client = GlinerModelService()
        entities = await gliner_client.predict_text(content)

    if upload_date:
        upload_date = datetime.fromisoformat(upload_date.replace("Z", "+00:00"))

    return {
        "url": url,
        "domain_name": domain_name,
        "title": title,
        "content": content,
        "published_time": upload_date,
        "description": description,
        "tags": tags,
        "article_keywords": article_keywords,
        "last_modified": last_modified,
        "author": author,
        "crawl_date": crawl_date,
        "image_url": image_url,
        "ner": str(entities) if run_ner else "",
        "ner_counted": False,
    }
