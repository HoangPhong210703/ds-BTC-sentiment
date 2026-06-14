"""Fetch BTC hourly OHLCV from Binance's public data API into the BTC_raw collection.

CryptoCompare is rate-limited; Binance's public klines endpoint needs no API key
and has generous limits. This writes the SAME document schema as the
CryptoCompare-based producer (coin_price_producer), so all downstream code that
reads <COIN>_raw is unchanged. Idempotent: resumes from the latest stored hour.

Run inside the worker container:

    docker compose exec airflow-worker python -m producer.binance_price
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mongo.mongo_client import MongoService

# data-api.binance.vision is Binance's public market-data host (no key, no geo-block)
BASE_URL = os.getenv("BINANCE_DATA_URL", "https://data-api.binance.vision")
SYMBOL = "BTCUSDT"
COIN = "BTC"
INTERVAL = "1h"
INTERVAL_MS = 3600 * 1000
LIMIT = 1000
START_DATE = datetime(2025, 5, 14, tzinfo=timezone.utc)


async def fetch_klines(client, start_ms, end_ms):
    r = await client.get(
        f"{BASE_URL}/api/v3/klines",
        params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": LIMIT,
        },
    )
    r.raise_for_status()
    return r.json()


def kline_to_doc(k):
    # Binance kline: [openTime, open, high, low, close, volume, closeTime,
    #                 quoteAssetVolume, trades, takerBuyBase, takerBuyQuote, ignore]
    t = int(k[0]) // 1000
    return {
        "time": t,
        "datetime": datetime.utcfromtimestamp(t),
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volumefrom": float(k[5]),   # base volume (BTC)
        "volumeto": float(k[7]),     # quote volume (USDT ~ USD)
        "conversionType": "direct",
        "conversionSymbol": "",
        "coin": COIN,
    }


async def main():
    mongo = MongoService()
    coll_name = f"{COIN}_raw"
    try:
        last = await mongo.get_latest_timestamp(coll_name)
        start = (last + timedelta(hours=1)) if last else START_DATE
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = datetime.now(timezone.utc)

        print(f"Fetching {SYMBOL} {INTERVAL} from {start} to {end}")
        cur_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        total = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while cur_ms < end_ms:
                klines = await fetch_klines(client, cur_ms, end_ms)
                if not klines:
                    break
                df = pd.DataFrame([kline_to_doc(k) for k in klines])
                await mongo.save_dataframe_to_collection(df, coll_name)
                total += len(df)
                print(f"  +{len(df)} through {df['datetime'].iloc[-1]} (total {total})")
                cur_ms = int(klines[-1][0]) + INTERVAL_MS
                if len(klines) < LIMIT:
                    break
                await asyncio.sleep(0.2)

        print(f"Done. Inserted {total} rows into {coll_name}.")
    finally:
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
