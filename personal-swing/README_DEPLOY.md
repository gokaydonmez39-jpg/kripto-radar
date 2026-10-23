# XRAY Kişisel START/FINAL — Kod PR ve devreye alma

- **Yalnızca kod** `personal-swing/` içinde GitHub açık depoya eklenir. Hiçbir kişisel sinyal JSON, veri API anahtarı, raw OHLCV, journal veya geçmiş dosyası repoya konmaz.
- Test iş akışı PR üzerinde provider ağına bağlanmadan `python -m unittest -q test_ci_v6 test_v6_alpaca_rest` ve `python -O ...` çalıştırmalıdır.
- Günlük `schedule` (23:15 UTC weekdays) ancak workflow **main** içine gerçekten alındıktan sonra çalışır. Secret'lar `XRAY_ALPACA_DATA_KEY_ID` ve `XRAY_ALPACA_DATA_SECRET_KEY` zaten tanımlanmışsa kullanılır, yoksa fail-closed. Secret değerlerini loglama.
- GitHub Actions ephemeral koşucusu kalıcı journal geçmişi veya iPhone'dan 7/24 özel ekran sağlamaz; bunlar için kimliği doğrulanmış özel depolama/hosting gerekir. Bu PR'ı merge etmek tek başına o iki hizmeti tamamlamaz.
- Kullanıcıya gösterilen yeni teknik AL bildirimleri için mevcut ChatGPT görevi devam eder. GitHub workflow hiçbir push/harici e-posta göndermez.
- Broker ve emir fonksiyonu veya kamuya açık Pages yayını yoktur.
