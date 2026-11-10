# XRAY NASDAQ A36 — Kaynak, yanlışlama ve maliyet ön-kabul kaydı

Tarih: 2026-10-29 (Türkiye). Kapsam: yalnız NASDAQ `personal-swing/research_lab`.
Statü: **RESEARCH-ONLY / NOT PRODUCTION / NO SIGNAL AUTHORITY**.

## 1. Bağımsız kaynak kanıtı

- Alpaca'nın bağlı yalnız-okunur piyasa verisi aracında 28 Ekim 2026'nın
  10:00:00–10:00:15 New York saatindeki beş hisselik tarihsel IEX
  örneklemi sorgulandı. 40 trade ve 248 quote kaydı döndü.
  Üç hissede o 15 saniyede hiç IEX trade döndürülmedi.
  Bu; sıfır alış/satış, tam gün ya da SIP piyasa sessizliği anlamına gelmez.
- Kaynak yanıtları (bağlı ChatGPT örneği) son sayfa jetonlarının tümünü
  bağımsız olarak doğrulamıyor: **REQUESTED_SAMPLE_NOT_FULLY_ATTESTED**.
- İkinci nanosaniye sıralı iki hisselik alt örneklem, toplam 40 işlemi
  quote-mid yöntemiyle ve `conditions=['@']` ön koşuluyla
  değerlendirdi. Bu; gerçek işlem yönü veya balina kimliği değildir.
- İlk basit milisaniye eşleştirmesi, nanosaniye eşleştirmesinden farklı
  sonuç verdi. Bu yüzden nanosaniye kesin sıra zorunlu kılındı.
- Kişisel ticker/sinyal düzeyinde yeni bir kamu dataseti, alış uyarısı,
  raw tick veya özel Sheet çıktısı oluşturulmadı.

## 2. Sabit duyarlılık matrisi (sadece araştırma ölçümü)

İki hisselik alt örneklem, 40 IEX işlemi, 28 Ekim 2026 ET 10:00:00–10:00:15.
Aşağıdaki sayılar alım/satım doğruluğu değil, **sınıflandırılabilen işlem adedi**.

| Önceki quote üst yaş sınırı | Maks. spread %0,1 | %0,5 | %1,0 |
|---:|---:|---:|---:|
| 250 ms | 1 | 7 | 9 |
| 500 ms | 1 | 8 | 10 |
| 1000 ms | 1 | 8 | 10 |

* Örneklem küçük ve zaman seçimi tek seans; eşikleri bu gözlemde
  en iyi görünen sonuçlara göre değiştirmek yasak.
* IEX quote ulusal NBBO sertifikası değildir. Quote-mid yönü tahminidir.
* Düzeltilmiş/iptal işlemler (`u`) UNKNOWN'a gider; kayıt iptali
  ve düzeltme için tam konsolidasyon motoru yoktur.
* Aynı nanosecond quote/trade'e nedensel öncelik verilmez.

## 3. Maliyet/kapasite alt sınırı (tahmin — gerçekleşmiş kota değil)

Her hisse için tek bir trade ve quote sorgusu yapılması durumunda
477 × 2 = **954 minimum GET**. Bu, sayfalama, düzeltme,
geçersiz sayfa, yeniden deneme ve farklı günleri kapsamıyor.
Alpaca Basic dokümantasyonu 200 tarihsel istek/dakika verdiğinden
yalnız bu teorik alt sınır dahi 954 / 200 = **4,77 dakika**
talep kapasitesi gerektirir. Bu bir canlı tarama süresi tahmini
veya ücret/abonelik doğrulaması değildir. Tam tick hacmi nedeniyle
gerçek ihtiyaç çok daha yüksek olabilir.

Mevcut manuel pilot en fazla 5 hisse, hisse başı 2 endpoint,
endpoint başı 10 sayfa, 1000 kayıt/sayfa ve maksimum 60 sn
veri penceresi ile sınırlandırılmıştır.
Bir pilot için **en fazla 100 GET** ve endpoint başına
10.000 kayıt limiti bulunur. Bu oran plan bazında garanti değildir;
aynı hesaptaki başka API çağrıları kotayı tüketebilir.
429/ulaşılamayan servis **BLOCKED**, asla AL veya başarı değildir.

## 4. Önceden ilan edilmiş geleceğe dönük değerlendirme koşulları

Bunlar henüz karşılanmadı ve bu tarihsel örneklem için
geriye dönük kabul ölçütü diye kullanılmamalıdır:

1. **Sağlam provenance:** Örneklenen her venue ve kaynak için lisans,
   veri hakkı, sembol geçmişi, raw/adjustment, exchange,
   `u` düzeltmeleri, trade/quote koşulları, tüm jetonlar,
   ET ve UTC zamanları doğrulanacak.
2. **Tam gün pilotu:** En az 20 ardışık resmî XNAS seansında,
   likidite bakımından katmanlı ve başlangıçta sabitlenmiş
   en az 5 hisse; açık saatlerini ve seans kapanışını kapsayan
   bağımsız kaynak kalite mutabakatı. UNKNOWN oranı ve hacim
   kapsamı ayrı raporlanacak. Bu eşiğin rastgele hisse seçiminin
   temsili olduğu iddia edilmiyor.
3. **Karşı hipotez:** EOD RVOL, RSI, gap, piyasa betası ve
   likidite zaten mevcut temel çizgi. Gerçek flow verisi
   bu değişkenleri kontrol ettikten sonra katkı sağlıyor mu?
4. **Risk ve OOS:** 15 seanslık etiket çakışmalarına purge + embargo,
   gerçekçi gap/commission/spread/slippage, çoklu deney düzeltmesi,
   walk-forward ve zamansal rejim dayanıklılığı olmadan AL filtresi
   veya balina bildirimi eklenmez.
5. **Mimari:** Yeni özel veri deposu, sürekli toplayıcı, GitHub secret,
   Sheets sekmesi, yeni :57 görev veya herhangi bir gerçek emir
   bu araştırma PR'ında oluşturulmayacak. Böyle bir entegrasyon
   ayrı güvenlik/izin onayına tabidir.

## 5. Kararlar

- Kaynak ihtilafı: IEX üretim AL kararını ve tarihsel fiyat/stop/hedefleri
  SIP veya quote-mid ölçümüyle değiştirmiyoruz.
- Yanlışlanabilirlik: Hacim artışı bağımsız alıcı kimliği değildir.
- Eksik örneklem: NO TRADES IN SAMPLE ≠ NO SIGNAL ≠ SELL.
- Sadece okuma: korunan ana EOD workflow, özel Sheets, iPhone alarmı,
  ChatGPT :57 ve bağımsız kripto sistemi değiştirilmez.

## Resmî kaynaklar

- Alpaca trades: https://docs.alpaca.markets/us/reference/stocktradesingle-1
- Alpaca quotes: https://docs.alpaca.markets/us/reference/stockquotesingle-1
- Alpaca feed and subscription policy: https://docs.alpaca.markets/us/docs/market-data-faq
- Alpaca Basic historical rate plan (hesaba özgü garanti değil):
  https://docs.alpaca.markets/us/docs/about-market-data-api
