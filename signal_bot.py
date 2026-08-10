import json, os, statistics, time
from datetime import datetime, timezone
import requests

STATE_FILE = "state.json"
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent":"Mozilla/5.0","Accept":"application/json,text/plain,*/*",
           "Referer":"https://edition.cnn.com/markets/fear-and-greed",
           "Origin":"https://edition.cnn.com"}
s = requests.Session(); s.headers.update(HEADERS)

def get_json(url, params=None, tries=3):
    last = None
    for i in range(tries):
        try:
            r = s.get(url, params=params, timeout=15); r.raise_for_status(); return r.json()
        except Exception as e:
            last = e
            if i + 1 < tries: time.sleep(2*(i+1))
    raise last

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def save_state(x):
    with open(STATE_FILE,"w",encoding="utf-8") as f: json.dump(x,f,ensure_ascii=False,indent=2)

def yahoo(symbol, range_="2y"):
    d = get_json(YAHOO_URL.format(symbol=symbol), {"range":range_,"interval":"1d","events":"history"})
    r=d["chart"]["result"][0]
    rows=[(t,c) for t,c in zip(r["timestamp"],r["indicators"]["quote"][0]["close"]) if c is not None]
    if not rows: raise RuntimeError("No Yahoo data: "+symbol)
    return rows

def vix_values():
    c=[float(x[1]) for x in yahoo("^VIX")]
    w=c[-100:]; sd=statistics.stdev(w)
    return c[-1], ((c[-1]-statistics.mean(w))/sd if sd else 0)

def spx_5d():
    c=[float(x[1]) for x in yahoo("^GSPC","1y")]
    return (c[-1]/c[-6]-1)*100

def fear_greed():
    x=get_json(CNN_URL)["fear_and_greed"]
    return float(x["score"]), str(x.get("rating","")), x.get("timestamp")

def fear_greed_cached(state):
    try:
        x=fear_greed()
        state["fear_greed"]={"score":x[0],"rating":x[1],"timestamp":x[2],
                             "fetched_at":datetime.now(timezone.utc).isoformat()}
        return x+(False,)
    except Exception as e:
        c=state.get("fear_greed")
        if c and "score" in c:
            print("WARNING: CNN F&G failed; using cached value:",e)
            return float(c["score"]),c.get("rating",""),c.get("timestamp"),True
        raise RuntimeError("CNN F&G unavailable and no cache exists: "+str(e))

def level(v,z,f,p):
    if v>=35: return 5,"VIX >= 35"
    if z>=2 and f<=10 and p<=-4: return 5,"ZVIX >= 2 & F&G <= 10 & S&P500 5d <= -4%"
    if z>=2 and p<=-4: return 4,"ZVIX >= 2 & S&P500 5d <= -4%"
    if v>=30 and f<=15: return 4,"VIX >= 30 & F&G <= 15"
    if z>=2: return 3,"ZVIX >= 2"
    if f<=15 and z<2: return 2,"F&G <= 15 & ZVIX < 2"
    if f>=80 and z<=-1: return 0,"F&G >= 80 & ZVIX <= -1"
    return 1,"None of the above"

def notify(title,msg):
    if not NTFY_TOPIC: raise RuntimeError("NTFY_TOPIC is empty")
    r=s.post("https://ntfy.sh/"+NTFY_TOPIC,data=msg.encode(),
             headers={"Title":title,"Priority":"high"},timeout=15)
    r.raise_for_status()

def main():
    state=load_state()
    v,z=vix_values(); p=spx_5d(); f,_,_,cached=fear_greed_cached(state)
    lv,reason=level(v,z,f,p); prev=int(state.get("last_level",1))
    print(f"VIX={v:.2f} ZVIX={z:.2f} F&G={f:.2f} SPX5d={p:.2f}% Level={lv} prev={prev} cached={cached}")
    if lv>=4 and lv!=prev:
        note="\n(F&Gは最後の成功取得値)" if cached else ""
        notify(f"米国株買い場 Level {lv}",
               f"Level {lv} の買い場候補を検出{note}\n\nVIX: {v:.2f}\nZVIX: {z:.2f}\nFear & Greed: {f:.0f}\nS&P500 5日騰落率: {p:.2f}%\n\n判定: {reason}\n\n※機械的な買い場候補通知です。")
    state["last_level"]=lv
    state["last_run_at"]=datetime.now(timezone.utc).isoformat()
    state["last_values"]={"vix":v,"zvix":z,"fear_greed":f,"spx5d":p,"level":lv,"reason":reason,"fear_greed_cached":cached}
    save_state(state)

if __name__=="__main__": main()
