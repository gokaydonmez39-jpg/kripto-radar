import streamlit as st
import requests
import pandas as pd
import numpy as np
import ta
import time
import json
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="ALFA NEXUS PRO v8.0 | Kripto Radar", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, limit=None, key="pro_autorefresh")

BINANCE_ENDPOINTS = [
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api4.binance.com",
    "https://api.binance.com",
]

TOP_COINS = [
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","DOGEUSDT",
    "ADAUSDT","AVAXUSDT","DOTUSDT","LINKUSDT","MATICUSDT","SHIBUSDT",
    "LTCUSDT","UNIUSDT","ATOMUSDT","ETCUSDT","NEARUSDT","APTUSDT",
    "FILUSDT","ARBUSDT","OPUSDT","INJUSDT","SUIUSDT","SEIUSDT",
    "TIAUSDT","JUPUSDT","STXUSDT","RENDERUSDT","FETUSDT","WIFUSDT",
    "PEPEUSDT","ONDOUSDT","TAOUSDT","RUNEUSDT","ENAUSDT","AAVEUSDT",
    "ICPUSDT","XLMUSDT","HBARUSDT","TRXUSDT"
]

TIMEFRAMES = {"1 Dakika":"1m","5 Dakika":"5m","15 Dakika":"15m","1 Saat":"1h","4 Saat":"4h","1 Gün":"1d"}

COIN_NAMES = {
    "BTC":"Bitcoin","ETH":"Ethereum","BNB":"BNB","SOL":"Solana","XRP":"Ripple","DOGE":"Dogecoin",
    "ADA":"Cardano","AVAX":"Avalanche","DOT":"Polkadot","LINK":"Chainlink","MATIC":"Polygon",
    "SHIB":"Shiba Inu","LTC":"Litecoin","UNI":"Uniswap","ATOM":"Cosmos","ETC":"Ethereum Classic",
    "NEAR":"NEAR Protocol","APT":"Aptos","FIL":"Filecoin","ARB":"Arbitrum","OP":"Optimism",
    "INJ":"Injective","SUI":"Sui","SEI":"Sei","TIA":"Celestia","JUP":"Jupiter","STX":"Stacks",
    "RENDER":"Render","FET":"Fetch.ai","WIF":"dogwifhat","PEPE":"Pepe","ONDO":"Ondo Finance",
    "TAO":"Bittensor","RUNE":"THORChain","ENA":"Ethena","AAVE":"Aave","ICP":"Internet Computer",
    "XLM":"Stellar","HBAR":"Hedera","TRX":"TRON"
}

# CSS
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800;900&display=swap');
.stApp{background:linear-gradient(135deg,#0a0a0f 0%,#0d1117 30%,#0a0e1a 70%,#080b12 100%);font-family:'Inter',sans-serif}
.stApp::before{content:'';position:fixed;top:0;left:0;right:0;bottom:0;background-image:linear-gradient(rgba(0,230,118,0.02) 1px,transparent 1px),linear-gradient(90deg,rgba(0,230,118,0.02) 1px,transparent 1px);background-size:80px 80px;pointer-events:none;z-index:0}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0d1117 0%,#161b22 100%)!important;border-right:1px solid rgba(0,230,118,0.1)!important}
header[data-testid="stHeader"]{background:rgba(10,10,15,0.9)!important;backdrop-filter:blur(20px);border-bottom:1px solid rgba(0,230,118,0.08)}
[data-testid="stMetric"]{background:rgba(13,17,23,0.8)!important;border:1px solid rgba(255,255,255,0.06)!important;border-radius:12px!important;padding:16px!important;backdrop-filter:blur(20px)}
[data-testid="stMetric"]:hover{border-color:rgba(0,230,118,0.2)!important;box-shadow:0 0 20px rgba(0,230,118,0.05)}
[data-testid="stMetricLabel"]{color:#8b949e!important;font-size:11px!important;font-weight:700!important;letter-spacing:1.5px!important;text-transform:uppercase!important;font-family:'JetBrains Mono',monospace!important}
[data-testid="stMetricValue"]{font-family:'JetBrains Mono',monospace!important;font-weight:900!important;font-size:28px!important}
[data-testid="stMetricDelta"]{font-family:'JetBrains Mono',monospace!important;font-weight:700!important}
.stTabs [data-baseweb="tab-list"]{gap:4px;background:rgba(13,17,23,0.6);border-radius:12px;padding:4px;border:1px solid rgba(255,255,255,0.05)}
.stTabs [data-baseweb="tab"]{border-radius:8px!important;color:#8b949e!important;font-weight:600!important;font-size:12px!important;font-family:'JetBrains Mono',monospace!important}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#00E676,#00BCD4)!important;color:#000!important;font-weight:800!important}
.stButton>button{background:linear-gradient(135deg,#00E676,#00BCD4)!important;color:#000!important;font-weight:800!important;border:none!important;border-radius:8px!important;font-family:'JetBrains Mono',monospace!important}
.stButton>button:hover{box-shadow:0 0 20px rgba(0,230,118,0.3)!important}
.stProgress>div>div>div{background:linear-gradient(90deg,#00E676,#00BCD4,#7C4DFF)!important}
hr{border-color:rgba(255,255,255,0.05)!important}
.signal-card{background:rgba(13,17,23,0.85);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:18px;backdrop-filter:blur(20px);transition:all 0.3s ease;margin-bottom:8px}
.signal-card:hover{border-color:rgba(0,230,118,0.15);box-shadow:0 4px 20px rgba(0,0,0,0.3)}
.signal-card-buy{border-left:3px solid #00E676}.signal-card-sell{border-left:3px solid #FF5252}.signal-card-neutral{border-left:3px solid #FFA726}
.coin-header{font-family:'JetBrains Mono',monospace;font-weight:900;font-size:18px;color:#e6edf3;margin-bottom:4px}
.coin-sub{font-family:'JetBrains Mono',monospace;font-size:11px;color:#555;letter-spacing:1px}
.price-main{font-family:'JetBrains Mono',monospace;font-weight:900;font-size:22px}
.badge{display:inline-block;padding:4px 14px;border-radius:20px;font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:800;letter-spacing:0.5px}
.badge-buy{background:rgba(0,230,118,0.15);color:#00E676;border:1px solid rgba(0,230,118,0.3)}
.badge-strong-buy{background:rgba(0,230,118,0.25);color:#00E676;border:1px solid rgba(0,230,118,0.5);box-shadow:0 0 10px rgba(0,230,118,0.2)}
.badge-sell{background:rgba(255,82,82,0.15);color:#FF5252;border:1px solid rgba(255,82,82,0.3)}
.badge-strong-sell{background:rgba(213,0,0,0.25);color:#FF5252;border:1px solid rgba(213,0,0,0.5);box-shadow:0 0 10px rgba(255,82,82,0.2)}
.badge-neutral{background:rgba(255,167,38,0.15);color:#FFA726;border:1px solid rgba(255,167,38,0.3)}
.indicator-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:6px;margin-top:8px}
.ind-chip{text-align:center;padding:6px 4px;border-radius:8px;font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700}
.ind-buy{background:rgba(0,230,118,0.1);color:#00E676;border:1px solid rgba(0,230,118,0.2)}
.ind-sell{background:rgba(255,82,82,0.1);color:#FF5252;border:1px solid rgba(255,82,82,0.2)}
.ind-neutral{background:rgba(255,255,255,0.03);color:#888;border:1px solid rgba(255,255,255,0.06)}
.signal-bar-container{display:flex;height:6px;border-radius:3px;overflow:hidden;margin:8px 0;gap:2px}
.signal-bar-buy{background:linear-gradient(90deg,#00E676,#69F0AE);border-radius:3px 0 0 3px}
.signal-bar-neutral{background:#444}.signal-bar-sell{background:linear-gradient(90deg,#FF5252,#D50000);border-radius:0 3px 3px 0}
.tp-sl-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}
.tp-card{text-align:center;padding:8px;border-radius:8px;font-family:'JetBrains Mono',monospace}
.tp-card-label{font-size:9px;color:#666;letter-spacing:1px}.tp-card-value{font-size:13px;font-weight:800;margin-top:2px}.tp-card-pct{font-size:9px;color:#555;margin-top:1px}
.score-gauge{text-align:center;padding:8px}.score-number{font-family:'JetBrains Mono',monospace;font-weight:900;font-size:36px;line-height:1}.score-label{font-family:'JetBrains Mono',monospace;font-size:10px;color:#666;letter-spacing:1.5px;margin-top:4px}
.main-header{display:flex;align-items:center;gap:16px;padding:8px 0 20px 0}
.logo-box{width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#00E676 0%,#00BCD4 50%,#7C4DFF 100%);display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;color:#000;box-shadow:0 0 30px rgba(0,230,118,0.3);font-family:'JetBrains Mono',monospace}
.title-main{font-family:'JetBrains Mono',monospace;font-weight:900;font-size:24px;background:linear-gradient(90deg,#00E676,#00BCD4,#7C4DFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px;line-height:1.2}
.title-sub{font-family:'JetBrains Mono',monospace;font-size:10px;color:#555;letter-spacing:3px;text-transform:uppercase}
.status-dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;animation:pulse 2s infinite}
.status-live{background:#00E676;box-shadow:0 0 8px #00E676}.status-loading{background:#FFA726;box-shadow:0 0 8px #FFA726}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
.disclaimer{text-align:center;font-size:10px;color:#333;padding:20px 0 10px 0;font-family:'JetBrains Mono',monospace;letter-spacing:0.5px;border-top:1px solid rgba(255,255,255,0.03);margin-top:30px}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
.api-status{font-family:'JetBrains Mono',monospace;font-size:10px;padding:4px 10px;border-radius:6px;display:inline-block}
.api-ok{background:rgba(0,230,118,0.1);color:#00E676;border:1px solid rgba(0,230,118,0.2)}
.api-fail{background:rgba(255,82,82,0.1);color:#FF5252;border:1px solid rgba(255,82,82,0.2)}
</style>""", unsafe_allow_html=True)


def try_binance_request(path, params=None, timeout=12):
    last_error = None
    for base_url in BINANCE_ENDPOINTS:
        try:
            resp = requests.get(f"{base_url}{path}", params=params, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "code" in data and data["code"] < 0:
                    last_error = f"{base_url}: {data.get('msg','API error')}"
                    continue
                return data, base_url
        except requests.exceptions.RequestException as e:
            last_error = f"{base_url}: {str(e)[:80]}"
            continue
    return None, last_error


def try_coingecko_fallback():
    try:
        resp = requests.get("https://api.coingecko.com/api/v3/coins/markets", params={"vs_currency":"usd","order":"market_cap_desc","per_page":50,"page":1,"sparkline":False}, timeout=15)
        if resp.status_code == 200: return resp.json()
    except: pass
    return None


@st.cache_data(ttl=55)
def get_market_data():
    data, source = try_binance_request("/api/v3/ticker/24hr")
    if data and isinstance(data, list):
        market = {}
        for item in data:
            if item.get("symbol") in TOP_COINS:
                market[item["symbol"]] = {"price":float(item["lastPrice"]),"change":float(item["priceChangePercent"]),"high":float(item["highPrice"]),"low":float(item["lowPrice"]),"volume":float(item["volume"]),"quoteVolume":float(item["quoteVolume"])}
        return market, source
    return {}, source


@st.cache_data(ttl=55)
def get_klines(symbol, interval="1h", limit=200):
    data, _ = try_binance_request("/api/v3/klines", params={"symbol":symbol,"interval":interval,"limit":limit})
    if data and isinstance(data, list) and len(data) > 0:
        df = pd.DataFrame(data, columns=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"])
        for col in ["open","high","low","close","volume","quote_volume"]: df[col] = df[col].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        return df
    return None


@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = resp.json()
        if data and "data" in data and len(data["data"]) > 0: return data["data"][0]
    except: pass
    return None


def analyze_coin(df, symbol):
    if df is None or len(df) < 50: return None
    close=df["close"];high=df["high"];low=df["low"];volume=df["volume"];price=close.iloc[-1]
    result={"symbol":symbol,"name":symbol.replace("USDT",""),"price":price};signals=[]

    rsi=ta.momentum.RSIIndicator(close,window=14).rsi().iloc[-1];result["rsi"]=rsi
    if rsi<30:signals.append({"name":"RSI","dir":"AL","val":f"{rsi:.1f}","w":2})
    elif rsi<40:signals.append({"name":"RSI","dir":"AL","val":f"{rsi:.1f}","w":1})
    elif rsi>70:signals.append({"name":"RSI","dir":"SAT","val":f"{rsi:.1f}","w":2})
    elif rsi>60:signals.append({"name":"RSI","dir":"SAT","val":f"{rsi:.1f}","w":1})
    else:signals.append({"name":"RSI","dir":"NÖTR","val":f"{rsi:.1f}","w":0})

    macd_ind=ta.trend.MACD(close,window_slow=26,window_fast=12,window_sign=9)
    ml=macd_ind.macd().iloc[-1];ms=macd_ind.macd_signal().iloc[-1];mh=macd_ind.macd_diff().iloc[-1];result["macd_hist"]=mh
    if mh>0 and ml>ms:signals.append({"name":"MACD","dir":"AL","val":f"{mh:.4f}","w":2})
    elif mh<0 and ml<ms:signals.append({"name":"MACD","dir":"SAT","val":f"{mh:.4f}","w":2})
    else:signals.append({"name":"MACD","dir":"NÖTR","val":f"{mh:.4f}","w":0})

    bb=ta.volatility.BollingerBands(close,window=20,window_dev=2)
    bu=bb.bollinger_hband().iloc[-1];bl=bb.bollinger_lband().iloc[-1];bm=bb.bollinger_mavg().iloc[-1]
    bw=((bu-bl)/bm)*100 if bm>0 else 0;result["bb_width"]=bw;result["bb_squeeze"]=bw<3
    if price<=bl:signals.append({"name":"BB","dir":"AL","val":"Alt Band","w":2})
    elif price>=bu:signals.append({"name":"BB","dir":"SAT","val":"Üst Band","w":2})
    else:signals.append({"name":"BB","dir":"NÖTR","val":"Orta","w":0})

    ema9=ta.trend.EMAIndicator(close,window=9).ema_indicator().iloc[-1]
    ema21=ta.trend.EMAIndicator(close,window=21).ema_indicator().iloc[-1]
    ema50=ta.trend.EMAIndicator(close,window=50).ema_indicator().iloc[-1]
    result["ema9"]=ema9;result["ema21"]=ema21;result["ema50"]=ema50
    if ema9>ema21>ema50:signals.append({"name":"EMA","dir":"AL","val":"9>21>50","w":2})
    elif ema9<ema21<ema50:signals.append({"name":"EMA","dir":"SAT","val":"9<21<50","w":2})
    elif ema9>ema21:signals.append({"name":"EMA","dir":"AL","val":"9>21","w":1})
    else:signals.append({"name":"EMA","dir":"SAT","val":"Karışık","w":1})

    stoch=ta.momentum.StochRSIIndicator(close,window=14,smooth1=3,smooth2=3)
    sk=stoch.stochrsi_k().iloc[-1]*100;sd=stoch.stochrsi_d().iloc[-1]*100;result["stoch_k"]=sk
    if sk<20 and sk>sd:signals.append({"name":"StochRSI","dir":"AL","val":f"{sk:.0f}","w":2})
    elif sk>80 and sk<sd:signals.append({"name":"StochRSI","dir":"SAT","val":f"{sk:.0f}","w":2})
    else:signals.append({"name":"StochRSI","dir":"NÖTR","val":f"{sk:.0f}","w":0})

    tp=(high+low+close)/3;ctpv=(tp*volume).rolling(20).sum();cvol=volume.rolling(20).sum()
    vwap=(ctpv/cvol).iloc[-1] if cvol.iloc[-1]>0 else price;result["vwap"]=vwap
    if price>vwap*1.005:signals.append({"name":"VWAP","dir":"AL","val":f"${vwap:.2f}","w":1})
    elif price<vwap*0.995:signals.append({"name":"VWAP","dir":"SAT","val":f"${vwap:.2f}","w":1})
    else:signals.append({"name":"VWAP","dir":"NÖTR","val":f"${vwap:.2f}","w":0})

    obv_s=ta.volume.OnBalanceVolumeIndicator(close,volume).on_balance_volume()
    on=obv_s.iloc[-1];op=obv_s.iloc[-2] if len(obv_s)>1 else on;result["obv_trend"]="Yükseliş" if on>op else "Düşüş"
    if on>op:signals.append({"name":"OBV","dir":"AL","val":"Yükseliş","w":1})
    else:signals.append({"name":"OBV","dir":"SAT","val":"Düşüş","w":1})

    sp=min(200,len(close));sma200=close.rolling(sp).mean().iloc[-1];result["sma200"]=sma200
    if price>sma200:signals.append({"name":"SMA200","dir":"AL","val":f"${sma200:.2f}","w":1})
    else:signals.append({"name":"SMA200","dir":"SAT","val":f"${sma200:.2f}","w":1})

    atr=ta.volatility.AverageTrueRange(high,low,close,window=14).average_true_range().iloc[-1];result["atr"]=atr

    try:
        adx=ta.trend.ADXIndicator(high,low,close,window=14).adx().iloc[-1];result["adx"]=adx
        if adx>25:signals.append({"name":"ADX","dir":"AL" if ema9>ema21 else "SAT","val":f"{adx:.0f}","w":1})
        else:signals.append({"name":"ADX","dir":"NÖTR","val":f"{adx:.0f}","w":0})
    except:result["adx"]=0

    o2,h2,l2,c2=df["open"].iloc[-1],df["high"].iloc[-1],df["low"].iloc[-1],df["close"].iloc[-1]
    po2,pc2=df["open"].iloc[-2],df["close"].iloc[-2]
    body=abs(c2-o2);rng=h2-l2;us=h2-max(o2,c2);ls=min(o2,c2)-l2
    cp,ct="Normal","neutral"
    if rng>0:
        if body/rng<0.1 and ls>body*2:cp,ct="Çekiç 🔨","bullish"
        elif body/rng<0.1 and us>body*2:cp,ct="Ters Çekiç ⚡","bearish"
        elif c2>o2 and pc2<po2 and c2>df["high"].iloc[-2]:cp,ct="Yutan Boğa 🐂","bullish"
        elif o2>c2 and po2<pc2 and o2>pc2:cp,ct="Yutan Ayı 🐻","bearish"
        elif body/rng<0.05:cp,ct="Doji ✦","neutral"
        elif c2>o2 and body>rng*0.7:cp,ct="Güçlü Boğa 🚀","bullish"
        elif o2>c2 and body>rng*0.7:cp,ct="Güçlü Ayı 📉","bearish"
    result["candle_pattern"]=cp;result["candle_type"]=ct
    if ct=="bullish":signals.append({"name":"Mum","dir":"AL","val":cp,"w":1})
    elif ct=="bearish":signals.append({"name":"Mum","dir":"SAT","val":cp,"w":1})

    sr=sum(s["w"]*(1 if s["dir"]=="AL" else -1 if s["dir"]=="SAT" else 0) for s in signals)
    mx=sum(s["w"] for s in signals) if signals else 1
    nm=((sr+mx)/(2*mx))*100;result["score"]=nm;result["signals"]=signals
    if nm>=75:result["direction"]="GÜÇLÜ AL";result["strength"]="very-bullish"
    elif nm>=60:result["direction"]="AL";result["strength"]="bullish"
    elif nm>=45:result["direction"]="NÖTR";result["strength"]="neutral"
    elif nm>=30:result["direction"]="SAT";result["strength"]="bearish"
    else:result["direction"]="GÜÇLÜ SAT";result["strength"]="very-bearish"

    result["tp1"]=price+atr*1.5;result["tp2"]=price+atr*2.5;result["tp3"]=price+atr*4.0;result["sl"]=price-atr*1.2
    va=volume.tail(20).mean();vl=volume.iloc[-1];result["vol_ratio"]=vl/va if va>0 else 1
    return result


def get_direction_color(s):return{"very-bullish":"#00E676","bullish":"#66BB6A","neutral":"#FFA726","bearish":"#EF5350","very-bearish":"#D50000"}.get(s,"#888")
def get_badge_class(s):return{"very-bullish":"badge-strong-buy","bullish":"badge-buy","neutral":"badge-neutral","bearish":"badge-sell","very-bearish":"badge-strong-sell"}.get(s,"badge-neutral")
def get_card_class(s):
    if s in("very-bullish","bullish"):return "signal-card-buy"
    if s in("very-bearish","bearish"):return "signal-card-sell"
    return "signal-card-neutral"
def format_price(p):
    if p>=1000:return f"${p:,.2f}"
    elif p>=1:return f"${p:.4f}"
    elif p>=0.001:return f"${p:.6f}"
    return f"${p:.8f}"
def format_volume(v):
    if v>=1e9:return f"${v/1e9:.2f}B"
    elif v>=1e6:return f"${v/1e6:.2f}M"
    elif v>=1e3:return f"${v/1e3:.1f}K"
    return f"${v:.0f}"

def render_signal_bar(signals):
    b=sum(1 for s in signals if s["dir"]=="AL");se=sum(1 for s in signals if s["dir"]=="SAT");n=sum(1 for s in signals if s["dir"]=="NÖTR")
    return f'<div class="signal-bar-container"><div class="signal-bar-buy" style="flex:{b};min-width:{"4px" if b>0 else "0"}"></div><div class="signal-bar-neutral" style="flex:{n};min-width:{"4px" if n>0 else "0"}"></div><div class="signal-bar-sell" style="flex:{se};min-width:{"4px" if se>0 else "0"}"></div></div><div style="display:flex;justify-content:space-between;font-family:\'JetBrains Mono\',monospace;font-size:10px;color:#555"><span style="color:#00E676">{b} AL</span><span>{n} NÖTR</span><span style="color:#FF5252">{se} SAT</span></div>'

def render_chips(signals):
    ch=""
    for s in signals:
        cl="ind-buy" if s["dir"]=="AL" else "ind-sell" if s["dir"]=="SAT" else "ind-neutral"
        ch+=f'<div class="ind-chip {cl}">{s["name"]}<br><b>{s["dir"]}</b></div>'
    return f'<div class="indicator-grid">{ch}</div>'

def render_tp_sl(coin):
    p=coin["price"]
    items=[("TP1",coin["tp1"],"#00E676","rgba(0,230,118,0.08)","rgba(0,230,118,0.2)"),("TP2",coin["tp2"],"#69F0AE","rgba(105,240,174,0.08)","rgba(105,240,174,0.2)"),("TP3",coin["tp3"],"#B2FF59","rgba(178,255,89,0.08)","rgba(178,255,89,0.2)"),("SL",coin["sl"],"#FF5252","rgba(255,82,82,0.08)","rgba(255,82,82,0.2)")]
    cards=""
    for lb,val,col,bg,bd in items:
        pct=((val-p)/p)*100
        cards+=f'<div class="tp-card" style="background:{bg};border:1px solid {bd}"><div class="tp-card-label">{lb}</div><div class="tp-card-value" style="color:{col}">{format_price(val)}</div><div class="tp-card-pct">{pct:+.2f}%</div></div>'
    return f'<div class="tp-sl-grid">{cards}</div>'

def render_card(coin, mkt_data):
    sym=coin["symbol"];nm=coin["name"];fn=COIN_NAMES.get(nm,nm);col=get_direction_color(coin["strength"]);bg=get_badge_class(coin["strength"]);cc=get_card_class(coin["strength"]);p=coin["price"]
    m=mkt_data.get(sym,{});ch=m.get("change",0);ci="▲" if ch>=0 else "▼";ccl="change-positive" if ch>=0 else "change-negative";vu=m.get("quoteVolume",0)
    return f'''<div class="signal-card {cc}"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="display:flex;align-items:center;gap:12px"><div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,{col}30,{col}10);display:flex;align-items:center;justify-content:center;font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:900;color:{col};border:2px solid {col}60">{nm[:3]}</div><div><div class="coin-header">{nm}/USDT</div><div class="coin-sub">{fn}</div></div></div><div style="text-align:right"><div class="price-main" style="color:#e6edf3">{format_price(p)}</div><div class="{ccl}" style="font-family:'JetBrains Mono',monospace;font-weight:700;font-size:14px">{ci} {abs(ch):.2f}%</div></div></div><div style="display:flex;justify-content:space-between;align-items:center;margin:12px 0 8px 0"><div class="score-gauge"><div class="score-number" style="color:{col}">{coin["score"]:.0f}</div><div class="score-label">SİNYAL SKORU</div></div><div><span class="badge {bg}">{coin["direction"]}</span></div><div style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:#555"><div>RSI: <b style="color:{"#00E676" if coin["rsi"]<30 else "#FF5252" if coin["rsi"]>70 else "#FFA726"}">{coin["rsi"]:.1f}</b></div><div>Hacim: <b style="color:#00BCD4">{format_volume(vu)}</b></div><div>{coin["candle_pattern"]}</div>{"<div style=color:#7C4DFF;font-weight:700>⚡ BB SIKIŞTIRMA</div>" if coin.get("bb_squeeze") else ""}</div></div>{render_signal_bar(coin["signals"])}{render_chips(coin["signals"])}<div style="margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:10px;color:#555;letter-spacing:1px;font-weight:700">TP/SL SEVİYELERİ (ATR)</div>{render_tp_sl(coin)}</div>'''


def main():
    st.markdown('<div class="main-header"><div class="logo-box">α</div><div><div class="title-main">ALFA NEXUS PRO v8.0</div><div class="title-sub">Bulut Tabanlı Algoritmik Ticaret Paneli</div></div></div>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown('<div style="text-align:center;padding:12px 0"><div style="font-family:\'JetBrains Mono\',monospace;font-weight:900;font-size:18px;background:linear-gradient(90deg,#00E676,#00BCD4);-webkit-background-clip:text;-webkit-text-fill-color:transparent">⚙️ KONTROL PANELİ</div></div>', unsafe_allow_html=True)
        stfl=st.selectbox("⏱ Zaman Dilimi",list(TIMEFRAMES.keys()),index=3);stf=TIMEFRAMES[stfl]
        st.markdown("---")
        sf=st.selectbox("🎯 Sinyal Filtresi",["🔵 Tümü","🟢 Sadece AL","🔴 Sadece SAT","⚡ Güçlü Sinyaller","🔥 BB Sıkışma"])
        st.markdown("---")
        so=st.selectbox("📊 Sıralama",["Skor (Yüksek→Düşük)","Skor (Düşük→Yüksek)","Değişim (Yüksek)","Değişim (Düşük)","RSI (Düşük)","RSI (Yüksek)"])
        st.markdown("---")
        cs=st.text_input("🔍 Coin Ara","",placeholder="BTC, ETH, SOL...")
        st.markdown("---")
        if st.button("🔄 Verileri Yenile",use_container_width=True):st.cache_data.clear();st.rerun()

    pb=st.progress(0);stx=st.empty()
    stx.markdown('<div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#555"><span class="status-dot status-loading"></span>API bağlantısı test ediliyor...</div>', unsafe_allow_html=True)

    mkt,api_src=get_market_data();fng=get_fear_greed()

    if not mkt:
        st.error(f"⚠️ **Binance API bağlantı hatası!**\n\nDenenen: data-api.binance.vision, api1-4.binance.com\n\nHata: {api_src}")
        st.info("🔄 CoinGecko yedek API deneniyor...")
        cg=try_coingecko_fallback()
        if cg:
            st.success("✅ CoinGecko bağlantısı başarılı (sınırlı veri)")
            for c in cg[:20]:
                chg=c.get("price_change_percentage_24h",0)
                st.markdown(f'<div class="signal-card signal-card-neutral"><div style="display:flex;justify-content:space-between"><div class="coin-header">{c["symbol"].upper()}/USD</div><div class="price-main" style="color:#e6edf3">${c["current_price"]:,.2f}</div></div><div style="color:{"#00E676" if chg>=0 else "#FF5252"};font-family:\'JetBrains Mono\',monospace;font-weight:700">{"▲" if chg>=0 else "▼"} {abs(chg):.2f}%</div></div>', unsafe_allow_html=True)
        else:st.error("❌ Hiçbir API'ye bağlanılamadı.")
        return

    al=api_src.replace("https://","").split("/")[0] if isinstance(api_src,str) and "http" in api_src else "?"
    stx.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#555"><span class="status-dot status-live"></span><b style="color:#00E676">BAĞLANTI OK</b> • <span class="api-status api-ok">{al}</span></div>', unsafe_allow_html=True)

    results=[]
    for i,sym in enumerate(TOP_COINS):
        df=get_klines(sym,stf)
        if df is not None:
            r=analyze_coin(df,sym)
            if r:results.append(r)
        pb.progress((i+1)/len(TOP_COINS))
    pb.empty();stx.empty()

    if not results:st.error("⚠️ Veri yok.");return

    fl=results.copy()
    if cs:fl=[c for c in fl if cs.upper() in c["name"]]
    if "AL" in sf:fl=[c for c in fl if c["score"]>=60]
    elif "SAT" in sf:fl=[c for c in fl if c["score"]<40]
    elif "Güçlü" in sf:fl=[c for c in fl if c["score"]>=75 or c["score"]<25]
    elif "Sıkışma" in sf:fl=[c for c in fl if c.get("bb_squeeze")]

    if "Yüksek→Düşük" in so:fl.sort(key=lambda x:x["score"],reverse=True)
    elif "Düşük→Yüksek" in so:fl.sort(key=lambda x:x["score"])
    elif "Değişim (Yüksek)" in so:fl.sort(key=lambda x:mkt.get(x["symbol"],{}).get("change",0),reverse=True)
    elif "Değişim (Düşük)" in so:fl.sort(key=lambda x:mkt.get(x["symbol"],{}).get("change",0))
    elif "RSI (Düşük)" in so:fl.sort(key=lambda x:x["rsi"])
    elif "RSI (Yüksek)" in so:fl.sort(key=lambda x:x["rsi"],reverse=True)

    bc=sum(1 for c in results if c["score"]>=60);sc2=sum(1 for c in results if c["score"]<40)
    nc=sum(1 for c in results if 40<=c["score"]<60);sqc=sum(1 for c in results if c.get("bb_squeeze"))
    avs=np.mean([c["score"] for c in results])

    cn=7 if fng else 6;cols=st.columns(cn)
    with cols[0]:st.metric("🟢 AL SİNYALİ",bc,delta=f"{(bc/len(results)*100):.0f}%")
    with cols[1]:st.metric("🔴 SAT SİNYALİ",sc2,delta=f"{(sc2/len(results)*100):.0f}%",delta_color="inverse")
    with cols[2]:st.metric("🟡 NÖTR",nc)
    with cols[3]:st.metric("⚡ BB SIKIŞTIRMA",sqc)
    with cols[4]:
        btc=mkt.get("BTCUSDT",{});st.metric("₿ BTC",f"${btc.get('price',0):,.0f}",delta=f"{btc.get('change',0):+.2f}%")
    with cols[5]:st.metric("📊 ORT. SKOR",f"{avs:.0f}/100")
    if fng:
        with cols[6]:fv=int(fng.get("value",50));st.metric("😱 KORKU/AÇGÖZLÜLÜK",f"{fv}",delta=fng.get("value_classification",""))

    st.markdown("---")
    now=datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px"><div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#555"><span class="status-dot status-live"></span><b style="color:#00E676">CANLI</b> • {len(fl)} coin • {stfl} • <span class="api-status api-ok">{al}</span></div><div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;color:#444">Son: {now} • Oto: 60sn</div></div>', unsafe_allow_html=True)

    t1,t2,t3=st.tabs(["📡 SİNYAL KARTLARI","📋 TABLO","📈 DETAY"])

    with t1:
        if not fl:st.warning("Sonuç yok.")
        else:
            c1,c2=st.columns(2)
            for i,coin in enumerate(fl):
                h=render_card(coin,mkt)
                if i%2==0:
                    with c1:st.markdown(h,unsafe_allow_html=True)
                else:
                    with c2:st.markdown(h,unsafe_allow_html=True)

    with t2:
        td=[]
        for coin in fl:
            m2=mkt.get(coin["symbol"],{});bs=sum(1 for s in coin["signals"] if s["dir"]=="AL");ss=sum(1 for s in coin["signals"] if s["dir"]=="SAT")
            td.append({"Coin":coin["name"],"Fiyat":format_price(coin["price"]),"Değişim":f"{m2.get('change',0):+.2f}%","RSI":f"{coin['rsi']:.1f}","MACD":"▲" if coin["macd_hist"]>0 else "▼","Skor":f"{coin['score']:.0f}","Yön":coin["direction"],"AL":bs,"SAT":ss,"Formason":coin["candle_pattern"],"Sıkışma":"⚡" if coin.get("bb_squeeze") else "","TP1":format_price(coin["tp1"]),"SL":format_price(coin["sl"])})
        st.dataframe(pd.DataFrame(td),use_container_width=True,height=min(len(td)*42+60,800),hide_index=True)

    with t3:
        if fl:
            sel=st.selectbox("Coin Seçin",[c["name"] for c in fl])
            coin=next((c for c in fl if c["name"]==sel),None)
            if coin:
                col=get_direction_color(coin["strength"])
                st.markdown(f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px"><div style="width:60px;height:60px;border-radius:16px;background:linear-gradient(135deg,{col}40,{col}10);display:flex;align-items:center;justify-content:center;font-family:\'JetBrains Mono\',monospace;font-size:22px;font-weight:900;color:{col};border:2px solid {col}60">{coin["name"][:3]}</div><div><div style="font-family:\'JetBrains Mono\',monospace;font-size:28px;font-weight:900;color:#e6edf3">{coin["name"]}/USDT</div><div style="font-size:14px;color:#555">{COIN_NAMES.get(coin["name"],coin["name"])}</div></div><div style="margin-left:auto;text-align:right"><div style="font-family:\'JetBrains Mono\',monospace;font-size:32px;font-weight:900;color:{col}">{format_price(coin["price"])}</div><span class="badge {get_badge_class(coin["strength"])}" style="font-size:14px;padding:6px 20px">{coin["direction"]}</span></div></div>', unsafe_allow_html=True)
                x1,x2,x3=st.columns([1,2,1])
                with x1:st.markdown(f'<div class="score-gauge" style="padding:20px"><div class="score-number" style="color:{col};font-size:56px">{coin["score"]:.0f}</div><div class="score-label">SKOR / 100</div></div>', unsafe_allow_html=True)
                with x2:st.markdown(f'<div style="padding:10px 0"><div style="font-family:\'JetBrains Mono\',monospace;font-size:10px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:8px">İNDİKATÖRLER</div>{render_signal_bar(coin["signals"])}<div style="margin-top:12px">{render_chips(coin["signals"])}</div></div>', unsafe_allow_html=True)
                with x3:st.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;padding:10px 0"><div style="color:#555;margin-bottom:8px;font-weight:700">BİLGİ</div><div style="color:#888">RSI: <b style="color:{"#00E676" if coin["rsi"]<30 else "#FF5252" if coin["rsi"]>70 else "#FFA726"}">{coin["rsi"]:.1f}</b></div><div style="color:#888">ATR: <b style="color:#00BCD4">{format_price(coin["atr"])}</b></div><div style="color:#888">Mum: <b>{coin["candle_pattern"]}</b></div>{"<div style=color:#7C4DFF;font-weight:700>⚡ BB SIKIŞTIRMA</div>" if coin.get("bb_squeeze") else ""}</div>', unsafe_allow_html=True)
                st.markdown("---")
                st.markdown(f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:11px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:10px">🎯 TP/SL</div>{render_tp_sl(coin)}', unsafe_allow_html=True)
                st.markdown("---")
                dc=st.columns(4)
                for i,(k,v) in enumerate([("RSI",f"{coin['rsi']:.1f}"),("MACD",f"{coin['macd_hist']:.6f}"),("BB",f"{coin['bb_width']:.2f}%"),("StochRSI",f"{coin.get('stoch_k',0):.1f}"),("EMA9",format_price(coin['ema9'])),("EMA21",format_price(coin['ema21'])),("EMA50",format_price(coin['ema50'])),("SMA200",format_price(coin['sma200'])),("VWAP",format_price(coin['vwap'])),("ATR",format_price(coin['atr'])),("ADX",f"{coin.get('adx',0):.1f}"),("OBV",coin['obv_trend'])]):
                    with dc[i%4]:st.markdown(f'<div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:10px;margin-bottom:6px;border:1px solid rgba(255,255,255,0.04)"><div style="font-family:\'JetBrains Mono\',monospace;font-size:9px;color:#555">{k}</div><div style="font-family:\'JetBrains Mono\',monospace;font-size:14px;font-weight:800;color:#ccc;margin-top:2px">{v}</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="disclaimer"><span style="letter-spacing:2px">ALFA NEXUS PRO v8.0</span> • Multi-API Fallback • 10 İndikatör + ATR TP/SL<br>⚠️ Bu panel yatırım tavsiyesi değildir.</div>', unsafe_allow_html=True)

if __name__=="__main__":main()
