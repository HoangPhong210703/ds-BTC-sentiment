# BTC News-Sentiment → Price Direction — Research Overview

**Goal:** test whether crypto **news attention + sentiment** helps predict short-term **BTC price
direction**. Short answer from this work: **no robust, out-of-sample edge** — see Findings.

---

## Pipeline at a glance

```
PRICE  ── Binance ─────────────► BTC_raw (Mongo)
NEWS   ── scrape / dataset ────► news_metadata (Mongo) / news.csv
                                      │
                          features (price TA + news counts + FinBERT sentiment)
                                      │
                                btc_features.csv
                                      │
                    direction classification (6h / 12h) + walk-forward
                                      │
                       out-of-sample backtest on Jan–Jun 2026
```

## Files

### Data ingestion (`news_scrape/`)
| File | What it does |
|---|---|
| `news_scrape/producer/binance_price.py` | Fetch hourly BTC OHLCV from Binance → `BTC_raw` (Mongo). Used because CryptoCompare was rate-limited. |
| `news_scrape/producer/news_scraper.py`, `rss_producer.py` | Live RSS scraping → `news_metadata` (Mongo). `async_extract_data_from_url(url, run_ner=False)` extracts content without NER. |
| `news_scrape/ner_model/gliner_model_service.py` | **Local in-process GLiNER** NER (replaced a dead remote service). Loaded once, CPU. |
| `news_scrape/producer/news_sitemap_backfill.py` | Historical news backfill via site **sitemaps**, date-windowed, ingest-only. |
| `news_scrape/producer/ner_backfill.py` | Runs GLiNER over stored articles missing NER (resumable). |
| `news_scrape/producer/news_backfill_producer.py` | *(superseded)* CryptoCompare News API backfill — abandoned (rate limits). |

External dataset actually used for modeling: **`bitcoin-news-data/datasets/news.csv`**
(~34k articles, **2025-07-17 → 2025-11-23**, pre-tagged coins + headlines).

### Modeling (`research/`)
| File | What it does |
|---|---|
| `research/1_build_dataset.ipynb` | Builds **`btc_features.csv`**: price/technical indicators + news volume features + **FinBERT** headline sentiment (cached to `headline_sentiment.csv`). |
| `research/2_modeling.ipynb` | **Direction classification** (up/down at **6h & 12h**) with LogReg/RF/XGB (+optional LSTM) across `price` / `price+news` / `price+news+sent`; single-split, **walk-forward validation**, and output visualization. |
| `research/make_backtest_features.py` | Builds **`btc_backtest_features.csv`** — price-only features for **Jan–Jun 2026** (out-of-sample). |
| `research/3_backtest.ipynb` | Trains price-only model on 2025, tests out-of-sample on **2026**; accuracy/AUC, prediction plot, illustrative equity curve. |
| `research/requirements.txt` | Python deps (use **Python 3.12**, e.g. the `.venv`). |

### Generated artifacts (in `research/`)
`btc_features.csv`, `btc_backtest_features.csv`, `headline_sentiment.csv` (FinBERT cache).

## Features (target = next-hour/`h`-hour direction)
- **Price/technical (10):** close, volume, ret_1h, ret_3h, vol_change, rsi_14, macd, macd_signal, sma20_ratio, bb_pct
- **News volume (5):** btc_mentions, n_articles, total_coin_mentions, btc_share, btc_mentions_3h  *(answers "when", not "which way")*
- **FinBERT sentiment (3):** sent_mean, sent_net, btc_sent_mean  *(the directional probe)*

## How to run
1. `pip install -r research/requirements.txt` (Python 3.12; the project `.venv` already has it).
2. In VS Code, set the notebook **kernel to `.venv`** (3.12). A hang on `import numpy` means the wrong kernel is selected, not a code problem.
3. Run `1_build_dataset.ipynb` → `2_modeling.ipynb`. For the backtest: `python research/make_backtest_features.py` then `3_backtest.ipynb`.

## Findings (honest)
- **Hourly returns are ~noise** — regressing return magnitude doesn't work; predicting **absolute price** with trees flat-lines (can't extrapolate beyond training range). So we predict **direction** at longer horizons.
- **Volume features = timing, not direction.** **FinBERT sentiment added marginal-to-no lift.**
- Single 80/20 split scored **below 0.5** because train (bull) and test (Nov crash) are different regimes — a non-stationarity artifact, not anti-signal. **Walk-forward** is the trustworthy view (~0.5).
- **Conclusion:** no robust, period-independent directional edge — consistent with the broader literature that public-news-sentiment direction prediction is, at best, a faint/cost-fragile signal. The value here is a rigorous, honest pipeline, not a profitable model.
