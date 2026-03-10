import streamlit as st
import requests
import pandas as pd
import numpy as np
import ta
import time
import json
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# ═══════════════════════════════════════════════════════════════════════════
#  ALFA NEXUS PRO v8.0 — BULUT TABANLI ALGORİTMİK TİCARET PANELİ
#  Cloud-Based Algorithmic Trading Dashboard
#  Streamlit + Binance API | Gerçek Zamanlı Sinyal Sistemi
#  GitHub: gokaydonmez39-jpg/kripto-radar
# ═══════════════════════════════════════════════════════════════════════════

# ─── SAYFA AYARLARI ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="ALFA NEXUS PRO v8.0 | Kripto Radar",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── OTOMATİK YENİLEME (60 saniye) ──────────────────────────────────────
st_autorefresh(interval=60000, limit=None, key="pro_autorefresh")

# ─── TOP COİNLER (Binance Piyasa Değeri En Yüksek) ──────────────────────
TOP_COINS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT", "SHIBUSDT",
    "LTCUSDT", "UNIUSDT", "ATOMUSDT", "ETCUSDT", "NEARUSDT", "APTUSDT",
    "FILUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT", "SEIUSDT",
    "TIAUSDT", "JUPUSDT", "STXUSDT", "RENDERUSDT", "FETUSDT", "WIFUSDT",
    "PEPEUSDT", "ONDOUSDT", "TAOUSDT", "RUNEUSDT", "ENAUSDT", "AAVEUSDT",
    "ICPUSDT", "XLMUSDT", "HBARUSDT", "TRXUSDT"
]

TIMEFRAMES = {
    "1 Dakika": "1m",
    "5 Dakika": "5m",
    "15 Dakika": "15m",
    "1 Saat": "1h",
    "4 Saat": "4h",
    "1 Gün": "1d",
}

# ─── COIN İSİMLERİ ──────────────────────────────────────────────────────
COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "BNB": "BNB", "SOL": "Solana",
    "XRP": "Ripple", "DOGE": "Dogecoin", "ADA": "Cardano", "AVAX": "Avalanche",
    "DOT": "Polkadot", "LINK": "Chainlink", "MATIC": "Polygon", "SHIB": "Shiba Inu",
    "LTC": "Litecoin", "UNI": "Uniswap", "ATOM": "Cosmos", "ETC": "Ethereum Classic",
    "NEAR": "NEAR Protocol", "APT": "Aptos", "FIL": "Filecoin", "ARB": "Arbitrum",
    "OP": "Optimism", "INJ": "Injective", "SUI": "Sui", "SEI": "Sei",
    "TIA": "Celestia", "JUP": "Jupiter", "STX": "Stacks", "RENDER": "Render",
    "FET": "Fetch.ai", "WIF": "dogwifhat", "PEPE": "Pepe", "ONDO": "Ondo Finance",
    "TAO": "Bittensor", "RUNE": "THORChain", "ENA": "Ethena", "AAVE": "Aave",
    "ICP": "Internet Computer", "XLM": "Stellar", "HBAR": "Hedera", "TRX": "TRON"
}


# ═══════════════════════════════════════════════════════════════════════════
#  CSS TASARIM — ULTRA PROFESYONEL KARANLIK TEMA
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* ── GENEL TEMA ── */
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800;900&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

    .stApp {
        background: linear-gradient(135deg, #0a0a0f 0%, #0d1117 30%, #0a0e1a 70%, #080b12 100%);
        font-family: 'Inter', sans-serif;
    }

    /* Grid overlay */
    .stApp::before {
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,230,118,0.02) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,230,118,0.02) 1px, transparent 1px);
        background-size: 80px 80px;
        pointer-events: none;
        z-index: 0;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%) !important;
        border-right: 1px solid rgba(0,230,118,0.1) !important;
    }

    /* Header gizle */
    header[data-testid="stHeader"] {
        background: rgba(10,10,15,0.9) !important;
        backdrop-filter: blur(20px);
        border-bottom: 1px solid rgba(0,230,118,0.08);
    }

    /* Metrik kartları */
    [data-testid="stMetric"] {
        background: rgba(13,17,23,0.8) !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 12px !important;
        padding: 16px !important;
        backdrop-filter: blur(20px);
        transition: all 0.3s ease;
    }
    [data-testid="stMetric"]:hover {
        border-color: rgba(0,230,118,0.2) !important;
        box-shadow: 0 0 20px rgba(0,230,118,0.05);
    }
    [data-testid="stMetricLabel"] {
        color: #8b949e !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 900 !important;
        font-size: 28px !important;
    }
    [data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-weight: 700 !important;
    }

    /* Tab stilleri */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background: rgba(13,17,23,0.6);
        border-radius: 12px;
        padding: 4px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px !important;
        color: #8b949e !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.5px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #00E676, #00BCD4) !important;
        color: #000 !important;
        font-weight: 800 !important;
    }

    /* DataFrame / Tablo */
    [data-testid="stDataFrame"] {
        border-radius: 12px !important;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.06) !important;
    }
    .stDataFrame table {
        font-family: 'JetBrains Mono', monospace !important;
    }
    .stDataFrame thead th {
        background: rgba(13,17,23,0.95) !important;
        color: #8b949e !important;
        font-size: 10px !important;
        font-weight: 700 !important;
        letter-spacing: 1.5px !important;
        text-transform: uppercase !important;
        border-bottom: 1px solid rgba(0,230,118,0.15) !important;
        padding: 12px 8px !important;
    }
    .stDataFrame tbody td {
        background: rgba(13,17,23,0.6) !important;
        color: #e6edf3 !important;
        font-size: 12px !important;
        border-bottom: 1px solid rgba(255,255,255,0.03) !important;
        padding: 10px 8px !important;
    }
    .stDataFrame tbody tr:hover td {
        background: rgba(0,230,118,0.05) !important;
    }

    /* Selectbox / Input */
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stMultiSelect"] > div > div {
        background: rgba(13,17,23,0.8) !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 8px !important;
        color: #e6edf3 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Expander */
    [data-testid="stExpander"] {
        background: rgba(13,17,23,0.6) !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 12px !important;
    }

    /* Butonlar */
    .stButton > button {
        background: linear-gradient(135deg, #00E676, #00BCD4) !important;
        color: #000 !important;
        font-weight: 800 !important;
        border: none !important;
        border-radius: 8px !important;
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.5px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        box-shadow: 0 0 20px rgba(0,230,118,0.3) !important;
        transform: translateY(-1px);
    }

    /* Progress bar */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #00E676, #00BCD4, #7C4DFF) !important;
        border-radius: 4px;
    }

    /* Divider */
    hr { border-color: rgba(255,255,255,0.05) !important; }

    /* Özel kartlar */
    .signal-card {
        background: rgba(13,17,23,0.85);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 14px;
        padding: 18px;
        backdrop-filter: blur(20px);
        transition: all 0.3s ease;
        margin-bottom: 8px;
    }
    .signal-card:hover {
        border-color: rgba(0,230,118,0.15);
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    .signal-card-buy { border-left: 3px solid #00E676; }
    .signal-card-sell { border-left: 3px solid #FF5252; }
    .signal-card-neutral { border-left: 3px solid #FFA726; }

    .coin-header {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 900;
        font-size: 18px;
        color: #e6edf3;
        margin-bottom: 4px;
    }
    .coin-sub {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        color: #555;
        letter-spacing: 1px;
    }
    .price-main {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 900;
        font-size: 22px;
    }
    .change-positive { color: #00E676; }
    .change-negative { color: #FF5252; }

    .badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.5px;
    }
    .badge-buy { background: rgba(0,230,118,0.15); color: #00E676; border: 1px solid rgba(0,230,118,0.3); }
    .badge-strong-buy { background: rgba(0,230,118,0.25); color: #00E676; border: 1px solid rgba(0,230,118,0.5); box-shadow: 0 0 10px rgba(0,230,118,0.2); }
    .badge-sell { background: rgba(255,82,82,0.15); color: #FF5252; border: 1px solid rgba(255,82,82,0.3); }
    .badge-strong-sell { background: rgba(213,0,0,0.25); color: #FF5252; border: 1px solid rgba(213,0,0,0.5); box-shadow: 0 0 10px rgba(255,82,82,0.2); }
    .badge-neutral { background: rgba(255,167,38,0.15); color: #FFA726; border: 1px solid rgba(255,167,38,0.3); }

    .indicator-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
        gap: 6px;
        margin-top: 8px;
    }
    .ind-chip {
        text-align: center;
        padding: 6px 4px;
        border-radius: 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        font-weight: 700;
    }
    .ind-buy { background: rgba(0,230,118,0.1); color: #00E676; border: 1px solid rgba(0,230,118,0.2); }
    .ind-sell { background: rgba(255,82,82,0.1); color: #FF5252; border: 1px solid rgba(255,82,82,0.2); }
    .ind-neutral { background: rgba(255,255,255,0.03); color: #888; border: 1px solid rgba(255,255,255,0.06); }

    .signal-bar-container {
        display: flex;
        height: 6px;
        border-radius: 3px;
        overflow: hidden;
        margin: 8px 0;
        gap: 2px;
    }
    .signal-bar-buy { background: linear-gradient(90deg, #00E676, #69F0AE); border-radius: 3px 0 0 3px; }
    .signal-bar-neutral { background: #444; }
    .signal-bar-sell { background: linear-gradient(90deg, #FF5252, #D50000); border-radius: 0 3px 3px 0; }

    .tp-sl-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 6px;
        margin-top: 8px;
    }
    .tp-card {
        text-align: center;
        padding: 8px;
        border-radius: 8px;
        font-family: 'JetBrains Mono', monospace;
    }
    .tp-card-label { font-size: 9px; color: #666; letter-spacing: 1px; }
    .tp-card-value { font-size: 13px; font-weight: 800; margin-top: 2px; }
    .tp-card-pct { font-size: 9px; color: #555; margin-top: 1px; }

    .score-gauge {
        text-align: center;
        padding: 8px;
    }
    .score-number {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 900;
        font-size: 36px;
        line-height: 1;
    }
    .score-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        color: #666;
        letter-spacing: 1.5px;
        margin-top: 4px;
    }

    /* Logo header */
    .main-header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 8px 0 20px 0;
    }
    .logo-box {
        width: 52px; height: 52px;
        border-radius: 14px;
        background: linear-gradient(135deg, #00E676 0%, #00BCD4 50%, #7C4DFF 100%);
        display: flex; align-items: center; justify-content: center;
        font-size: 26px; font-weight: 900; color: #000;
        box-shadow: 0 0 30px rgba(0,230,118,0.3);
        font-family: 'JetBrains Mono', monospace;
    }
    .title-main {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 900;
        font-size: 24px;
        background: linear-gradient(90deg, #00E676, #00BCD4, #7C4DFF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: 1px;
        line-height: 1.2;
    }
    .title-sub {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px;
        color: #555;
        letter-spacing: 3px;
        text-transform: uppercase;
    }

    .status-dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
        animation: pulse 2s infinite;
    }
    .status-live { background: #00E676; box-shadow: 0 0 8px #00E676; }
    .status-loading { background: #FFA726; box-shadow: 0 0 8px #FFA726; }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }

    /* Disclaimer */
    .disclaimer {
        text-align: center;
        font-size: 10px;
        color: #333;
        padding: 20px 0 10px 0;
        font-family: 'JetBrains Mono', monospace;
        letter-spacing: 0.5px;
        border-top: 1px solid rgba(255,255,255,0.03);
        margin-top: 30px;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
    ::-webkit-scrollbar-track { background: transparent; }

    /* Fear & Greed Gauge */
    .fng-gauge {
        text-align: center;
        padding: 12px;
        background: rgba(13,17,23,0.6);
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.06);
    }
    .fng-value {
        font-family: 'JetBrains Mono', monospace;
        font-weight: 900;
        font-size: 40px;
        line-height: 1;
    }
    .fng-label {
        font-size: 10px;
        color: #666;
        letter-spacing: 1.5px;
        font-family: 'JetBrains Mono', monospace;
        margin-top: 6px;
    }
    .fng-text {
        font-size: 12px;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
#  VERİ ÇEKME MOTORU
# ═══════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=55)
def get_market_data():
    """Binance 24hr ticker verisi"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        resp = requests.get(url, timeout=15)
        data = resp.json()
        market = {}
        for item in data:
            if item["symbol"] in TOP_COINS:
                market[item["symbol"]] = {
                    "price": float(item["lastPrice"]),
                    "change": float(item["priceChangePercent"]),
                    "high": float(item["highPrice"]),
                    "low": float(item["lowPrice"]),
                    "volume": float(item["volume"]),
                    "quoteVolume": float(item["quoteVolume"]),
                }
        return market
    except Exception as e:
        st.error(f"Piyasa verisi çekilemedi: {e}")
        return {}


@st.cache_data(ttl=55)
def get_klines(symbol, interval="1h", limit=200):
    """Binance kline (mum) verisi"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url, timeout=15)
        data = resp.json()
        if not isinstance(data, list):
            return None
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = df[col].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        return df
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_fear_greed():
    """Kripto Korku & Açgözlülük Endeksi"""
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10)
        data = resp.json()
        if data and "data" in data and len(data["data"]) > 0:
            return data["data"][0]
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  TEKNİK ANALİZ MOTORU
# ═══════════════════════════════════════════════════════════════════════════

def analyze_coin(df, symbol):
    """Tam teknik analiz — 10 indikatör + mum formasyonu"""
    if df is None or len(df) < 50:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]
    price = close.iloc[-1]

    result = {"symbol": symbol, "name": symbol.replace("USDT", ""), "price": price}
    signals = []

    # ── 1. RSI ──
    rsi_indicator = ta.momentum.RSIIndicator(close, window=14)
    rsi = rsi_indicator.rsi().iloc[-1]
    result["rsi"] = rsi
    if rsi < 30:
        signals.append({"name": "RSI", "dir": "AL", "val": f"{rsi:.1f}", "w": 2})
    elif rsi < 40:
        signals.append({"name": "RSI", "dir": "AL", "val": f"{rsi:.1f}", "w": 1})
    elif rsi > 70:
        signals.append({"name": "RSI", "dir": "SAT", "val": f"{rsi:.1f}", "w": 2})
    elif rsi > 60:
        signals.append({"name": "RSI", "dir": "SAT", "val": f"{rsi:.1f}", "w": 1})
    else:
        signals.append({"name": "RSI", "dir": "NÖTR", "val": f"{rsi:.1f}", "w": 0})

    # ── 2. MACD ──
    macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_ind.macd().iloc[-1]
    macd_signal = macd_ind.macd_signal().iloc[-1]
    macd_hist = macd_ind.macd_diff().iloc[-1]
    result["macd_hist"] = macd_hist
    if macd_hist > 0 and macd_line > macd_signal:
        signals.append({"name": "MACD", "dir": "AL", "val": f"{macd_hist:.4f}", "w": 2})
    elif macd_hist < 0 and macd_line < macd_signal:
        signals.append({"name": "MACD", "dir": "SAT", "val": f"{macd_hist:.4f}", "w": 2})
    else:
        signals.append({"name": "MACD", "dir": "NÖTR", "val": f"{macd_hist:.4f}", "w": 0})

    # ── 3. Bollinger Bands ──
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bb_mid = bb.bollinger_mavg().iloc[-1]
    bb_width = ((bb_upper - bb_lower) / bb_mid) * 100 if bb_mid > 0 else 0
    result["bb_width"] = bb_width
    result["bb_squeeze"] = bb_width < 3
    if price <= bb_lower:
        signals.append({"name": "BB", "dir": "AL", "val": "Alt Band", "w": 2})
    elif price >= bb_upper:
        signals.append({"name": "BB", "dir": "SAT", "val": "Üst Band", "w": 2})
    else:
        signals.append({"name": "BB", "dir": "NÖTR", "val": "Orta", "w": 0})

    # ── 4. EMA Cross (9/21/50) ──
    ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator().iloc[-1]
    ema21 = ta.trend.EMAIndicator(close, window=21).ema_indicator().iloc[-1]
    ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().iloc[-1]
    result["ema9"] = ema9
    result["ema21"] = ema21
    result["ema50"] = ema50
    if ema9 > ema21 > ema50:
        signals.append({"name": "EMA", "dir": "AL", "val": "9>21>50", "w": 2})
    elif ema9 < ema21 < ema50:
        signals.append({"name": "EMA", "dir": "SAT", "val": "9<21<50", "w": 2})
    elif ema9 > ema21:
        signals.append({"name": "EMA", "dir": "AL", "val": "9>21", "w": 1})
    else:
        signals.append({"name": "EMA", "dir": "SAT", "val": "Karışık", "w": 1})

    # ── 5. Stochastic RSI ──
    stoch = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
    stoch_k = stoch.stochrsi_k().iloc[-1] * 100
    stoch_d = stoch.stochrsi_d().iloc[-1] * 100
    result["stoch_k"] = stoch_k
    if stoch_k < 20 and stoch_k > stoch_d:
        signals.append({"name": "StochRSI", "dir": "AL", "val": f"{stoch_k:.0f}", "w": 2})
    elif stoch_k > 80 and stoch_k < stoch_d:
        signals.append({"name": "StochRSI", "dir": "SAT", "val": f"{stoch_k:.0f}", "w": 2})
    else:
        signals.append({"name": "StochRSI", "dir": "NÖTR", "val": f"{stoch_k:.0f}", "w": 0})

    # ── 6. VWAP ──
    tp = (high + low + close) / 3
    cum_tpv = (tp * volume).rolling(20).sum()
    cum_vol = volume.rolling(20).sum()
    vwap = (cum_tpv / cum_vol).iloc[-1] if cum_vol.iloc[-1] > 0 else price
    result["vwap"] = vwap
    if price > vwap * 1.005:
        signals.append({"name": "VWAP", "dir": "AL", "val": f"${vwap:.2f}", "w": 1})
    elif price < vwap * 0.995:
        signals.append({"name": "VWAP", "dir": "SAT", "val": f"${vwap:.2f}", "w": 1})
    else:
        signals.append({"name": "VWAP", "dir": "NÖTR", "val": f"${vwap:.2f}", "w": 0})

    # ── 7. OBV Trend ──
    obv_series = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
    obv_now = obv_series.iloc[-1]
    obv_prev = obv_series.iloc[-2] if len(obv_series) > 1 else obv_now
    result["obv_trend"] = "Yükseliş" if obv_now > obv_prev else "Düşüş"
    if obv_now > obv_prev:
        signals.append({"name": "OBV", "dir": "AL", "val": "Yükseliş", "w": 1})
    else:
        signals.append({"name": "OBV", "dir": "SAT", "val": "Düşüş", "w": 1})

    # ── 8. SMA 200 ──
    if len(close) >= 200:
        sma200 = close.rolling(200).mean().iloc[-1]
    else:
        sma200 = close.rolling(len(close)).mean().iloc[-1]
    result["sma200"] = sma200
    if price > sma200:
        signals.append({"name": "SMA200", "dir": "AL", "val": f"${sma200:.2f}", "w": 1})
    else:
        signals.append({"name": "SMA200", "dir": "SAT", "val": f"${sma200:.2f}", "w": 1})

    # ── 9. ATR ──
    atr_ind = ta.volatility.AverageTrueRange(high, low, close, window=14)
    atr = atr_ind.average_true_range().iloc[-1]
    result["atr"] = atr

    # ── 10. ADX (Trend Gücü) ──
    try:
        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        adx = adx_ind.adx().iloc[-1]
        result["adx"] = adx
        if adx > 25:
            signals.append({"name": "ADX", "dir": "AL" if ema9 > ema21 else "SAT", "val": f"{adx:.0f}", "w": 1})
        else:
            signals.append({"name": "ADX", "dir": "NÖTR", "val": f"{adx:.0f}", "w": 0})
    except Exception:
        result["adx"] = 0

    # ── MUM FORMASYONU ──
    o, h_val, l_val, c_val = df["open"].iloc[-1], df["high"].iloc[-1], df["low"].iloc[-1], df["close"].iloc[-1]
    po, pc_val = df["open"].iloc[-2], df["close"].iloc[-2]
    body = abs(c_val - o)
    rng = h_val - l_val
    upper_shadow = h_val - max(o, c_val)
    lower_shadow = min(o, c_val) - l_val

    candle_pattern = "Normal"
    candle_type = "neutral"
    if rng > 0:
        if body / rng < 0.1 and lower_shadow > body * 2:
            candle_pattern, candle_type = "Çekiç 🔨", "bullish"
        elif body / rng < 0.1 and upper_shadow > body * 2:
            candle_pattern, candle_type = "Ters Çekiç ⚡", "bearish"
        elif c_val > o and pc_val < po and c_val > df["high"].iloc[-2]:
            candle_pattern, candle_type = "Yutan Boğa 🐂", "bullish"
        elif o > c_val and po < pc_val and o > pc_val:
            candle_pattern, candle_type = "Yutan Ayı 🐻", "bearish"
        elif body / rng < 0.05:
            candle_pattern, candle_type = "Doji ✦", "neutral"
        elif c_val > o and body > rng * 0.7:
            candle_pattern, candle_type = "Güçlü Boğa 🚀", "bullish"
        elif o > c_val and body > rng * 0.7:
            candle_pattern, candle_type = "Güçlü Ayı 📉", "bearish"

    result["candle_pattern"] = candle_pattern
    result["candle_type"] = candle_type
    if candle_type == "bullish":
        signals.append({"name": "Mum", "dir": "AL", "val": candle_pattern, "w": 1})
    elif candle_type == "bearish":
        signals.append({"name": "Mum", "dir": "SAT", "val": candle_pattern, "w": 1})

    # ── SKOR HESAPLAMA ──
    score_raw = sum(s["w"] * (1 if s["dir"] == "AL" else -1 if s["dir"] == "SAT" else 0) for s in signals)
    max_score = sum(s["w"] for s in signals) if signals else 1
    normalized = ((score_raw + max_score) / (2 * max_score)) * 100
    result["score"] = normalized
    result["signals"] = signals

    if normalized >= 75:
        result["direction"] = "GÜÇLÜ AL"
        result["strength"] = "very-bullish"
    elif normalized >= 60:
        result["direction"] = "AL"
        result["strength"] = "bullish"
    elif normalized >= 45:
        result["direction"] = "NÖTR"
        result["strength"] = "neutral"
    elif normalized >= 30:
        result["direction"] = "SAT"
        result["strength"] = "bearish"
    else:
        result["direction"] = "GÜÇLÜ SAT"
        result["strength"] = "very-bearish"

    # ── TP / SL ──
    result["tp1"] = price + atr * 1.5
    result["tp2"] = price + atr * 2.5
    result["tp3"] = price + atr * 4.0
    result["sl"] = price - atr * 1.2

    # ── HACİM ANALİZİ ──
    vol_avg = volume.tail(20).mean()
    vol_last = volume.iloc[-1]
    result["vol_ratio"] = vol_last / vol_avg if vol_avg > 0 else 1

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  GÖRSEL RENDER FONKSİYONLARI
# ═══════════════════════════════════════════════════════════════════════════

def get_direction_color(strength):
    colors = {
        "very-bullish": "#00E676",
        "bullish": "#66BB6A",
        "neutral": "#FFA726",
        "bearish": "#EF5350",
        "very-bearish": "#D50000"
    }
    return colors.get(strength, "#888")


def get_badge_class(strength):
    mapping = {
        "very-bullish": "badge-strong-buy",
        "bullish": "badge-buy",
        "neutral": "badge-neutral",
        "bearish": "badge-sell",
        "very-bearish": "badge-strong-sell"
    }
    return mapping.get(strength, "badge-neutral")


def get_card_class(strength):
    if strength in ("very-bullish", "bullish"):
        return "signal-card-buy"
    elif strength in ("very-bearish", "bearish"):
        return "signal-card-sell"
    return "signal-card-neutral"


def format_price(p):
    if p >= 1000:
        return f"${p:,.2f}"
    elif p >= 1:
        return f"${p:.4f}"
    elif p >= 0.001:
        return f"${p:.6f}"
    return f"${p:.8f}"


def format_volume(v):
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    elif v >= 1e6:
        return f"${v/1e6:.2f}M"
    elif v >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


def render_signal_bar_html(signals):
    buy = sum(1 for s in signals if s["dir"] == "AL")
    sell = sum(1 for s in signals if s["dir"] == "SAT")
    neutral = sum(1 for s in signals if s["dir"] == "NÖTR")
    total = buy + sell + neutral
    if total == 0:
        return ""
    return f"""
    <div class="signal-bar-container">
        <div class="signal-bar-buy" style="flex:{buy};min-width:{'4px' if buy > 0 else '0'}"></div>
        <div class="signal-bar-neutral" style="flex:{neutral};min-width:{'4px' if neutral > 0 else '0'}"></div>
        <div class="signal-bar-sell" style="flex:{sell};min-width:{'4px' if sell > 0 else '0'}"></div>
    </div>
    <div style="display:flex;justify-content:space-between;font-family:'JetBrains Mono',monospace;font-size:10px;color:#555">
        <span style="color:#00E676">{buy} AL</span>
        <span>{neutral} NÖTR</span>
        <span style="color:#FF5252">{sell} SAT</span>
    </div>
    """


def render_indicator_chips(signals):
    chips = ""
    for s in signals:
        cls = "ind-buy" if s["dir"] == "AL" else "ind-sell" if s["dir"] == "SAT" else "ind-neutral"
        chips += f'<div class="ind-chip {cls}">{s["name"]}<br><b>{s["dir"]}</b></div>'
    return f'<div class="indicator-grid">{chips}</div>'


def render_tp_sl(coin):
    price = coin["price"]
    items = [
        ("TP1", coin["tp1"], "#00E676", "rgba(0,230,118,0.08)", "rgba(0,230,118,0.2)"),
        ("TP2", coin["tp2"], "#69F0AE", "rgba(105,240,174,0.08)", "rgba(105,240,174,0.2)"),
        ("TP3", coin["tp3"], "#B2FF59", "rgba(178,255,89,0.08)", "rgba(178,255,89,0.2)"),
        ("SL", coin["sl"], "#FF5252", "rgba(255,82,82,0.08)", "rgba(255,82,82,0.2)"),
    ]
    cards = ""
    for label, val, color, bg, border in items:
        pct = ((val - price) / price) * 100
        cards += f"""
        <div class="tp-card" style="background:{bg};border:1px solid {border}">
            <div class="tp-card-label">{label}</div>
            <div class="tp-card-value" style="color:{color}">{format_price(val)}</div>
            <div class="tp-card-pct">{pct:+.2f}%</div>
        </div>
        """
    return f'<div class="tp-sl-grid">{cards}</div>'


def render_coin_card(coin, market_data):
    """Tam coin kartı HTML render"""
    symbol = coin["symbol"]
    name = coin["name"]
    full_name = COIN_NAMES.get(name, name)
    color = get_direction_color(coin["strength"])
    badge = get_badge_class(coin["strength"])
    card_cls = get_card_class(coin["strength"])
    price = coin["price"]

    mkt = market_data.get(symbol, {})
    change = mkt.get("change", 0)
    change_cls = "change-positive" if change >= 0 else "change-negative"
    change_icon = "▲" if change >= 0 else "▼"
    vol_usd = mkt.get("quoteVolume", 0)

    signal_bar = render_signal_bar_html(coin["signals"])
    ind_chips = render_indicator_chips(coin["signals"])
    tp_sl = render_tp_sl(coin)

    score_color = color

    html = f"""
    <div class="signal-card {card_cls}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="display:flex;align-items:center;gap:12px">
                <div style="width:44px;height:44px;border-radius:12px;
                    background:linear-gradient(135deg,{color}30,{color}10);
                    display:flex;align-items:center;justify-content:center;
                    font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:900;
                    color:{color};border:2px solid {color}60">
                    {name[:3]}
                </div>
                <div>
                    <div class="coin-header">{name}/USDT</div>
                    <div class="coin-sub">{full_name}</div>
                </div>
            </div>
            <div style="text-align:right">
                <div class="price-main" style="color:#e6edf3">{format_price(price)}</div>
                <div class="{change_cls}" style="font-family:'JetBrains Mono',monospace;font-weight:700;font-size:14px">
                    {change_icon} {abs(change):.2f}%
                </div>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin:12px 0 8px 0">
            <div class="score-gauge">
                <div class="score-number" style="color:{score_color}">{coin['score']:.0f}</div>
                <div class="score-label">SİNYAL SKORU</div>
            </div>
            <div>
                <span class="badge {badge}">{coin['direction']}</span>
            </div>
            <div style="text-align:right;font-family:'JetBrains Mono',monospace;font-size:10px;color:#555">
                <div>RSI: <b style="color:{'#00E676' if coin['rsi']<30 else '#FF5252' if coin['rsi']>70 else '#FFA726'}">{coin['rsi']:.1f}</b></div>
                <div>Hacim: <b style="color:#00BCD4">{format_volume(vol_usd)}</b></div>
                <div>{coin['candle_pattern']}</div>
                {'<div style="color:#7C4DFF;font-weight:700">⚡ BB SIKIŞTIRMA</div>' if coin.get('bb_squeeze') else ''}
            </div>
        </div>

        {signal_bar}
        {ind_chips}

        <div style="margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:10px;color:#555;letter-spacing:1px;font-weight:700">
            HEDEFLEMELİ İŞLEM SEVİYELERİ (ATR BAZLI)
        </div>
        {tp_sl}
    </div>
    """
    return html


# ═══════════════════════════════════════════════════════════════════════════
#  ANA UYGULAMA
# ═══════════════════════════════════════════════════════════════════════════

def main():
    # ── LOGO HEADER ──
    st.markdown("""
    <div class="main-header">
        <div class="logo-box">α</div>
        <div>
            <div class="title-main">ALFA NEXUS PRO v8.0</div>
            <div class="title-sub">Bulut Tabanlı Algoritmik Ticaret Paneli</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── SIDEBAR KONTROLLER ──
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:12px 0">
            <div style="font-family:'JetBrains Mono',monospace;font-weight:900;font-size:18px;
                background:linear-gradient(90deg,#00E676,#00BCD4);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent">
                ⚙️ KONTROL PANELİ
            </div>
        </div>
        """, unsafe_allow_html=True)

        selected_tf_label = st.selectbox(
            "⏱ Zaman Dilimi",
            list(TIMEFRAMES.keys()),
            index=3,  # default: 1 Saat
            help="Teknik analiz için kullanılacak mum zaman dilimi"
        )
        selected_tf = TIMEFRAMES[selected_tf_label]

        st.markdown("---")
        signal_filter = st.selectbox(
            "🎯 Sinyal Filtresi",
            ["🔵 Tümü", "🟢 Sadece AL", "🔴 Sadece SAT", "⚡ Güçlü Sinyaller", "🔥 BB Sıkışma"],
            index=0
        )

        st.markdown("---")
        sort_option = st.selectbox(
            "📊 Sıralama",
            ["Skor (Yüksek → Düşük)", "Skor (Düşük → Yüksek)", "Değişim (Yüksek)", "Değişim (Düşük)", "RSI (Düşük)", "RSI (Yüksek)"],
            index=0
        )

        st.markdown("---")
        coin_search = st.text_input("🔍 Coin Ara", "", placeholder="BTC, ETH, SOL...")

        st.markdown("---")
        if st.button("🔄 Verileri Yenile", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("""
        <div style="margin-top:30px;text-align:center;font-size:9px;color:#333;
            font-family:'JetBrains Mono',monospace;letter-spacing:1px">
            ALFA NEXUS PRO v8.0<br>
            Binance API • 10 İndikatör<br>
            Mum Formasyonu • ATR TP/SL<br>
            © 2025 Kripto Radar
        </div>
        """, unsafe_allow_html=True)

    # ── VERİ ÇEKME ──
    with st.spinner(""):
        progress_bar = st.progress(0)
        status_text = st.empty()

        market_data = get_market_data()
        fng = get_fear_greed()

        all_results = []
        total = len(TOP_COINS)

        for i, symbol in enumerate(TOP_COINS):
            status_text.markdown(f"""
            <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#555">
                <span class="status-dot status-loading"></span>
                Analiz ediliyor: <b style="color:#00BCD4">{symbol.replace('USDT','')}/USDT</b>
                ({i+1}/{total})
            </div>
            """, unsafe_allow_html=True)

            df = get_klines(symbol, selected_tf)
            if df is not None:
                result = analyze_coin(df, symbol)
                if result is not None:
                    all_results.append(result)

            progress_bar.progress((i + 1) / total)

        progress_bar.empty()
        status_text.empty()

    if not all_results:
        st.error("⚠️ Veri çekilemedi. Lütfen internet bağlantınızı kontrol edin.")
        return

    # ── FİLTRELE ──
    filtered = all_results.copy()
    if coin_search:
        filtered = [c for c in filtered if coin_search.upper() in c["name"]]
    if "AL" in signal_filter:
        filtered = [c for c in filtered if c["score"] >= 60]
    elif "SAT" in signal_filter:
        filtered = [c for c in filtered if c["score"] < 40]
    elif "Güçlü" in signal_filter:
        filtered = [c for c in filtered if c["score"] >= 75 or c["score"] < 25]
    elif "Sıkışma" in signal_filter:
        filtered = [c for c in filtered if c.get("bb_squeeze")]

    # ── SIRALA ──
    if "Yüksek → Düşük" in sort_option:
        filtered.sort(key=lambda x: x["score"], reverse=True)
    elif "Düşük → Yüksek" in sort_option:
        filtered.sort(key=lambda x: x["score"])
    elif "Değişim (Yüksek)" in sort_option:
        filtered.sort(key=lambda x: market_data.get(x["symbol"], {}).get("change", 0), reverse=True)
    elif "Değişim (Düşük)" in sort_option:
        filtered.sort(key=lambda x: market_data.get(x["symbol"], {}).get("change", 0))
    elif "RSI (Düşük)" in sort_option:
        filtered.sort(key=lambda x: x["rsi"])
    elif "RSI (Yüksek)" in sort_option:
        filtered.sort(key=lambda x: x["rsi"], reverse=True)

    # ── ÜST PANEL: İSTATİSTİKLER ──
    buy_count = sum(1 for c in all_results if c["score"] >= 60)
    sell_count = sum(1 for c in all_results if c["score"] < 40)
    neutral_count = sum(1 for c in all_results if 40 <= c["score"] < 60)
    squeeze_count = sum(1 for c in all_results if c.get("bb_squeeze"))
    avg_score = np.mean([c["score"] for c in all_results]) if all_results else 0

    if fng:
        fng_val = int(fng.get("value", 50))
        fng_text = fng.get("value_classification", "Nötr")
        fng_color = "#00E676" if fng_val > 60 else "#FFA726" if fng_val > 40 else "#FF5252"
        cols = st.columns(7)
    else:
        cols = st.columns(6)

    with cols[0]:
        st.metric("🟢 AL SİNYALİ", buy_count,
                   delta=f"{(buy_count/len(all_results)*100):.0f}%" if all_results else "0%")
    with cols[1]:
        st.metric("🔴 SAT SİNYALİ", sell_count,
                   delta=f"{(sell_count/len(all_results)*100):.0f}%" if all_results else "0%",
                   delta_color="inverse")
    with cols[2]:
        st.metric("🟡 NÖTR", neutral_count)
    with cols[3]:
        st.metric("⚡ BB SIKIŞTIRMA", squeeze_count)
    with cols[4]:
        btc_data = market_data.get("BTCUSDT", {})
        st.metric("₿ BTC", f"${btc_data.get('price', 0):,.0f}",
                   delta=f"{btc_data.get('change', 0):+.2f}%")
    with cols[5]:
        st.metric("📊 ORT. SKOR", f"{avg_score:.0f}/100")

    if fng:
        with cols[6]:
            st.metric(f"😱 KORKU/AÇGÖZLÜLÜK", f"{fng_val}",
                       delta=fng_text)

    st.markdown("---")

    # ── DURUM ÇUBUĞU ──
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px">
        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#555">
            <span class="status-dot status-live"></span>
            <b style="color:#00E676">CANLI</b> • {len(filtered)} coin gösteriliyor • {selected_tf_label}
        </div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#444">
            Son güncelleme: {now} • Otomatik yenileme: 60sn
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── TABLAR ──
    tab1, tab2, tab3 = st.tabs(["📡 SİNYAL KARTLARI", "📋 TABLO GÖRÜNÜMÜ", "📈 DETAYLI ANALİZ"])

    # ── TAB 1: SİNYAL KARTLARI ──
    with tab1:
        if not filtered:
            st.warning("Filtreye uygun coin bulunamadı.")
        else:
            # 2 sütunlu grid
            col1, col2 = st.columns(2)
            for i, coin in enumerate(filtered):
                html = render_coin_card(coin, market_data)
                if i % 2 == 0:
                    with col1:
                        st.markdown(html, unsafe_allow_html=True)
                else:
                    with col2:
                        st.markdown(html, unsafe_allow_html=True)

    # ── TAB 2: TABLO GÖRÜNÜMÜ ──
    with tab2:
        table_data = []
        for coin in filtered:
            mkt = market_data.get(coin["symbol"], {})
            change = mkt.get("change", 0)
            vol = mkt.get("quoteVolume", 0)
            buy_signals = sum(1 for s in coin["signals"] if s["dir"] == "AL")
            sell_signals = sum(1 for s in coin["signals"] if s["dir"] == "SAT")

            table_data.append({
                "Coin": coin["name"],
                "Fiyat": format_price(coin["price"]),
                "Değişim %": f"{change:+.2f}%",
                "RSI": f"{coin['rsi']:.1f}",
                "MACD": "▲" if coin["macd_hist"] > 0 else "▼",
                "StochRSI": f"{coin.get('stoch_k', 0):.0f}",
                "Skor": f"{coin['score']:.0f}/100",
                "Yön": coin["direction"],
                "AL": buy_signals,
                "SAT": sell_signals,
                "Formason": coin["candle_pattern"],
                "BB Sıkışma": "⚡" if coin.get("bb_squeeze") else "",
                "Hacim": format_volume(vol),
                "TP1": format_price(coin["tp1"]),
                "SL": format_price(coin["sl"]),
            })

        df_table = pd.DataFrame(table_data)
        st.dataframe(
            df_table,
            use_container_width=True,
            height=min(len(table_data) * 42 + 60, 800),
            hide_index=True
        )

    # ── TAB 3: DETAYLI ANALİZ ──
    with tab3:
        selected_coin_name = st.selectbox(
            "Coin Seçin",
            [c["name"] for c in filtered],
            index=0 if filtered else None
        )

        if selected_coin_name:
            coin = next((c for c in filtered if c["name"] == selected_coin_name), None)
            if coin:
                mkt = market_data.get(coin["symbol"], {})
                color = get_direction_color(coin["strength"])

                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
                    <div style="width:60px;height:60px;border-radius:16px;
                        background:linear-gradient(135deg,{color}40,{color}10);
                        display:flex;align-items:center;justify-content:center;
                        font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:900;
                        color:{color};border:2px solid {color}60">
                        {coin['name'][:3]}
                    </div>
                    <div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:28px;font-weight:900;color:#e6edf3">
                            {coin['name']}/USDT
                        </div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:14px;color:#555">
                            {COIN_NAMES.get(coin['name'], coin['name'])}
                        </div>
                    </div>
                    <div style="margin-left:auto;text-align:right">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:32px;font-weight:900;color:{color}">
                            {format_price(coin['price'])}
                        </div>
                        <span class="badge {get_badge_class(coin['strength'])}" style="font-size:14px;padding:6px 20px">
                            {coin['direction']}
                        </span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Score + signal bar
                c1, c2, c3 = st.columns([1, 2, 1])
                with c1:
                    st.markdown(f"""
                    <div class="score-gauge" style="padding:20px">
                        <div class="score-number" style="color:{color};font-size:56px">{coin['score']:.0f}</div>
                        <div class="score-label">SİNYAL SKORU / 100</div>
                    </div>
                    """, unsafe_allow_html=True)

                with c2:
                    st.markdown(f"""
                    <div style="padding:10px 0">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:8px">
                            İNDİKATÖR DAĞILIMI
                        </div>
                        {render_signal_bar_html(coin['signals'])}
                        <div style="margin-top:12px">
                            {render_indicator_chips(coin['signals'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with c3:
                    st.markdown(f"""
                    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;padding:10px 0">
                        <div style="color:#555;margin-bottom:8px;font-weight:700;letter-spacing:1px">HIZLI BİLGİ</div>
                        <div style="color:#888">RSI: <b style="color:{'#00E676' if coin['rsi']<30 else '#FF5252' if coin['rsi']>70 else '#FFA726'}">{coin['rsi']:.1f}</b></div>
                        <div style="color:#888">ATR: <b style="color:#00BCD4">{format_price(coin['atr'])}</b></div>
                        <div style="color:#888">ADX: <b>{coin.get('adx',0):.0f}</b></div>
                        <div style="color:#888">Hacim: <b style="color:#00BCD4">{coin['vol_ratio']:.2f}x ort.</b></div>
                        <div style="color:#888">Mum: <b>{coin['candle_pattern']}</b></div>
                        {'<div style="color:#7C4DFF;font-weight:700;margin-top:4px">⚡ BB SIKIŞTIRMA AKTİF</div>' if coin.get('bb_squeeze') else ''}
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("---")

                # TP/SL detay
                st.markdown(f"""
                <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:10px">
                    🎯 HEDEFLEMELİ İŞLEM SEVİYELERİ (ATR BAZLI)
                </div>
                {render_tp_sl(coin)}
                """, unsafe_allow_html=True)

                st.markdown("---")

                # Tüm indikatör detayları
                st.markdown("""
                <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:#555;letter-spacing:1.5px;font-weight:700;margin-bottom:10px">
                    🔬 TEKNİK İNDİKATÖR DETAYLARI
                </div>
                """, unsafe_allow_html=True)

                det_cols = st.columns(4)
                details = [
                    ("RSI (14)", f"{coin['rsi']:.1f}"),
                    ("MACD Hist", f"{coin['macd_hist']:.6f}"),
                    ("BB Genişlik", f"{coin['bb_width']:.2f}%"),
                    ("StochRSI K", f"{coin.get('stoch_k', 0):.1f}"),
                    ("EMA 9", format_price(coin['ema9'])),
                    ("EMA 21", format_price(coin['ema21'])),
                    ("EMA 50", format_price(coin['ema50'])),
                    ("SMA 200", format_price(coin['sma200'])),
                    ("VWAP", format_price(coin['vwap'])),
                    ("ATR (14)", format_price(coin['atr'])),
                    ("ADX", f"{coin.get('adx', 0):.1f}"),
                    ("OBV Trend", coin['obv_trend']),
                ]

                for i, (key, val) in enumerate(details):
                    with det_cols[i % 4]:
                        st.markdown(f"""
                        <div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:10px;margin-bottom:6px;
                            border:1px solid rgba(255,255,255,0.04)">
                            <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:#555;letter-spacing:1px">{key}</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:800;color:#ccc;margin-top:2px">{val}</div>
                        </div>
                        """, unsafe_allow_html=True)

    # ── FOOTER ──
    st.markdown(f"""
    <div class="disclaimer">
        <span style="letter-spacing:2px">ALFA NEXUS PRO v8.0</span> •
        Binance API ile Gerçek Zamanlı Veri •
        10 İndikatör + Mum Formasyonu + ATR TP/SL<br>
        ⚠️ Bu panel yatırım tavsiyesi değildir. Kripto para yatırımları yüksek risk içerir.<br>
        Risk yönetimi her zaman önceliğiniz olmalıdır.
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
