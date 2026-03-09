[README.md](https://github.com/user-attachments/files/25854567/README.md)
# ⚡ ALFA NEXUS PRO v8.0 — Bulut Tabanlı Algoritmik Ticaret Paneli

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Binance](https://img.shields.io/badge/Binance-FCD535?style=for-the-badge&logo=binance&logoColor=black)

## 🚀 Özellikler

### Teknik Analiz Motoru (10 İndikatör)
- **RSI** (Relative Strength Index) — Aşırı alım/satım tespiti
- **MACD** (Moving Average Convergence Divergence) — Trend yön tespiti
- **Bollinger Bands** — Volatilite analizi + Sıkışma tespiti
- **EMA Cross** (9/21/50) — Çoklu hareketli ortalama kesişimi
- **Stochastic RSI** — Momentum osilatörü
- **VWAP** (Volume Weighted Average Price) — Hacim ağırlıklı ortalama
- **OBV** (On-Balance Volume) — Hacim trend analizi
- **SMA 200** — Uzun vadeli trend
- **ADX** — Trend gücü ölçümü
- **ATR** — Volatilite ve TP/SL hesaplama

### Mum Formasyonu Tanıma
Çekiç, Ters Çekiç, Yutan Boğa/Ayı, Doji, Güçlü Boğa/Ayı

### Sinyal Sistemi
- 0-100 arası kompozit sinyal skoru
- 5 kademeli yön: GÜÇLÜ AL → AL → NÖTR → SAT → GÜÇLÜ SAT
- ATR bazlı TP1/TP2/TP3 + Stop Loss seviyeleri
- Bollinger Band Sıkışma (squeeze) uyarısı
- Fear & Greed Endeksi entegrasyonu

### 40 Coin Takibi
Binance'ta listelenen en yüksek piyasa değerli 40 coin gerçek zamanlı analiz

### Zaman Dilimleri
1 Dakika, 5 Dakika, 15 Dakika, 1 Saat, 4 Saat, 1 Gün

## 📦 Kurulum

```bash
git clone https://github.com/gokaydonmez39-jpg/kripto-radar.git
cd kripto-radar
pip install -r requirements.txt
streamlit run app.py
```

## ☁️ Streamlit Cloud ile Deploy

1. GitHub'a push edin
2. [share.streamlit.io](https://share.streamlit.io) adresine gidin
3. Repo: `gokaydonmez39-jpg/kripto-radar`
4. Branch: `main`
5. Main file: `app.py`
6. **Deploy** butonuna tıklayın

## ⚠️ Sorumluluk Reddi

Bu panel yatırım tavsiyesi değildir. Kripto para yatırımları yüksek risk içerir. Risk yönetimi her zaman önceliğiniz olmalıdır.
