"""Run GLiNER NER on stored articles that have a published_time but no NER yet.

Targets documents where ner is "" / null AND published_time is a real date
(i.e. the historical sitemap backfill). Processes them one at a time (the model
loads once), writing each result immediately so the job is fully resumable: if it
is interrupted, just run it again and it continues with the remaining articles.

Run inside the worker container:

    docker compose exec airflow-worker python -m producer.ner_backfill
"""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mongo.mongo_client import MongoService
from ner_model.gliner_model_service import GlinerModelService

BATCH = int(os.getenv("NER_BACKFILL_BATCH", "50"))
MAX_CONTENT_CHARS = int(os.getenv("NER_MAX_CONTENT_CHARS", "15000"))

QUERY = {"ner": {"$in": ["", None]}, "published_time": {"$type": "date"}}


async def run():
    mongo = MongoService()
    coll = mongo.news_metadata_collection
    try:
        total = await coll.count_documents(QUERY)
        print(f"{total} articles to NER-process (ner empty + real published_time).")
        if total == 0:
            return

        svc = GlinerModelService()  # loads the model once
        done = 0
        empty = 0

        while True:
            docs = await coll.find(QUERY, {"content": 1}).limit(BATCH).to_list(length=BATCH)
            if not docs:
                break

            for d in docs:
                content = d.get("content")
                if not isinstance(content, str) or not content.strip():
                    entities = []
                    empty += 1
                else:
                    entities = await svc.predict_text(content[:MAX_CONTENT_CHARS])
                # str(entities) is never "" -> doc leaves the QUERY set (resumable)
                await coll.update_one({"_id": d["_id"]}, {"$set": {"ner": str(entities)}})
                done += 1
                if done % 25 == 0:
                    print(f"  {done}/{total} processed")

        print(f"\nDone. Processed {done} articles ({empty} had no usable content).")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(run())
