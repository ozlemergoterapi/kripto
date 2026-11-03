# Geliştirme doğrulaması — 2026-11-03

Bu kayıt strateji performans raporu değildir.

## Pozisyon tutarı gösterimi

Açık pozisyonlarda ilk/kalan teminat ve giriş fiyatıyla ilk/kalan pozisyon
büyüklüğü USDT olarak eklendi. Kapanan işlem geçmişinde ilk tutarlar korunur.
LONG ve SHORT için gerçek paper kısmi çıkış → SQLite geri yükleme → kapanış
akışında tutarların korunması test edildi. Toplam **41 test geçti**; JavaScript
sözdizimi kontrolü başarılı. Bu değişiklik risk hesaplarını ve stratejiyi değiştirmez.

## v0.2 sürekli aday takibi

Son kontrol: **39 test geçti**; Python derleme ve JavaScript sözdizimi kontrolleri başarılı.

- Kapanmış mum stream'i analizi tetikler; açık mumlar kullanılmaz. İlk REST
  tarihçe ısınması ve 5 dakikalık mutabakat devam eder.
- Fiyat güncellemesi geldiğinde geçerli adaylar yeniden kontrol edilir; sıradaki
  genel tur beklenmez. Funding ve kur istekleri fiyat döngüsünden ayrıldı.
- Paused → Başlat sonrası mevcut adaydan giriş, fiyat geri gelince yeniden
  deneme, tek kimlikle tek giriş, süre aşımı, eski funding engeli, mum analizi
  yarış durumu, stream yeniden aboneliği ve çelişkili mum testleri eklendi.
- WebSocket aboneliği/yeniden bağlantısı sentetik taşıyıcıyla, arka plan giriş
  yönetimi sahte piyasa adaptörüyle test edildi. Bu testler Binance canlı
  bağlantı veya strateji performans doğrulaması değildir.
- Bulut ortamının bölgesel Binance 451 engeli devam ettiğinden gerçek WebSocket
  akışı burada doğrulanmadı; kullanıcının Mac'inde bağlantı sayısı, kapanış
  olayları ve giriş takibi ayrıca gözlemlenmelidir.
- Araştırma backtest'i henüz v0.2 aday yürütmesiyle eşleştirilmedi; sonuçları
  bu davranışın doğrulaması sayılamaz. Gerçek emir modu hâlâ yoktur.

## Sonraki düzeltme: veri yaşı

Mac'te kur ve coin taraması çalışırken en eski coin fiyatının global veri yaşına
atanması yanlış SAFE_MODE tetikleyebiliyordu. Global veri yaşı artık en yeni
geçerli borsa olayını kullanır. Açık pozisyonların her birinin fiyatı watchdog
tarafından ayrıca kontrol edilir; 15 saniye sınırı değişmedi. HTTP yanıtının
gelmesi eski borsa verisini güncel saydırmaz. Bu üç senaryo için regresyon
testleri eklendi; toplam **29 test geçti**. Bu düzeltmenin kullanıcının Mac'inde
canlı uçtan uca doğrulaması henüz yapılmadı.

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
