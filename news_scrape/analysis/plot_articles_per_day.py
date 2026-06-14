"""Plot the number of news articles per day (by published_time) in MongoDB.

Saves a bar chart to results/plots/articles_per_day.png. The Jun 8-12 sitemap
backfill window is highlighted. Connection is env-configurable; defaults assume
running in a container that reaches the published Mongo port via the Docker host.
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pymongo import MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "host.docker.internal")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27027"))
MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASS = os.getenv("MONGO_PASS", "admin")
MONGO_DB = os.getenv("MONGO_DB", "news_data")
OUT_PATH = os.getenv("OUT_PATH", "/out/results/plots/articles_per_day.png")

WINDOW_START, WINDOW_END = "2026-06-08", "2026-06-12"


def main():
    client = MongoClient(
        host=MONGO_HOST,
        port=MONGO_PORT,
        username=MONGO_USER,
        password=MONGO_PASS,
        authSource="admin",
    )
    coll = client[MONGO_DB].news_metadata
    rows = list(
        coll.aggregate(
            [
                {"$match": {"published_time": {"$type": "date"}}},
                {
                    "$group": {
                        "_id": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$published_time",
                            }
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"_id": 1}},
            ]
        )
    )
    no_date = coll.count_documents({"published_time": {"$in": ["", None]}})

    days = [r["_id"] for r in rows]
    counts = [r["count"] for r in rows]

    fig, ax = plt.subplots(figsize=(15, 6))
    x = range(len(days))
    bars = ax.bar(x, counts, color="#4C9BE8")
    for d, b in zip(days, bars):
        if WINDOW_START <= d <= WINDOW_END:
            b.set_color("#E8744C")

    ax.set_title(
        "News articles per day by published_time  "
        "(orange = Jun 8-12 sitemap backfill)"
    )
    ax.set_xlabel("Published date")
    ax.set_ylabel("Article count")
    ax.set_xticks(list(x))
    ax.set_xticklabels(days, rotation=90, fontsize=8)
    for b, c in zip(bars, counts):
        ax.text(
            b.get_x() + b.get_width() / 2,
            c,
            str(c),
            ha="center",
            va="bottom",
            fontsize=7,
        )
    ax.margins(x=0.01)
    plt.figtext(
        0.99,
        0.01,
        f"{no_date} articles have no published_time (excluded)",
        ha="right",
        fontsize=8,
        color="gray",
    )
    plt.tight_layout()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    plt.savefig(OUT_PATH, dpi=120)
    print(
        f"saved {OUT_PATH} | days={len(days)} total={sum(counts)} no_date={no_date}"
    )


if __name__ == "__main__":
    main()
