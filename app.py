import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ═══════════════════════════════════════════════════════════════════════════
#  ALFA NEXUS PRO v8.0 — BULUT TABANLI ALGORİTMİK TİCARET PANELİ
#  Streamlit Cloud Uyumlu — CoinGecko + CryptoCompare API
#  Binance API ABD sunucularında engellendiği için alternatif veri kaynakları
# ═══════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="ALFA NEXUS PRO v8.0 | Kripto Radar", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")
st_autorefresh(interval=60000, limit=None, key="autorefresh")

# Top 40 coin — CoinGecko ID'leri
COINS = {
    "bitcoin":{"sym":"BTC","name":"Bitcoin"},"ethereum":{"sym":"ETH","name":"Ethereum"},
    "binancecoin":{"sym":"BNB","name":"BNB"},"solana":{"sym":"SOL","name":"Solana"},
    "ripple":{"sym":"XRP","name":"Ripple"},"dogecoin":{"sym":"DOGE","name":"Dogecoin"},
    "cardano":{"sym":"ADA","name":"Cardano"},"avalanche-2":{"sym":"AVAX","name":"Avalanche"},
    "polkadot":{"sym":"DOT","name":"Polkadot"},"chainlink":{"sym":"LINK","name":"Chainlink"},
    "matic-network":{"sym":"MATIC","name":"Polygon"},"shiba-inu":{"sym":"SHIB","name":"Shiba Inu"},
    "litecoin":{"sym":"LTC","name":"Litecoin"},"uniswap":{"sym":"UNI","name":"Uniswap"},
    "cosmos":{"sym":"ATOM","name":"Cosmos"},"ethereum-classic":{"sym":"ETC","name":"Ethereum Classic"},
    "near":{"sym":"NEAR","name":"NEAR Protocol"},"aptos":{"sym":"APT","name":"Aptos"},
    "filecoin":{"sym":"FIL","name":"Filecoin"},"arbitrum":{"sym":"ARB","name":"Arbitrum"},
    "optimism":{"sym":"OP","name":"Optimism"},"injective-protocol":{"sym":"INJ","name":"Injective"},
    "sui":{"sym":"SUI","name":"Sui"},"sei-network":{"sym":"SEI","name":"Sei"},
    "celestia":{"sym":"TIA","name":"Celestia"},"jupiter-exchange-solana":{"sym":"JUP","name":"Jupiter"},
    "blockstack":{"sym":"STX","name":"Stacks"},"render-token":{"sym":"RENDER","name":"Render"},
    "fetch-ai":{"sym":"FET","name":"Fetch.ai"},"dogwifcoin":{"sym":"WIF","name":"dogwifhat"},
    "pepe":{"sym":"PEPE","name":"Pepe"},"ondo-finance":{"sym":"ONDO","name":"Ondo Finance"},
    "bittensor":{"sym":"TAO","name":"Bittensor"},"thorchain":{"sym":"RUNE","name":"THORChain"},
    "ethena":{"sym":"ENA","name":"Ethena"},"aave":{"sym":"AAVE","name":"Aave"},
    "internet-computer":{"sym":"ICP","name":"Internet Computer"},"stellar":{"sym":"XLM","name":"Stellar"},
    "hedera-hashgraph":{"sym":"HBAR","name":"Hedera"},"tron":{"sym":"TRX","name":"TRON"},
}

TF_MAP = {"1 Saat":"1","4 Saat":"4","1 Gün":"24","7 Gün":"168","30 Gün":"720"}

# ── CSS ──
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800;900&display=swap');
.stApp{background:linear-gradient(135deg,#0a0a0f 0%,#0d1117 30%,#0a0e1a 70%,#080b12 100%)}
.stApp::before{content:'';position:fixed;top:0;left:0;right:0;bottom:0;background-image:linear-gradient(rgba(0,230,118,0.02) 1px,transparent 1px),linear-gradient(90deg,rgba(0,230,118,0.02) 1px,transparent 1px);background-size:80px 80px;pointer-events:none;z-index:0}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0d1117 0%,#161b22 100%)!important;border-right:1px solid rgba(0,230,118,0.1)!important}
header[data-testid="stHeader"]{background:rgba(10,10,15,0.9)!important;backdrop-filter:blur(20px);border-bottom:1px solid rgba(0,230,118,0.08)}
[data-testid="stMetric"]{background:rgba(13,17,23,0.8)!important;border:1px solid rgba(255,255,255,0.06)!important;border-radius:12px!important;padding:16px!important}
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
.sc{background:rgba(13,17,23,0.85);border:1px solid rgba(255,255,255,0.06);border-radius:14px;padding:18px;backdrop-filter:blur(20px);transition:all 0.3s;margin-bottom:8px}
.sc:hover{border-color:rgba(0,230,118,0.15);box-shadow:0 4px 20px rgba(0,0,0,0.3)}
.sb{border-left:3px solid #00E676}.ss{border-left:3px solid #FF5252}.sn{border-left:3px solid #FFA726}
.jm{font-family:'JetBrains Mono',monospace}
.badge{display:inline-block;padding:4px 14px;border-radius:20px;font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:800}
.bb{background:rgba(0,230,118,0.15);color:#00E676;border:1px solid rgba(0,230,118,0.3)}
.bsb{background:rgba(0,230,118,0.25);color:#00E676;border:1px solid rgba(0,230,118,0.5);box-shadow:0 0 10px rgba(0,230,118,0.2)}
.bs{background:rgba(255,82,82,0.15);color:#FF5252;border:1px solid rgba(255,82,82,0.3)}
.bss{background:rgba(213,0,0,0.25);color:#FF5252;border:1px solid rgba(213,0,0,0.5)}
.bn{background:rgba(255,167,38,0.15);color:#FFA726;border:1px solid rgba(255,167,38,0.3)}
.ig{display:grid;grid-template-columns:repeat(auto-fill,minmax(85px,1fr));gap:5px;margin-top:8px}
.ic{text-align:center;padding:5px 3px;border-radius:7px;font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:700}
.ib{background:rgba(0,230,118,0.1);color:#00E676;border:1px solid rgba(0,230,118,0.2)}
.is{background:rgba(255,82,82,0.1);color:#FF5252;border:1px solid rgba(255,82,82,0.2)}
.inn{background:rgba(255,255,255,0.03);color:#888;border:1px solid rgba(255,255,255,0.06)}
.sbr{display:flex;height:6px;border-radius:3px;overflow:hidden;margin:8px 0;gap:2px}
.sbb{background:linear-gradient(90deg,#00E676,#69F0AE);border-radius:3px 0 0 3px}
.sbn{background:#444}
.sbs{background:linear-gradient(90deg,#FF5252,#D50000);border-radius:0 3px 3px 0}
.tg{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}
.tc{text-align:center;padding:8px;border-radius:8px;font-family:'JetBrains Mono',monospace}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
.sd{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;animation:pulse 2s infinite}
.sl{background:#00E676;box-shadow:0 0 8px #00E676}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
</style>""", unsafe_allow_html=True)

# ── VERİ ÇEKME ──
@st.cache_data(ttl=55)
def get_coingecko_data():
    """CoinGecko Market Data — ABD dahil her yerden çalışır"""
    ids = ",".join(COINS.keys())
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency":"usd","ids":ids,"order":"market_cap_desc",
                    "per_page":50,"page":1,"sparkline":True,
                    "price_change_percentage":"1h,24h,7d"}, timeout=20)
        if r.status_code == 200:
            return r.json(), "CoinGecko"
    except: pass
    return None, "Hata"

@st.cache_data(ttl=55)
def get_ohlc(coin_id, days=14):
    """CoinGecko OHLC verisi — teknik analiz için"""
    try:
        r = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
            params={"vs_currency":"usd","days":days}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                df = pd.DataFrame(data, columns=["timestamp","open","high","low","close"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df["volume"] = 1  # OHLC endpoint'te hacim yok, dummy
                return df
    except: pass
    return None

@st.cache_data(ttl=300)
def get_fear_greed():
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        d = r.json()
        if d and "data" in d and len(d["data"]) > 0: return d["data"][0]
    except: pass
    return None

# ── TEKNİK ANALİZ ──
def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)

def calc_ema(data, period):
    if len(data) < period: return data[-1] if len(data) > 0 else 0
    k = 2 / (period + 1)
    ema = np.mean(data[:period])
    for val in data[period:]:
        ema = val * k + ema * (1 - k)
    return ema

def calc_macd(closes):
    if len(closes) < 26: return 0, 0, 0
    e12 = calc_ema(closes, 12)
    e26 = calc_ema(closes, 26)
    macd_line = e12 - e26
    # Basitleştirilmiş sinyal
    hist_vals = []
    k12, k26 = 2/13, 2/27
    em12 = np.mean(closes[:12])
    em26 = np.mean(closes[:26])
    for i in range(26, len(closes)):
        em12 = closes[i] * k12 + em12 * (1 - k12)
        em26 = closes[i] * k26 + em26 * (1 - k26)
        hist_vals.append(em12 - em26)
    if len(hist_vals) >= 9:
        signal = calc_ema(np.array(hist_vals), 9)
    else:
        signal = 0
    histogram = macd_line - signal
    return macd_line, signal, histogram

def calc_bb(closes, period=20):
    if len(closes) < period: return 0, 0, 0, 0
    sl = closes[-period:]
    mean = np.mean(sl)
    std = np.std(sl)
    return mean + 2*std, mean, mean - 2*std, (4*std/mean*100) if mean > 0 else 0

def calc_stoch_rsi(closes, period=14):
    if len(closes) < period * 2: return 50, 50
    rsi_vals = []
    for i in range(period+1, len(closes)+1):
        rsi_vals.append(calc_rsi(closes[:i], period))
    if len(rsi_vals) < period: return 50, 50
    recent = rsi_vals[-period:]
    mn, mx = min(recent), max(recent)
    if mx == mn: return 50, 50
    k = ((recent[-1] - mn) / (mx - mn)) * 100
    d = np.mean(rsi_vals[-3:]) if len(rsi_vals) >= 3 else k
    return k, d

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1: return 0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    if len(trs) < period: return np.mean(trs) if trs else 0
    return np.mean(trs[-period:])

def analyze(coin_data, ohlc_df):
    """Tam teknik analiz"""
    price = coin_data["current_price"]
    result = {"price": price, "id": coin_data["id"]}
    info = COINS.get(coin_data["id"], {"sym": coin_data["symbol"].upper(), "name": coin_data["name"]})
    result["sym"] = info["sym"]
    result["name"] = info["name"]
    result["market_cap"] = coin_data.get("market_cap", 0)
    result["volume"] = coin_data.get("total_volume", 0)
    result["change_1h"] = coin_data.get("price_change_percentage_1h_in_currency", 0) or 0
    result["change_24h"] = coin_data.get("price_change_percentage_24h", 0) or 0
    result["change_7d"] = coin_data.get("price_change_percentage_7d_in_currency", 0) or 0
    result["high_24h"] = coin_data.get("high_24h", price)
    result["low_24h"] = coin_data.get("low_24h", price)
    result["sparkline"] = coin_data.get("sparkline_in_7d", {}).get("price", [])

    signals = []

    if ohlc_df is not None and len(ohlc_df) >= 30:
        closes = ohlc_df["close"].values
        highs = ohlc_df["high"].values
        lows = ohlc_df["low"].values
    elif result["sparkline"] and len(result["sparkline"]) >= 30:
        closes = np.array(result["sparkline"])
        highs = closes * 1.002
        lows = closes * 0.998
    else:
        closes = np.array([price])
        highs = lows = closes

    # 1. RSI
    rsi = calc_rsi(closes)
    result["rsi"] = rsi
    if rsi < 30: signals.append({"n":"RSI","d":"AL","v":f"{rsi:.1f}","w":2})
    elif rsi < 40: signals.append({"n":"RSI","d":"AL","v":f"{rsi:.1f}","w":1})
    elif rsi > 70: signals.append({"n":"RSI","d":"SAT","v":f"{rsi:.1f}","w":2})
    elif rsi > 60: signals.append({"n":"RSI","d":"SAT","v":f"{rsi:.1f}","w":1})
    else: signals.append({"n":"RSI","d":"NÖTR","v":f"{rsi:.1f}","w":0})

    # 2. MACD
    ml, ms, mh = calc_macd(closes)
    result["macd_h"] = mh
    if mh > 0 and ml > ms: signals.append({"n":"MACD","d":"AL","v":f"{mh:.4f}","w":2})
    elif mh < 0 and ml < ms: signals.append({"n":"MACD","d":"SAT","v":f"{mh:.4f}","w":2})
    else: signals.append({"n":"MACD","d":"NÖTR","v":f"{mh:.4f}","w":0})

    # 3. Bollinger Bands
    bu, bm, bl, bw = calc_bb(closes)
    result["bb_w"] = bw
    result["bb_sq"] = bw < 3 and bw > 0
    if price <= bl and bl > 0: signals.append({"n":"BB","d":"AL","v":"Alt Band","w":2})
    elif price >= bu and bu > 0: signals.append({"n":"BB","d":"SAT","v":"Üst Band","w":2})
    else: signals.append({"n":"BB","d":"NÖTR","v":"Orta","w":0})

    # 4. EMA Cross
    ema9 = calc_ema(closes, 9)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, min(50, len(closes)))
    result["ema9"] = ema9; result["ema21"] = ema21; result["ema50"] = ema50
    if ema9 > ema21 > ema50: signals.append({"n":"EMA","d":"AL","v":"9>21>50","w":2})
    elif ema9 < ema21 < ema50: signals.append({"n":"EMA","d":"SAT","v":"9<21<50","w":2})
    elif ema9 > ema21: signals.append({"n":"EMA","d":"AL","v":"9>21","w":1})
    else: signals.append({"n":"EMA","d":"SAT","v":"Karışık","w":1})

    # 5. Stochastic RSI
    sk, sd = calc_stoch_rsi(closes)
    result["stoch_k"] = sk
    if sk < 20 and sk > sd: signals.append({"n":"StochRSI","d":"AL","v":f"{sk:.0f}","w":2})
    elif sk > 80 and sk < sd: signals.append({"n":"StochRSI","d":"SAT","v":f"{sk:.0f}","w":2})
    else: signals.append({"n":"StochRSI","d":"NÖTR","v":f"{sk:.0f}","w":0})

    # 6. SMA 200
    sma = np.mean(closes[-min(200, len(closes)):])
    result["sma200"] = sma
    if price > sma: signals.append({"n":"SMA200","d":"AL","v":f"${sma:.2f}","w":1})
    else: signals.append({"n":"SMA200","d":"SAT","v":f"${sma:.2f}","w":1})

    # 7. Momentum (1h/24h/7d)
    if result["change_24h"] > 3: signals.append({"n":"24s","d":"AL","v":f"{result['change_24h']:.1f}%","w":1})
    elif result["change_24h"] < -3: signals.append({"n":"24s","d":"SAT","v":f"{result['change_24h']:.1f}%","w":1})
    else: signals.append({"n":"24s","d":"NÖTR","v":f"{result['change_24h']:.1f}%","w":0})

    # 8. Volume/MCap Ratio
    vm = (result["volume"] / result["market_cap"] * 100) if result["market_cap"] > 0 else 0
    result["vol_mcap"] = vm
    if vm > 10: signals.append({"n":"Hacim","d":"AL","v":f"{vm:.1f}%","w":1})
    elif vm < 3: signals.append({"n":"Hacim","d":"SAT","v":f"{vm:.1f}%","w":1})
    else: signals.append({"n":"Hacim","d":"NÖTR","v":f"{vm:.1f}%","w":0})

    # 9. ATR
    atr = calc_atr(highs, lows, closes)
    result["atr"] = atr

    # 10. 24h Range Position
    h24 = result["high_24h"]; l24 = result["low_24h"]
    if h24 and l24 and h24 > l24:
        rng_pos = ((price - l24) / (h24 - l24)) * 100
        if rng_pos < 20: signals.append({"n":"Aralık","d":"AL","v":f"{rng_pos:.0f}%","w":1})
        elif rng_pos > 80: signals.append({"n":"Aralık","d":"SAT","v":f"{rng_pos:.0f}%","w":1})
        else: signals.append({"n":"Aralık","d":"NÖTR","v":f"{rng_pos:.0f}%","w":0})

    # SKOR
    sr = sum(s["w"]*(1 if s["d"]=="AL" else -1 if s["d"]=="SAT" else 0) for s in signals)
    mx = sum(s["w"] for s in signals) or 1
    nm = ((sr+mx)/(2*mx))*100
    result["score"] = nm
    result["signals"] = signals

    if nm >= 75: result["dir"]="GÜÇLÜ AL"; result["str"]="vb"
    elif nm >= 60: result["dir"]="AL"; result["str"]="b"
    elif nm >= 45: result["dir"]="NÖTR"; result["str"]="n"
    elif nm >= 30: result["dir"]="SAT"; result["str"]="s"
    else: result["dir"]="GÜÇLÜ SAT"; result["str"]="vs"

    # TP/SL
    if atr > 0:
        result["tp1"]=price+atr*1.5; result["tp2"]=price+atr*2.5; result["tp3"]=price+atr*4; result["sl"]=price-atr*1.2
    else:
        pct = price * 0.02
        result["tp1"]=price+pct*1.5; result["tp2"]=price+pct*2.5; result["tp3"]=price+pct*4; result["sl"]=price-pct*1.2

    return result

# ── YARDIMCI FONKSİYONLAR ──
def dcol(s):return{"vb":"#00E676","b":"#66BB6A","n":"#FFA726","s":"#EF5350","vs":"#D50000"}.get(s,"#888")
def bcls(s):return{"vb":"bsb","b":"bb","n":"bn","s":"bs","vs":"bss"}.get(s,"bn")
def ccls(s):
    if s in("vb","b"):return "sb"
    if s in("vs","s"):return "ss"
    return "sn"

def fp(p):
    if not p: return "—"
    if p>=1000:return f"${p:,.2f}"
    elif p>=1:return f"${p:.4f}"
    elif p>=0.001:return f"${p:.6f}"
    return f"${p:.8f}"

def fv(v):
    if not v: return "—"
    if v>=1e9:return f"${v/1e9:.2f}B"
    elif v>=1e6:return f"${v/1e6:.2f}M"
    return f"${v/1e3:.1f}K"

def sig_bar(sigs):
    b=sum(1 for s in sigs if s["d"]=="AL");se=sum(1 for s in sigs if s["d"]=="SAT");n=sum(1 for s in sigs if s["d"]=="NÖTR")
    return f'<div class="sbr"><div class="sbb" style="flex:{b};min-width:{"4px" if b else "0"}"></div><div class="sbn" style="flex:{n};min-width:{"4px" if n else "0"}"></div><div class="sbs" style="flex:{se};min-width:{"4px" if se else "0"}"></div></div><div style="display:flex;justify-content:space-between;font-size:10px;color:#555" class="jm"><span style="color:#00E676">{b} AL</span><span>{n} NÖTR</span><span style="color:#FF5252">{se} SAT</span></div>'

def chips(sigs):
    h=""
    for s in sigs:
        c="ib" if s["d"]=="AL" else "is" if s["d"]=="SAT" else "inn"
        h+=f'<div class="ic {c}">{s["n"]}<br><b>{s["d"]}</b></div>'
    return f'<div class="ig">{h}</div>'

def tp_html(c):
    p=c["price"]
    items=[("TP1",c["tp1"],"#00E676","rgba(0,230,118,0.08)","rgba(0,230,118,0.2)"),("TP2",c["tp2"],"#69F0AE","rgba(105,240,174,0.08)","rgba(105,240,174,0.2)"),("TP3",c["tp3"],"#B2FF59","rgba(178,255,89,0.08)","rgba(178,255,89,0.2)"),("SL",c["sl"],"#FF5252","rgba(255,82,82,0.08)","rgba(255,82,82,0.2)")]
    h=""
    for lb,val,col,bg,bd in items:
        pct=((val-p)/p)*100 if p else 0
        h+=f'<div class="tc" style="background:{bg};border:1px solid {bd}"><div style="font-size:9px;color:#666;letter-spacing:1px">{lb}</div><div style="font-size:13px;font-weight:800;color:{col};margin-top:2px">{fp(val)}</div><div style="font-size:9px;color:#555;margin-top:1px">{pct:+.2f}%</div></div>'
    return f'<div class="tg">{h}</div>'

def card(c):
    col=dcol(c["str"]);bg=bcls(c["str"]);cc=ccls(c["str"])
    ch=c["change_24h"];ci="▲" if ch>=0 else "▼";ccl="#00E676" if ch>=0 else "#FF5252"
    return f'''<div class="sc {cc}"><div style="display:flex;justify-content:space-between;align-items:flex-start"><div style="display:flex;align-items:center;gap:12px"><div style="width:44px;height:44px;border-radius:12px;background:linear-gradient(135deg,{col}30,{col}10);display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:900;color:{col};border:2px solid {col}60" class="jm">{c["sym"][:3]}</div><div><div class="jm" style="font-weight:900;font-size:18px;color:#e6edf3">{c["sym"]}/USD</div><div class="jm" style="font-size:11px;color:#555">{c["name"]}</div></div></div><div style="text-align:right"><div class="jm" style="font-weight:900;font-size:22px;color:#e6edf3">{fp(c["price"])}</div><div class="jm" style="font-weight:700;font-size:14px;color:{ccl}">{ci} {abs(ch):.2f}%</div></div></div><div style="display:flex;justify-content:space-between;align-items:center;margin:12px 0 8px"><div style="text-align:center;padding:8px"><div class="jm" style="font-weight:900;font-size:36px;color:{col};line-height:1">{c["score"]:.0f}</div><div class="jm" style="font-size:10px;color:#666;letter-spacing:1.5px;margin-top:4px">SİNYAL SKORU</div></div><div><span class="badge {bg}">{c["dir"]}</span></div><div style="text-align:right;font-size:10px;color:#555" class="jm"><div>RSI: <b style="color:{"#00E676" if c["rsi"]<30 else "#FF5252" if c["rsi"]>70 else "#FFA726"}">{c["rsi"]:.1f}</b></div><div>Hacim: <b style="color:#00BCD4">{fv(c["volume"])}</b></div>{"<div style=color:#7C4DFF;font-weight:700>⚡ BB SIKIŞTIRMA</div>" if c.get("bb_sq") else ""}</div></div>{sig_bar(c["signals"])}{chips(c["signals"])}<div class="jm" style="margin-top:10px;font-size:10px;color:#555;letter-spacing:1px;font-weight:700">TP/SL SEVİYELERİ (ATR)</div>{tp_html(c)}</div>'''

# ═════ ANA UYGULAMA ═════
def main():
    st.markdown('<div style="display:flex;align-items:center;gap:16px;padding:8px 0 20px"><div style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#00E676,#00BCD4,#7C4DFF);display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;color:#000;box-shadow:0 0 30px rgba(0,230,118,0.3)" class="jm">α</div><div><div class="jm" style="font-weight:900;font-size:24px;background:linear-gradient(90deg,#00E676,#00BCD4,#7C4DFF);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:1px;line-height:1.2">ALFA NEXUS PRO v8.0</div><div class="jm" style="font-size:10px;color:#555;letter-spacing:3px;text-transform:uppercase">Bulut Tabanlı Algoritmik Ticaret Paneli</div></div></div>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown('<div style="text-align:center;padding:12px 0"><div class="jm" style="font-weight:900;font-size:18px;background:linear-gradient(90deg,#00E676,#00BCD4);-webkit-background-clip:text;-webkit-text-fill-color:transparent">⚙️ KONTROL PANELİ</div></div>', unsafe_allow_html=True)
        sf=st.selectbox("🎯 Sinyal Filtresi",["🔵 Tümü","🟢 Sadece AL","🔴 Sadece SAT","⚡ Güçlü Sinyaller","🔥 BB Sıkışma"])
        st.markdown("---")
        so=st.selectbox("📊 Sıralama",["Skor (Yüksek→Düşük)","Skor (Düşük→Yüksek)","Değişim (Yüksek)","Değişim (Düşük)","RSI (Düşük)","Piyasa Değeri"])
        st.markdown("---")
        cs=st.text_input("🔍 Coin Ara","",placeholder="BTC, ETH, SOL...")
        st.markdown("---")
        if st.button("🔄 Verileri Yenile",use_container_width=True):st.cache_data.clear();st.rerun()

    pb=st.progress(0);stx=st.empty()
    stx.markdown('<div class="jm" style="font-size:11px;color:#555"><span class="sd" style="background:#FFA726;box-shadow:0 0 8px #FFA726"></span>CoinGecko API bağlanıyor...</div>', unsafe_allow_html=True)

    data, src = get_coingecko_data()
    fng = get_fear_greed()

    if not data:
        st.error("⚠️ CoinGecko API'ye bağlanılamadı. Birkaç dakika sonra tekrar deneyin.")
        return

    stx.markdown(f'<div class="jm" style="font-size:11px;color:#555"><span class="sd sl"></span><b style="color:#00E676">BAĞLANTI OK</b> • <span style="background:rgba(0,230,118,0.1);color:#00E676;border:1px solid rgba(0,230,118,0.2);padding:2px 8px;border-radius:6px;font-size:10px">{src}</span></div>', unsafe_allow_html=True)

    results = []
    for i, coin in enumerate(data):
        if coin["id"] in COINS:
            ohlc = get_ohlc(coin["id"], days=14)
            r = analyze(coin, ohlc)
            if r: results.append(r)
        pb.progress(min((i+1)/len(data), 1.0))
        # Rate limit: CoinGecko ücretsiz plan ~10-30 req/dk
        if i % 5 == 4: time.sleep(1.2)

    pb.empty(); stx.empty()

    if not results: st.error("Veri yok."); return

    # FİLTRE
    fl = results.copy()
    if cs: fl=[c for c in fl if cs.upper() in c["sym"]]
    if "AL" in sf: fl=[c for c in fl if c["score"]>=60]
    elif "SAT" in sf: fl=[c for c in fl if c["score"]<40]
    elif "Güçlü" in sf: fl=[c for c in fl if c["score"]>=75 or c["score"]<25]
    elif "Sıkışma" in sf: fl=[c for c in fl if c.get("bb_sq")]

    if "Yüksek→Düşük" in so: fl.sort(key=lambda x:x["score"],reverse=True)
    elif "Düşük→Yüksek" in so: fl.sort(key=lambda x:x["score"])
    elif "Değişim (Yüksek)" in so: fl.sort(key=lambda x:x["change_24h"],reverse=True)
    elif "Değişim (Düşük)" in so: fl.sort(key=lambda x:x["change_24h"])
    elif "RSI" in so: fl.sort(key=lambda x:x["rsi"])
    elif "Piyasa" in so: fl.sort(key=lambda x:x.get("market_cap",0),reverse=True)

    # İSTATİSTİK
    bc=sum(1 for c in results if c["score"]>=60);sc=sum(1 for c in results if c["score"]<40)
    nc=sum(1 for c in results if 40<=c["score"]<60);sq=sum(1 for c in results if c.get("bb_sq"))
    av=np.mean([c["score"] for c in results])

    cn=7 if fng else 6; cols=st.columns(cn)
    with cols[0]: st.metric("🟢 AL SİNYALİ",bc,delta=f"{(bc/len(results)*100):.0f}%")
    with cols[1]: st.metric("🔴 SAT SİNYALİ",sc,delta=f"{(sc/len(results)*100):.0f}%",delta_color="inverse")
    with cols[2]: st.metric("🟡 NÖTR",nc)
    with cols[3]: st.metric("⚡ BB SIKIŞTIRMA",sq)
    with cols[4]:
        btc=next((c for c in results if c["sym"]=="BTC"),None)
        if btc: st.metric("₿ BTC",f"${btc['price']:,.0f}",delta=f"{btc['change_24h']:+.2f}%")
    with cols[5]: st.metric("📊 ORT. SKOR",f"{av:.0f}/100")
    if fng:
        with cols[6]: st.metric("😱 KORKU/AÇGÖZLÜLÜK",fng.get("value","?"),delta=fng.get("value_classification",""))

    st.markdown("---")
    now=datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px"><div class="jm" style="font-size:11px;color:#555"><span class="sd sl"></span><b style="color:#00E676">CANLI</b> • {len(fl)} coin • CoinGecko API</div><div class="jm" style="font-size:10px;color:#444">Son: {now} • Oto: 60sn</div></div>', unsafe_allow_html=True)

    t1,t2,t3=st.tabs(["📡 SİNYAL KARTLARI","📋 TABLO","📈 DETAY"])

    with t1:
        if not fl: st.warning("Sonuç yok.")
        else:
            c1,c2=st.columns(2)
            for i,coin in enumerate(fl):
                if i%2==0:
                    with c1: st.markdown(card(coin), unsafe_allow_html=True)
                else:
                    with c2: st.markdown(card(coin), unsafe_allow_html=True)

    with t2:
        td=[]
        for c in fl:
            bs=sum(1 for s in c["signals"] if s["d"]=="AL");ss=sum(1 for s in c["signals"] if s["d"]=="SAT")
            td.append({"Coin":c["sym"],"Fiyat":fp(c["price"]),"24s":f"{c['change_24h']:+.2f}%","7g":f"{c['change_7d']:+.2f}%","RSI":f"{c['rsi']:.1f}","MACD":"▲" if c["macd_h"]>0 else "▼","Skor":f"{c['score']:.0f}","Yön":c["dir"],"AL":bs,"SAT":ss,"Sıkışma":"⚡" if c.get("bb_sq") else "","TP1":fp(c["tp1"]),"SL":fp(c["sl"])})
        st.dataframe(pd.DataFrame(td),use_container_width=True,height=min(len(td)*42+60,800),hide_index=True)

    with t3:
        if fl:
            sel=st.selectbox("Coin Seçin",[f"{c['sym']} — {c['name']}" for c in fl])
            sym=sel.split(" — ")[0]
            coin=next((c for c in fl if c["sym"]==sym),None)
            if coin:
                col=dcol(coin["str"])
                st.markdown(f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px"><div style="width:60px;height:60px;border-radius:16px;background:linear-gradient(135deg,{col}40,{col}10);display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:900;color:{col};border:2px solid {col}60" class="jm">{coin["sym"][:3]}</div><div><div class="jm" style="font-size:28px;font-weight:900;color:#e6edf3">{coin["sym"]}/USD</div><div style="font-size:14px;color:#555">{coin["name"]}</div></div><div style="margin-left:auto;text-align:right"><div class="jm" style="font-size:32px;font-weight:900;color:{col}">{fp(coin["price"])}</div><span class="badge {bcls(coin["str"])}" style="font-size:14px;padding:6px 20px">{coin["dir"]}</span></div></div>', unsafe_allow_html=True)
                x1,x2,x3=st.columns([1,2,1])
                with x1: st.markdown(f'<div style="text-align:center;padding:20px"><div class="jm" style="font-weight:900;font-size:56px;color:{col};line-height:1">{coin["score"]:.0f}</div><div class="jm" style="font-size:10px;color:#666;letter-spacing:1.5px;margin-top:4px">SKOR / 100</div></div>', unsafe_allow_html=True)
                with x2: st.markdown(f'<div style="padding:10px 0"><div class="jm" style="font-size:10px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:8px">İNDİKATÖRLER</div>{sig_bar(coin["signals"])}<div style="margin-top:12px">{chips(coin["signals"])}</div></div>', unsafe_allow_html=True)
                with x3: st.markdown(f'<div class="jm" style="font-size:11px;padding:10px 0"><div style="color:#555;margin-bottom:8px;font-weight:700">BİLGİ</div><div style="color:#888">RSI: <b style="color:{"#00E676" if coin["rsi"]<30 else "#FF5252" if coin["rsi"]>70 else "#FFA726"}">{coin["rsi"]:.1f}</b></div><div style="color:#888">ATR: <b style="color:#00BCD4">{fp(coin["atr"])}</b></div><div style="color:#888">MCap: <b>{fv(coin["market_cap"])}</b></div><div style="color:#888">1s: <b style="color:{"#00E676" if coin["change_1h"]>=0 else "#FF5252"}">{coin["change_1h"]:+.2f}%</b></div><div style="color:#888">7g: <b style="color:{"#00E676" if coin["change_7d"]>=0 else "#FF5252"}">{coin["change_7d"]:+.2f}%</b></div>{"<div style=color:#7C4DFF;font-weight:700>⚡ BB SIKIŞTIRMA</div>" if coin.get("bb_sq") else ""}</div>', unsafe_allow_html=True)
                st.markdown("---")
                st.markdown(f'<div class="jm" style="font-size:11px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:10px">🎯 TP/SL SEVİYELERİ</div>{tp_html(coin)}', unsafe_allow_html=True)

    st.markdown('<div style="text-align:center;font-size:10px;color:#333;padding:20px 0 10px;font-family:\'JetBrains Mono\',monospace;border-top:1px solid rgba(255,255,255,0.03);margin-top:30px"><span style="letter-spacing:2px">ALFA NEXUS PRO v8.0</span> • CoinGecko API • 10 İndikatör + ATR TP/SL<br>⚠️ Bu panel yatırım tavsiyesi değildir.</div>', unsafe_allow_html=True)

if __name__=="__main__": main()
