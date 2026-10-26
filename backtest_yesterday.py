#!/usr/bin/env python3
"""Read-only prior-day LONG strategy diagnostic using OKX public swap candles."""
import json, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

SYMBOLS = {"BTCUSDT":"BTC-USDT-SWAP","ETHUSDT":"ETH-USDT-SWAP","SOLUSDT":"SOL-USDT-SWAP"}
BARS = {"1h":"1H","15m":"15m","5m":"5m"}

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20) as r: return json.loads(r.read().decode())

def candles(inst, bar, limit=300):
    q=urllib.parse.urlencode({"instId":inst,"bar":bar,"limit":str(limit)})
    p=get("https://www.okx.com/api/v5/market/history-candles?"+q)
    if p.get("code")!="0": raise RuntimeError(str(p))
    out=[]
    for k in reversed(p.get("data",[])):
        if len(k)>=9 and k[8]=="1":
            out.append({"t":int(k[0]),"o":float(k[1]),"h":float(k[2]),"l":float(k[3]),"c":float(k[4]),"v":float(k[6])})
    return out

def ema(v,n):
    if len(v)<n:return None
    x=sum(v[:n])/n; a=2/(n+1)
    for z in v[n:]:x=z*a+x*(1-a)
    return x

def rsi(v,n):
    if len(v)<=n:return None
    d=[b-a for a,b in zip(v[:-1],v[1:])]
    g=sum(max(x,0) for x in d[:n])/n; l=sum(max(-x,0) for x in d[:n])/n
    for x in d[n:]:
        g=(g*(n-1)+max(x,0))/n; l=(l*(n-1)+max(-x,0))/n
    return 100 if l==0 else 100-100/(1+g/l)

def macd_hist(v):
    s=[ema(v[:i],12)-ema(v[:i],26) for i in range(26,len(v)+1)]
    if len(s)<10:return None,None
    sig=ema(s,9)
    prev=ema(s[:-1],9)
    return s[-1]-sig, s[-2]-prev

def run(symbol,inst,start,end):
    data={k:candles(inst,v) for k,v in BARS.items()}
    h1,m15,m5=data["1h"],data["15m"],data["5m"]
    results=[]
    for i in range(60,len(m15)-1):
        t=m15[i]["t"]
        if not start<=t<end:continue
        # Indicators only use candles that had closed at the signal timestamp.
        hh=[x for x in h1 if x["t"]+3600000<=t+900000]
        ff=[x for x in m5 if x["t"]+300000<=t+900000]
        if len(hh)<55 or len(ff)<35:continue
        c1=[x["c"] for x in hh]; c15=[x["c"] for x in m15[:i+1]]; c5=[x["c"] for x in ff]
        hist,prev=macd_hist(c15)
        trend=ema(c1,20)>ema(c1,50) and c1[-1]>ema(c1,20)
        confirm=c15[-1]>ema(c15,20) and 50<=rsi(c15,14)<=70 and hist is not None and hist>0
        fh,fp=macd_hist(c5)
        early=rsi(c5,6)<=35 and fh is not None and fp is not None and fh>fp
        if trend and confirm:
            future=m15[i+1:i+5]
            if not future:continue
            entry=m15[i+1]["o"]
            up=(max(x["h"] for x in future)/entry-1)*100
            down=(min(x["l"] for x in future)/entry-1)*100
            results.append({"time_utc":datetime.fromtimestamp(t/1000,timezone.utc).isoformat(),"entry":entry,"max_up_pct_1h":round(up,4),"max_down_pct_1h":round(down,4),"5m_early_turn":early})
    return {"data_source":"OKX public swap history","signals":len(results),"results":results}

def main():
    now=datetime.now(timezone.utc)
    # Yesterday in Vietnam (UTC+7), expressed as UTC epoch boundaries.
    local=now+timedelta(hours=7)
    d=(local.date()-timedelta(days=1))
    start=int(datetime(d.year,d.month,d.day,tzinfo=timezone(timedelta(hours=7))).timestamp()*1000)
    end=start+86400000
    out={"date_vietnam":str(d),"method":"LONG-only historical signal audit: 1h EMA20/50 trend + 15m close above EMA20, RSI14 50-70 and positive MACD histogram; 5m RSI6/MACD rising is context only. Entry at next 15m open; measure next 1h high/low excursion. No fees, slippage, funding, stop/target or position sizing. Not a profitability backtest.","symbols":{}}
    for s,inst in SYMBOLS.items():
        try:out["symbols"][s]=run(s,inst,start,end)
        except Exception as e:out["symbols"][s]={"error":type(e).__name__+": "+str(e)}
        time.sleep(.2)
    with open("data/strategy_backtest_yesterday.json","w") as f:json.dump(out,f,indent=2)
    print(json.dumps({s:({"signals":v.get("signals"),"error":v.get("error")} ) for s,v in out["symbols"].items()},indent=2))
if __name__=="__main__":main()
