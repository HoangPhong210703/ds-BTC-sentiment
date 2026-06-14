import asyncio
import logging
import os
import sys

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mongo.mongo_client import MongoService

logger = logging.getLogger(__name__)

# Max articles processed through GLiNER concurrently. Each concurrent slot holds
# a model forward pass in memory, so this is the main lever against OOM. Keep low
# on memory-constrained hosts; raise for speed when RAM allows.
SCRAPE_CONCURRENCY = int(os.getenv("NER_SCRAPE_CONCURRENCY", "2"))

# Hàm xử lý một URL


async def process_url(mongo_client: MongoService, url: str):
    from producer.news_scraper import async_extract_data_from_url

    try:
        res = await async_extract_data_from_url(url)

        # Ghi vào MongoDB
        await mongo_client.insert_news_metadata(res)
        print(f"Inserted to Mongo: {url}")
        logger.info(f"Inserted to Mongo: {url}")
    except Exception as e:
        logger.error(f"Error with url {url}: {e}", exc_info=True)
    except asyncio.CancelledError:
        logger.info(f"Cancelled error with url {url}")


# Hàm chính
async def stream_data():
    from producer.news_scraper import urls_from_webpage

    mongo_client = MongoService()
    try:
        urls = await urls_from_webpage()
        print(f"Found {len(urls)} URLs to process.")
        # _ = await mongo_client.insert_news_url(urls)
        semaphore = asyncio.Semaphore(SCRAPE_CONCURRENCY)

        async def limited_process_url(url):
            async with semaphore:
                await process_url(mongo_client, url)

        tasks = [limited_process_url(url) for url in urls]
        _ = await asyncio.gather(*tasks)

    except Exception as e:
        logger.error(f"Pipeline error: {e}")

    finally:
        await mongo_client.close()
        logger.info("MongoDB connection closed.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(stream_data())
