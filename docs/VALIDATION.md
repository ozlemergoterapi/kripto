# Geliştirme doğrulaması — 2026-11-03

Bu kayıt strateji performans raporu değildir.

## Çalıştırılan kontroller

- Python 3.12.14; sabit sürümlü gereksinimlerin kurulumu ve tekrar kurulumu başarılı.
- `python -m pytest -q`: **26 passed**.
- `python -m pip check`: kırık bağımlılık yok.
- `python -m compileall -q lsa`: başarılı.
- `node --check lsa/static/app.js`: başarılı.
- Yerel HTTP: panel, state, session, control ve health test edildi; oturumsuz
  kontrol isteği 403, acil durdur isteği başarılı.
- Chromium 155: 1440×1100 masaüstü ve 390×844 ekran taşma kontrolü başarılı;
  SAFE_MODE görünümü, 100 USDT bakiye, veri yokken Başlat kilidi ve Acil durdur
  düğmesinin sunucudan başarılı yanıt alması doğrulandı. JavaScript exception yok.
- Sunucu durdurulup son kodla yeniden başlatıldı; SQLite açılışı, health ve
  SAFE_MODE state yanıtı doğrulandı. Yeniden açılışta otomatik işlem başlamadı.

## Test verisinin kapsamı

Risk, gösterge, sinyal ve replay birim testleri deterministik sentetik fixture
verileri kullanır. Bunlar kullanıcı oturumuna fiyat/işlem olarak aktarılmadı.
Replay testinde gerçekten en az bir işlem açılıp kapanması kontrol edildi;
bu sonuç gerçek piyasa başarısını ölçmez.

## Çalıştırılamayan kontroller

- Binance `/fapi/v1/time` isteği ağ vekilinden CONNECT 403 aldı. Çalışan ortamın
  etkin custom-domain listesi hâlâ boş. Bu nedenle gerçek piyasa verisi, 150
  coin taraması, funding ve TL kuru uçtan uca doğrulanamadı.
- `fapi.binance.com` ve `api.binance.com` ağ taslağına eklendi; bu kayıt
  runtime'a uygulandığı veya ortamın yayımlandığı anlamına gelmez.
- Kurulum betiği ve başlangıç talimatları yapılandırma taslağına kaydedildi.
- Gerçek tarihsel veri indirilmedi; 24 ay/300 işlem/holdout/maliyet sonrası başarı
  değerlendirmesi yapılmadı. Backtest araştırma aracındaki kalan model eksikleri
  SPEC.md ve README.md içinde listelenmiştir.
- Gerçek para, emir API'si, testnet emirleri ve sürekli sunucu dağıtımı yapılmadı.

Sonraki engel: ortam ayarlarında ağ taslağını gözden geçirip kaydetmek ve ortamı
yayımlamak. Sonrasında gerçek erişim yeniden denenmeli; erişim açılmadan
canlı piyasa akışı veya strateji doğrulaması iddia edilmemeli.
