import matplotlib
matplotlib.use("Agg")
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

df = pd.read_csv("/out/research/btc_features.csv", index_col=0, parse_dates=True).sort_index()
df["next_close"] = df["close"].shift(-1)
df["ret_next"] = df["next_close"] / df["close"] - 1
df = df.dropna(subset=["next_close"])

price_features = ["close","volume","ret_1h","ret_3h","vol_change","rsi_14","macd","macd_signal","sma20_ratio","bb_pct"]
news_features = ["btc_mentions","n_articles","total_coin_mentions","btc_share","btc_mentions_3h"]
feats = price_features + news_features

def split(X, y, frac=0.8):
    n = int(len(X)*frac); return X.iloc[:n], X.iloc[n:], y.iloc[:n], y.iloc[n:]
def fit_pred(t):
    Xtr,Xte,ytr,yte = split(df[feats], df[t])
    m = XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=0).fit(Xtr,ytr)
    return yte, m.predict(Xte)

fig, ax = plt.subplots(2,1,figsize=(13,9),sharex=True)
yp,pp = fit_pred("next_close")
ax[0].plot(yp.index,yp.values,color="black",lw=1.6,label="actual")
ax[0].plot(yp.index,pp,color="tab:orange",lw=1.4,label="predicted")
ax[0].set_title("Next-hour BTC close: actual vs predicted (XGB, price+news)")
ax[0].set_ylabel("close (USD)"); ax[0].legend()
yr,pr = fit_pred("ret_next")
ax[1].plot(yr.index,yr.values,color="black",lw=1.2,label="actual")
ax[1].plot(yr.index,pr,color="tab:green",lw=1.2,label="predicted")
ax[1].axhline(0,color="grey",ls=":",lw=0.8)
ax[1].set_title("Next-hour return: actual vs predicted")
ax[1].set_ylabel("return"); ax[1].set_xlabel("time"); ax[1].legend()
plt.xticks(rotation=45); plt.tight_layout()
plt.savefig("/out/results/plots/predicted_vs_actual.png", dpi=120)
print("price  MAE", round(mean_absolute_error(yp,pp),2), "RMSE", round(mean_squared_error(yp,pp)**0.5,2))
print("return MAE", round(mean_absolute_error(yr,pr),6), "RMSE", round(mean_squared_error(yr,pr)**0.5,6))
print("return directional acc:", round(float((np.sign(pr)==np.sign(yr)).mean()),3))
print("test rows:", len(yp))
