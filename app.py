import streamlit as st
import requests
import pandas as pd
import ta
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# 1. ULTRA SAYFA AYARLARI (Geniş ekran, pro görünüm)
st.set_page_config(page_title="🚀 Kripto Radar ULTRA", layout="wide", initial_sidebar_state="expanded")

# 60 Saniyede Bir Tam Otomatik Yenileme
st_autorefresh(interval=60000, limit=None, key="ultra_refresh")

# CSS ile Profesyonel Makyaj (Siyah tema metrik kartları)
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: #1e1e1e; border: 1px solid #333; padding: 5% 10% 5% 10%; border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# 2. GELİŞMİŞ VERİ VE SKORLAMA MOTORU
@st.cache_data(ttl=50)
def get_ultra_data():
    ticker_url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        data = requests.get(ticker_url, timeout=10).json()
        df = pd.DataFrame(data)
        df = df[df['symbol'].str.endswith('USDT')]
        df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
        
        # Sistemi en hızlı tutmak için en hacimli 30 coini (Balina koinleri) al
        top_30 = df.sort_values(by='quoteVolume', ascending=False).head(30)
        
        results = []
        for index, row in top_30.iterrows():
            coin = row['symbol']
            try:
                # Canlı 15 dakikalık mumları çek
                kline_url = f"https://data-api.binance.vision/api/v3/klines?symbol={coin}&interval=15m&limit=100"
                k_data = requests.get(kline_url, timeout=5).json()
                
                df_k = pd.DataFrame(k_data, columns=['Open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close_time', 'Quote_asset_volume', 'Number_of_trades', 'Taker_buy_base_asset_volume', 'Taker_buy_quote_asset_volume', 'Ignore'])
                df_k['Close'] = pd.to_numeric(df_k['Close'])
                
                # İNDİKATÖRLER (RSI, MACD ve EMA50)
                rsi = ta.momentum.RSIIndicator(df_k['Close'], window=14).rsi().iloc[-1]
                macd = ta.trend.MACD(df_k['Close'])
                macd_line = macd.macd().iloc[-1]
                macd_signal = macd.macd_signal().iloc[-1]
                ema_50 = ta.trend.EMAIndicator(df_k['Close'], window=50).ema_indicator().iloc[-1]
                
                current_price = df_k['Close'].iloc[-1]
                change_pct = float(row['priceChangePercent'])
                
                # --- ULTRA GÜÇ SKORU HESAPLAMA (100 Üzerinden) ---
                score = 50 # Başlangıç nötr
                if rsi < 35: score += 20 # Ucuzlamış
                elif rsi > 70: score -= 20 # Şişmiş
                
                if macd_line > macd_signal: score += 15 # Trend yukarı kesti
                else: score -= 15
                
                if current_price > ema_50: score += 15 # Güçlü trend üzerinde
                
                if change_pct > 2: score += 10 # Hacim ivmesi var
                
                # Skor Yorumlama
                if score >= 85: sinyal = "🟢 NOKTA ATIŞI AL (Mükemmel)"
                elif score >= 70: sinyal = "🟢 GÜÇLÜ AL"
                elif score <= 30: sinyal = "🔴 TEHLİKE (Düşüş)"
                else: sinyal = "⏳ Nötr Bölge"
                
                results.append({
                    "Parite": coin,
                    "Fiyat": current_price,
                    "Değişim (%)": change_pct,
                    "RSI": round(rsi, 1),
                    "Güç Skoru": score,
                    "Durum": sinyal
                })
            except:
                continue
                
        return pd.DataFrame(results), top_30
    except:
        return pd.DataFrame(), pd.DataFrame()

# 3. INTERAKTİF GRAFİK ÇİZDİRİCİ
def draw_chart(coin_symbol):
    try:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={coin_symbol}&interval=15m&limit=60"
        data = requests.get(url).json()
        df_c = pd.DataFrame(data, columns=['Time', 'Open', 'High', 'Low', 'Close', 'Vol', 'CloseTime', 'QVol', 'Trades', 'TakerBase', 'TakerQuote', 'Ignore'])
        df_c['Time'] = pd.to_datetime(df_c['Time'], unit='ms')
        for col in ['Open', 'High', 'Low', 'Close']: df_c[col] = df_c[col].astype(float)
        
        fig = go.Figure(data=[go.Candlestick(x=df_c['Time'], open=df_c['Open'], high=df_c['High'], low=df_c['Low'], close=df_c['Close'], name='Fiyat')])
        fig.update_layout(title=f"{coin_symbol} Canlı Mum Grafiği (15m)", template="plotly_dark", height=400, margin=dict(l=0, r=0, t=40, b=0))
        return fig
    except:
        return None

# --- ARAYÜZ (DASHBOARD) ---
st.title("🎯 Kripto Radar ULTRA: Wall Street Terminali")

with st.spinner('Kuantum algoritmaları piyasayı tarıyor...'):
    df_signals, df_raw = get_ultra_data()

if not df_signals.empty:
    # ÜST PANO (KPI METRİKLERİ)
    btc_price = df_signals[df_signals['Parite'] == 'BTCUSDT']['Fiyat'].values[0] if 'BTCUSDT' in df_signals['Parite'].values else 0
    firsat_sayisi = len(df_signals[df_signals['Güç Skoru'] >= 80])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("👑 Lider: BTC/USDT", f"${btc_price:,.2f}")
    col2.metric("🎯 Nokta Atışı Fırsat Sayısı", f"{firsat_sayisi} Adet", "Yapay Zeka Onaylı")
    col3.metric("⏱️ Sistem Durumu", "Aktif", "Oto-Pilot Devrede")
    
    st.markdown("---")
    
    # ORTA BÖLÜM: GRAFİK VE LİSTE YAN YANA
    left_col, right_col = st.columns([1, 2])
    
    with left_col:
        st.subheader("Filtre & Grafik Seçimi")
        secilen_coin = st.selectbox("Grafiğini Görmek İstediğin Coini Seç:", df_signals['Parite'].tolist())
        st.markdown("**Nokta Atışı Sinyaller (Skor > 85)**")
        st.dataframe(df_signals[df_signals['Güç Skoru'] >= 85][['Parite', 'Fiyat']], hide_index=True, use_container_width=True)

    with right_col:
        # Seçilen coinin profesyonel mum grafiğini çiz
        chart = draw_chart(secilen_coin)
        if chart:
            st.plotly_chart(chart, use_container_width=True)
            
    st.markdown("---")
    
    # ALT BÖLÜM: ANA TERMİNAL TABLOSU (Renkli)
    st.subheader("🌐 Tüm Piyasa Algoritma Sonuçları")
    def style_terminal(val):
        if isinstance(val, str) and "NOKTA" in val: return 'background-color: #004d00; color: #00ff00; font-weight: bold;'
        if isinstance(val, str) and "GÜÇLÜ AL" in val: return 'color: #00ffcc; font-weight: bold;'
        if isinstance(val, str) and "TEHLİKE" in val: return 'color: #ff3333; font-weight: bold;'
        if isinstance(val, (int, float)) and val >= 85: return 'color: #00ff00; font-weight: bold;'
        return ''
    
    st.dataframe(
        df_signals.style.applymap(style_terminal, subset=['Durum', 'Güç Skoru'])
                        .format({"Fiyat": "${:.4f}", "Değişim (%)": "{:+.2f}%"}),
        use_container_width=True, hide_index=True, height=400
    )
else:
    st.warning("Veriler çekiliyor, Terminal birazdan aktif olacak...")
