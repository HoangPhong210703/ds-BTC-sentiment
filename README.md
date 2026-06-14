# intro-ds-project

Crypto price forecasting from market data + news. The project scrapes crypto news,
runs NER over the articles, ingests OHLCV price data, builds technical/social features,
stores everything in MongoDB, and trains time-series models to forecast prices.

## Project layout

```
.
├── news_scrape/          # Dockerized ingestion & serving platform
│   ├── compose.yaml      #   Airflow + MongoDB + FastAPI stack
│   ├── airflow/dags/     #   scrape_and_process, fetch_coin_price, fetch_all_ner_count
│   ├── producer/         #   news / RSS / coin-price / NER producers
│   ├── ner_model/        #   GLiNER + spaCy entity extraction
│   ├── mongo/            #   MongoDB client
│   └── main/             #   FastAPI service (api_main.py) + feature/integration code
├── data/                 # Data integration, validation & feature pipelines
├── models/              # ARIMA, SARIMAX, GRU, LSTM, Random Forest, XGBoost
├── factory/trainer.py    # Thin training wrapper
├── configs/hydra/        # Hydra config-driven training (one YAML per model)
├── research/             # Notebooks: feature engineering & model training
├── results/              # Metrics, predictions, comparison plots
└── saved_models/         # Trained LSTM model + scalers
```

## Approach

### Feature Engineering + Data Integration
1. Lag features and rolling stats
2. Technical indicators: SMA, EMA, RSI, MACD, Bollinger Bands
3. Correlation-Based Feature Selection (CFS)

### Machine Learning
ARIMA, SARIMAX, GRU, LSTM, Random Forest, XGBoost (Prophet / Orbit / NeuralProphet via configs).

---

## Running the project

The project has two parts you run independently:

1. **`news_scrape/`** — the data platform (Airflow + MongoDB + FastAPI), run with Docker Compose.
2. **The ML / research code** at the repo root, run locally in Python.

### Prerequisites
- Docker & Docker Compose (for the data platform)
- Python 3.10+ (for the ML code)
- A [CryptoCompare](https://min-api.cryptocompare.com/) API key (for price ingestion)
- At least 4 GB RAM and 2 CPUs free for Docker (Airflow requirement)

> **Windows users — line endings:** the shell scripts (e.g. `news_scrape/init-airflow.sh`)
> must use **LF** line endings. If git checks them out with Windows **CRLF**, `airflow-init`
> fails with `exit 2` and logs `init-airflow.sh: line 2: $'\r': command not found`, because
> bash inside the Linux container can't parse the `\r`. This repo ships a `.gitattributes`
> (`*.sh text eol=lf`) to prevent it. If you already hit the error, convert the file to LF and
> re-run the stack:
> ```powershell
> # from the repo root
> python -c "p='news_scrape/init-airflow.sh'; d=open(p,'rb').read(); open(p,'wb').write(d.replace(b'\r\n',b'\n'))"
> ```
> (Or use your editor's "CRLF → LF" toggle / `dos2unix`.) No rebuild is needed — the script is
> volume-mounted, so just `docker compose --profile with-airflow up -d` again.

---

### 1. Run the data platform (`news_scrape/`)

All commands below are run from the `news_scrape/` directory.

**a. Create the `.env` file** from the template and fill in your values:

```bash
cd news_scrape
cp .env.example .env
```

Edit `.env` — at minimum set `CRYPTOCOMPARE_API_KEY`, and change the default
MongoDB / Airflow credentials. On Linux also set `AIRFLOW_UID` to your user id
(`echo "AIRFLOW_UID=$(id -u)" >> .env`).

**b. Create the shared external Docker network** (the FastAPI service attaches to it):

```bash
docker network create entire-app-net
```

**c. Start the stack.** MongoDB + the FastAPI API start by default; Airflow is
behind a profile so you opt in:

```bash
# MongoDB + FastAPI only
docker compose up -d

# MongoDB + FastAPI + the full Airflow stack
docker compose --profile with-airflow up -d
```

**Services / ports** (defaults, configurable via `.env`):

| Service          | URL                          | Notes                                  |
|------------------|------------------------------|----------------------------------------|
| FastAPI          | http://localhost:8000        | `/`, `/scraped_urls`, `/total_scraped_urls`, `/ner_count` |
| Airflow web UI   | http://localhost:8080        | login: `AIRFLOW_WEB_USER` / `AIRFLOW_WEB_PASSWORD` |
| MongoDB          | localhost:`${MONGO_PORT}`    | default host port `27027`              |

**d. Trigger the pipelines.** Open the Airflow UI and unpause / trigger the DAGs
(they are paused at creation):

- `scrape_and_process` — scrape news and run NER
  > NER runs **locally on CPU** via GLiNER (`urchade/gliner_small-v2.1`), loaded
  > in-process — no external NER endpoint is required. The model downloads once into
  > the `news-hf-cache` volume on first run.
- `fetch_coin_price_dag` — pull OHLCV price data
- `fetch_all_ner_count` — aggregate NER counts

**e. Stop the stack:**

```bash
docker compose --profile with-airflow down
# add -v to also remove the MongoDB / Postgres volumes
```

---

### 2. Run the ML / research code (repo root)

The training and feature code runs locally against the MongoDB populated by the
data platform (or your own data).

**a. Create a virtual environment and install dependencies:**

```bash
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

**b. Explore via the notebooks** in `research/`:

- `3.feature_engineering.ipynb` — build features
- `model_training.ipynb` — train a single model
- `multi_model_traning.ipynb` — compare multiple models

```bash
jupyter notebook research/
```

Model behavior is configured through the Hydra configs in `configs/hydra/`
(`model/lstm.yaml`, `model/xgboost.yaml`, … and `metrics.yaml`).

Trained artifacts land in `results/` (metrics, predictions, plots) and
`saved_models/` (e.g. the LSTM model `.h5` plus input/output scalers).

---

## Notes
- `news_scrape/` and the root ML code use **separate Python environments** with
  different pinned versions (e.g. `numpy`/`pandas`), so keep them isolated.
- `trash/` and `saved_models/` are gitignored; the committed LSTM model predates
  that rule.