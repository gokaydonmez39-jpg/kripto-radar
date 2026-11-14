# XRAY NASDAQ 477 · #406 üretim geçişi için ilk kabul kontrolü

## Kanıt

- İzole App giriş ve yayın testi: [43583838228](https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/43583838228), üçüncü deneme başarılı; [43589985977](https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/43589985977), GitHub App push olayı, zorunlu CI ve korumalı test dalına yayın başarılı. Staging ve test hedefi aynı `c0cacce6809ec099d98c4788c9c585ef5821a7a4` SHA'sına ve aynı sentetik blob'a sahip.
- Canlı inceleme: [ruleset 26024575](https://github.com/gokaydonmez39-jpg/kripto-radar/rules/26024575) varsayılan dalda etkin. Yalnız silme ve force-push korumaları var, zorunlu CI yok.
- İncelenen main: `14084b22cf64bd10b8c16acc60ed8a0944fdc939`. Son overlay commit'i doğrudan yazımın sürdüğünü gösterir. Bu tarihte main'deki zorunlu iş PR olayıyla tetiklenir; izole pilotun staging push yolu main'de yoktur.
- Official Witness iş akışı iki ayrı doğrudan yazım içerir. İlk yazım resmi guard ve append-only ledger içindir; ikinci yazım daha geniş resilience dosyaları içindir ve ilk yazımın kabul kapsamına girmez. [Gerçek iki dosyalı örnek](https://github.com/gokaydonmez39-jpg/kripto-radar/commit/3c67b87fe16c9a79f3465c880049dba0ee53e518). Bu örnek yeniden yayımlanmaz.

## Bu dalın sınırı

Bu çalışma yalnız çevrimdışı kabul kodu ve sentetik testler ekler. Workflow, token, cron, Sheet, ruleset veya canlı yazım değişikliği içermez. Araç güvenilir kaynaktan bağımsız alınan CI ve görünürlük makbuzlarının aday SHA ve blob kimlikleriyle bağını sınar. Makbuzları kendi üretmez ve kaynak kimliğini kendi doğrulamaz.

```sh
python -m unittest discover -s personal-swing/research_lab -p test_xray406_witness_acceptance.py -v
python -O -m unittest discover -s personal-swing/research_lab -p test_xray406_witness_acceptance.py -v
```

## Sonraki gerçek kabul

1. Aday commit'in tek ebeveyni en son gözlenen hedef SHA, değişen yollar yalnız resmi guard ve ledger olmalı. Ledger önceki girdilerin aynen korunduğunu, son payload'ların ledger'a bağlandığını ve işlem yetkisi olmadığını göstermeli. Staging olayını susturan commit işaretleri kabul edilmez.
2. Gerçek check, aynı aday SHA, `xray-477-required-ci`, GitHub Actions App 15368, doğru run/attempt ve success ile eşleşmeli. Yayıncı bir hata ya da yarışta korumalı hedefi değiştirmemeli. Zamanlama için normal CI süresini varsayma.
3. Üretim sonrası bağımsız GitHub okuması aynı SHA ve iki blob'u kapanış kesimine kadar görmeli. Kesim mevcut XNAS seans kapanışı artı 45 dakikadır. Mevcut guard'ın ilk yayın kontrolündeki 15 dakikalık tazelik sınırı bu aday kabulünde de korunur. Commit zamanı ilk görünürlük kanıtı değildir.
4. Geçiş önce sadece bu yazıcı için doğal çalışmada ölçülür. Aynı workflow içindeki ikinci doğrudan yazım, diğer aktif yazıcılar ve zamanlama bağımlılıkları ayrı doğrulanır. Ortak main kuralı, kırmızı PR reddi, yeşil PR kabulü, doğal bot sürekliliği ve geri dönüş kanıtları olmadan tamamlandı sayılmaz.
5. Otomatik 477 kapanış kartının doğal teslim kabulü ayrı kapıdır. Pilot başarıları otomatik kart teslimi veya iPhone cihaz onayı değildir.

İzolasyon ve yayından önce CI, geniş bir bot muafiyetine göre daha güçlü koruma sağlar. İnsan onaylı PR ise gözetimsiz yayınların zamanlama eşdeğeri değildir. Henüz üretim cutover kararı verilmemiştir. `FULL_FINAL=HOLD`, `EXECUTION=NONE`.
