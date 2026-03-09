import streamlit as st
import requests
import pandas as pd
import ta
from streamlit_autorefresh import st_autorefresh

# 1. SAYFA AYARLARI
st.set_page_config(page_title="10/10 Kripto Radar PRO", layout="wide", initial_sidebar_state="collapsed")

# OTO-PİLOT: Sayfayı her 60 saniyede bir el değmeden otomatik yeniler (60000 milisaniye)
st_autorefresh(interval=60000, limit=None, key="pro_autorefresh")

# 2. YAPAY ZEKA VE VERİ MOTORU
@st.cache_data(ttl=50) 
def get_pro_market_data():
    # En hacimli 50 coini bul
    ticker_url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        resp = requests.get(ticker_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df = df[df['symbol'].str.endswith('USDT')]
        df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
        
        # Sistemi yormamak için en hacimli 50 coini filtrele
        top_50 = df.sort_values(by='quoteVolume', ascending=False).head(50)['symbol'].tolist()
        
        results = []
        # Bu 50 coin için 15 dakikalık canlı mumları çek ve Matematiğe (RSI/MACD) sok
        for coin in top_50:
            try:
                kline_url = f"https://data-api.binance.vision/api/v3/klines?symbol={coin}&interval=15m&limit=50"
                k_resp = requests.get(kline_url, timeout=5)
                k_data = k_resp.json()
                
                # Sadece kapanış fiyatlarını al
                closes = [float(candle[4]) for candle in k_data]
                df_k = pd.DataFrame(closes, columns=['Close'])
                
                # PROFESYONEL İNDİKATÖRLER (RSI ve MACD)
                rsi = ta.momentum.RSIIndicator(df_k['Close'], window=14).rsi().iloc[-1]
                macd_line = ta.trend.MACD(df_k['Close']).macd().iloc[-1]
                macd_signal = ta.trend.MACD(df_k['Close']).macd_signal().iloc[-1]
                
                # Ticker'dan günlük değişimi al
                coin_info = df[df['symbol'] == coin].iloc[0]
                change_pct = float(coin_info['priceChangePercent'])
                volume = float(coin_info['quoteVolume'])
                current_price = closes[-1]
                
                # --- 10/10 ULTRA SİNYAL ALGORİTMASI ---
                sinyal = "⏳ İzlemede"
                
                # Mantık 1: RSI 30'un altındaysa (Aşırı Satım) ve MACD yukarı kesiyorsa -> DİPTEN AL
                if rsi < 30 and macd_line > macd_signal:
                    sinyal = "💎 DİPTEN AL (RSI + MACD Onaylı)"
                    
                # Mantık 2: RSI 70'in üzerindeyse (Aşırı Alım) ve MACD aşağı kesiyorsa -> DİKKAT SATIŞ
                elif rsi > 70 and macd_line < macd_signal:
                    sinyal = "🚨 DİKKAT TEHLİKE (Aşırı Şişti)"
                    
                # Mantık 3: Günlük %3'ten fazla artmış, Hacim uçmuş ve RSI hala 70'in altındaysa -> HACİM PATLAMASI
                elif change_pct > 3 and volume > 50000000 and rsi < 70:
                    sinyal = "🚀 HACİM PATLAMASI (Trend Güçlü)"

                results.append({
                    "Parite": coin,
                    "Son Fiyat": current_price,
                    "Değişim (%)": change_pct,
                    "RSI (15m)": round(rsi, 2),
                    "Hacim (USDT)": volume,
                    "10/10 PRO Sinyal": sinyal
                })
            except:
                continue # Hata veren coin olursa sistemi çökertme, diğerine geç (İşte sağlamlık budur)
                
        return pd.DataFrame(results)
        
    except Exception as e:
        st.error(f"Bağlantı Hatası: {e}")
        return pd.DataFrame()

# 3. PROFESYONEL ARAYÜZ
st.title("⚡ 10/10 Kripto Radar PRO")
st.markdown("**Sistem Durumu:** 🟢 **OTO-PİLOT AKTİF** | Her 60 saniyede bir kendini yeniler. İlk 50 coin RSI ve MACD ile anlık taranıyor.")

with st.spinner('Piyasa matematiği hesaplanıyor, lütfen bekleyin...'):
    df_final = get_pro_market_data()

if not df_final.empty:
    def color_pro(val):
        if isinstance(val, str):
            if "DİPTEN AL" in val: return 'background-color: #003366; color: #00ffcc; font-weight: bold;'
            if "HACİM PATLAMASI" in val: return 'background-color: #004d00; color: #00ff00; font-weight: bold;'
            if "TEHLİKE" in val: return 'background-color: #4d0000; color: #ff3333; font-weight: bold;'
            if "İzlemede" in val: return 'color: gray;'
        elif isinstance(val, float):
            if val < 0: return 'color: #ff4b4b; font-weight: bold;'
            if val > 0: return 'color: #00cc96; font-weight: bold;'
        return ''
        
    st.dataframe(
        df_final.style.applymap(color_pro, subset=['Değişim (%)', '10/10 PRO Sinyal'])
                      .format({"Son Fiyat": "${:.4f}", "Değişim (%)": "{:+.2f}%", "Hacim (USDT)": "${:,.0f}"}),
        use_container_width=True,
        hide_index=True,
        height=700
    )
else:
    st.warning("Veriler işleniyor, otomatik olarak yenilenecektir...")
