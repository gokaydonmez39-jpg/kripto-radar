import streamlit as st
import requests
import pandas as pd

# 1. SAYFA AYARLARI
st.set_page_config(page_title="10/10 Kripto Radar", layout="wide", initial_sidebar_state="collapsed")

# 2. VERİ ÇEKME VE SİNYAL MOTORU
@st.cache_data(ttl=30) 
def fetch_top_300_coins():
 url = "https://data-api.binance.vision/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        df = pd.DataFrame(data)
        df = df[df['symbol'].str.endswith('USDT')]
        
        # Sayısal verilere çevirme
        df['quoteVolume'] = pd.to_numeric(df['quoteVolume'])
        df['lastPrice'] = pd.to_numeric(df['lastPrice'])
        df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'])
        df['highPrice'] = pd.to_numeric(df['highPrice'])
        df['lowPrice'] = pd.to_numeric(df['lowPrice'])
        
        # İlk 300'ü hacme göre filtrele
        df_top_300 = df.sort_values(by='quoteVolume', ascending=False).head(300)
        
        # --- 10/10 SİNYAL ALGORİTMASI ---
        def avci_sinyal(row):
            fiyat = row['lastPrice']
            tepe = row['highPrice']
            dip = row['lowPrice']
            degisim = row['priceChangePercent']
            
            # Kırılım Stratejisi: Fiyat zirveye %1'den daha yakınsa ve artış trendindeyse
            if tepe > 0 and (tepe - fiyat) / tepe < 0.01 and degisim > 2:
                return "🚀 Güçlü Al (Kırılım)"
            
            # Dipten Dönüş Stratejisi: Fiyat dibe %1'den daha yakınsa ve düşüş durmuşsa
            elif dip > 0 and (fiyat - dip) / dip < 0.01 and degisim < -2:
                return "💎 Dipten Topla"
            
            else:
                return "⏳ İzlemede"

        # Yeni "Sinyal" sütununu oluştur ve algoritmayı çalıştır
        df_top_300['Sinyal'] = df_top_300.apply(avci_sinyal, axis=1)
        
        # Ekranda gösterilecekleri seç
        df_final = df_top_300[['symbol', 'lastPrice', 'priceChangePercent', 'quoteVolume', 'Sinyal']].copy()
        df_final.columns = ['Parite', 'Son Fiyat (USDT)', 'Değişim (%)', '24s Hacim (USDT)', '10/10 Sinyal']
        
        return df_final
        
    except Exception as e:
        st.error(f"Sistem Uyarısı: Binance verisi çekilemedi. Hata: {e}")
        return pd.DataFrame()

# 3. WEB ARAYÜZÜ
st.title("🚀 10/10 Kripto Radar Merkezi")
st.markdown("**Sistem Durumu:** Aktif | Özel algoritma devrede. Kırılım ve Dip fırsatları aranıyor.")

with st.spinner('Yapay Zeka piyasayı tarıyor ve sinyalleri hesaplıyor...'):
    df_coins = fetch_top_300_coins()

if not df_coins.empty:
    # Sinyalleri ve Yüzdeleri Renklendirme
    def color_cells(val):
        if isinstance(val, str) and "Güçlü Al" in val:
            return 'background-color: #004d00; color: #00ff00; font-weight: bold;'
        elif isinstance(val, str) and "Dipten" in val:
            return 'background-color: #003366; color: #66ccff; font-weight: bold;'
        elif isinstance(val, str) and "İzlemede" in val:
            return 'color: gray;'
        elif isinstance(val, float) or isinstance(val, int):
            if val < 0:
                return 'color: #ff4b4b; font-weight: bold;'
            elif val > 0:
                return 'color: #00cc96; font-weight: bold;'
        return ''
    
    st.dataframe(
        df_coins.style.applymap(color_cells, subset=['Değişim (%)', '10/10 Sinyal'])
                      .format({"Son Fiyat (USDT)": "${:.4f}", "Değişim (%)": "{:+.2f}%", "24s Hacim (USDT)": "${:,.0f}"}),
        use_container_width=True,
        hide_index=True,
        height=700
    )
else:

    st.warning("Veri bağlantısı bekleniyor. Lütfen sayfayı yenileyin.")
