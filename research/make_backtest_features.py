"""Build BTC price/technical features for Jan-Jun 2026 (out-of-sample backtest set).

Reads BTC_raw from Mongo, computes the SAME technical features as
1_build_dataset.ipynb, slices to 2026-01-01 .. 2026-07-01 (whatever price exists),
and writes research/btc_backtest_features.csv.

NOTE: the news/sentiment dataset only covers 2025-07 .. 2025-11, so this backtest
set has **price features only**. Use it to backtest the price-feature model
out-of-sample (the news+sentiment columns don't exist for 2026).

Run (needs pymongo, pandas, ta):
    python research/make_backtest_features.py
"""

import os

import pandas as pd
from pymongo import MongoClient
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:admin@localhost:27027/?authSource=admin")
MONGO_DB = os.getenv("MONGO_DB", "news_data")
COIN = "BTC"
START = pd.Timestamp("2026-01-01", tz="UTC")
END = pd.Timestamp("2026-07-01", tz="UTC")  # exclusive
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "btc_backtest_features.csv")


def main():
    db = MongoClient(MONGO_URI)[MONGO_DB]
    price = pd.DataFrame(list(db[f"{COIN}_raw"].find({}, {"_id": 0})))
    if price.empty:
        raise SystemExit(f"{COIN}_raw is empty - fetch price first (producer/binance_price.py)")
    price["datetime"] = pd.to_datetime(price["datetime"], utc=True)
    price = price.sort_values("datetime").drop_duplicates("datetime").set_index("datetime")
    price = price[["open", "high", "low", "close", "volumefrom", "volumeto"]].astype(float)

    # Compute indicators on the FULL series so the Jan-Jun slice has valid warmup.
    feat = pd.DataFrame(index=price.index)
    feat["close"] = price["close"]
    feat["volume"] = price["volumeto"]
    feat["ret_1h"] = price["close"].pct_change()
    feat["ret_3h"] = price["close"].pct_change(3)
    feat["vol_change"] = price["volumeto"].pct_change()
    feat["rsi_14"] = RSIIndicator(price["close"], window=14).rsi()
    macd = MACD(price["close"])
    feat["macd"] = macd.macd()
    feat["macd_signal"] = macd.macd_signal()
    sma20 = SMAIndicator(price["close"], window=20).sma_indicator()
    feat["sma20_ratio"] = price["close"] / sma20 - 1
    bb = BollingerBands(price["close"], window=20)
    feat["bb_pct"] = (price["close"] - bb.bollinger_lband()) / (bb.bollinger_hband() - bb.bollinger_lband())

    out = feat[(feat.index >= START) & (feat.index < END)].dropna()
    out.to_csv(OUT)
    print(f"saved {OUT}")
    print(f"  rows: {len(out)} | range: {out.index.min()} -> {out.index.max()}")
    print(f"  columns: {list(out.columns)}")


if __name__ == "__main__":
    main()
