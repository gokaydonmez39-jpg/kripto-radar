# XRAY #406 — Yalıtılmış GitHub App giriş pilotu

## Kanıt ve sınır

Read-only preflight run [43583838228](https://github.com/gokaydonmez39-jpg/kripto-radar/actions/runs/43583838228) geçti; App işi kapalıyken atlandı. Hiçbir üretim ayarı bu pilotla değiştirilmez. Paylaşımlı main kuralına bypass eklenmez. App'in repository Contents:write yetkisi dal düzeyinde sınırlı değildir. Workflow dal kısıtları, environment kısıtı ve credentials'ı ayrı tutmak zorunlu pilot güvenceleridir. Pilot App'i başka depoya veya hesaba kurma.

## Sahip kurulumu

1. GitHub Developer settings → GitHub Apps altında yalnız bu hesapta kurulabilen özel bir App kaydet. Webhook'u devre dışı bırak. Repository permissions altında yalnız Contents: Read and write seç; GitHub'ın zorunlu Metadata: Read izni dışında Actions, Checks, Workflows ve Administration yazma izni verme.
2. App'i Only select repositories ile yalnız `kripto-radar` deposuna kur. Ruleset veya branch protection muafiyeti verme.
3. Repo Settings → Environments altında `xray-406-isolated-app-pilot` oluştur. Deployment branches and tags ayarını Selected branches and tags yap ve Branch türü olarak yalnız tam `xray-406-token-ingress-probe-20261114` dalına izin ver. Wildcard, tag, main veya bütün korumalı dallar kullanma. Bir insan onayı eklenirse bunun ilk canlı pilot olduğunu, gözetimsiz üretim kabulü olmadığını kaydet.
4. O environment içinde GitHub App Client ID'yi `XRAY406_APP_CLIENT_ID` değişkenine, App private key PEM'ini `XRAY406_APP_PRIVATE_KEY` secret'ına doğrudan GitHub arayüzünden koy. Anahtarı hiçbir sohbete, loga, commit'e veya repo-geneli secret'a yazma.
5. Yalnız sınırları yeniden doğruladıktan sonra repository seviyesindeki Actions değişkeni `XRAY406_APP_PILOT_ARMED` değerini geçici olarak `1` yap. Bu değişken gizli anahtar değildir. Hazırlık run'ı `43583838228` için **Re-run all jobs** bir kez kullan. Önceki EOD veya üretim işlerini rerun etme.

## Gerçek kabul

- Başlangıç staging: `46385339dfda1b30c04626c5995b6ce2e5b9c632`. Korumalı hedef: `7d2cc87620ceb9fc4f65ae09e7e482121b5abf1c`. Herhangi bir drift varsa pilotu çalıştırma.
- Ingress makbuzu gerçek App kimliğini ve tek marker commit SHA'sını verir. Ingress'in kendi SUCCESS sonucu yeterli değildir.
- Yeni run'ın olayı `push`, dalı `xray-406-ci-staging-probe-20261114`, actor'u App bot'u olmalı. Run head SHA, marker commit SHA'sı ile birebir eşleşmeli. Gerekli check adı `xray-477-required-ci`, kaynak GitHub Actions App 15368, sonuç success. Ayrı yayım job'u aynı SHA'yı korumalı hedefe yazmalı.
- Bağımsız API okumaları staging ve korumalı hedefin aynı tam SHA'sını, sentetik blob kimliğini ve ortak main/ruleset'in bu işlemden etkilenmediğini doğrulamalı. Korumalı test dalı sonucu, üretim yazıcılarının sürekliliği değildir.
- Başarılı, başarısız veya sonucu belirsiz ilk denemeden sonra arming değişkenini kapat. Belirsiz write'ı tekrar etme. GitHub App pilotu bittiğinde artık gerekmeyen test anahtarını GitHub üzerinden iptal et. Main'e kural ekleme, mevcut yazıcı yollarını değiştirme.

[App kurulumu](https://docs.github.com/en/apps/using-github-apps/installing-your-own-github-app) · [Environment kısıtları](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) · [Workflow rerun](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
