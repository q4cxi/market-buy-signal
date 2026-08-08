import json
import os
from pathlib import Path

import requests
import yfinance as yf

STATE_FILE = Path("state.json")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

def close_series(df):
    s = df["Close"]
    if hasattr(s, "columns"):
        s = s.iloc[:, 0]
    return s.dropna()

def get_fear_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    r.raise_for_status()
    data = r.json()
    fg = data.get("fear_and_greed", {})
    if not isinstance(fg, dict) or fg.get("score") is None:
        raise RuntimeError("Fear & Greed score unavailable")
    return float(fg["score"])

def get_market_data():
    vix = yf.download("^VIX", period="130d", interval="1d",
                       auto_adjust=False, progress=False)
    spx = yf.download("^GSPC", period="10d", interval="1d",
                       auto_adjust=False, progress=False)
    if vix.empty or spx.empty:
        raise RuntimeError("Yahoo Finance returned no data")

    vc = close_series(vix)
    sc = close_series(spx)
    if len(vc) < 101 or len(sc) < 6:
        raise RuntimeError("Not enough history")

    current_vix = float(vc.iloc[-1])
    base = vc.iloc[-101:-1]
    std = float(base.std(ddof=1))
    if std == 0:
        raise RuntimeError("VIX std is zero")

    zvix = (current_vix - float(base.mean())) / std
    spx5d = (float(sc.iloc[-1]) / float(sc.iloc[-6]) - 1) * 100
    fg = get_fear_greed()

    return {"vix": current_vix, "zvix": zvix, "fg": fg, "spx5d": spx5d}

def classify(d):
    v, z, f, s = d["vix"], d["zvix"], d["fg"], d["spx5d"]
    if v >= 35 or (z >= 2 and f <= 10 and s <= -4):
        return 5
    if (z >= 2 and s <= -4) or (v >= 30 and f <= 15):
        return 4
    return 1

def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_notified_level": 1}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")

def send_ntfy(level, d):
    title = f"🚨{'🚨' if level == 5 else ''} 米国株 買い場シグナル LEVEL {level}"
    msg = (
        f"VIX: {d['vix']:.2f}\n"
        f"ZVIX: {d['zvix']:.2f}\n"
        f"Fear & Greed: {d['fg']:.1f}\n"
        f"S&P500 5日騰落率: {d['spx5d']:.2f}%\n\n"
        f"判定: LEVEL {level}\n"
        "※市場全体の買い場候補シグナル。個別銘柄の推奨ではありません。"
    )
    r = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg.encode("utf-8"),
        headers={"Title": title, "Priority": "max" if level == 5 else "high",
                 "Tags": "rotating_light"},
        timeout=15,
    )
    r.raise_for_status()

def main():
    d = get_market_data()
    level = classify(d)
    state = load_state()
    previous = int(state.get("last_notified_level", 1))

    if level >= 4 and level > previous:
        send_ntfy(level, d)
        state["last_notified_level"] = level
        save_state(state)
        print(f"NOTIFIED Level {level}")
    elif level < 4:
        if previous >= 4:
            state["last_notified_level"] = 1
            save_state(state)
        print(f"No signal: Level {level}")
    else:
        print(f"Already notified Level {previous}")

if __name__ == "__main__":
    main()
