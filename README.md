# LSA Trader Bot

Türkçe kontrol paneli bulunan **yalnızca simülasyon** uygulaması. Binance USDⓈ-M
Futures public verisiyle USDT teminatlı sürekli sözleşmeleri analiz eder.
Gerçek emir, hesap bağlantısı, API anahtarı veya Telegram entegrasyonu yoktur.
Strateji doğrulanmış değildir; herhangi bir kârlılık iddiası yoktur.

## Başlatma

### Mac'te kolay başlatma

Python 3.12 veya 3.13 kurulu olmalıdır. GitHub ZIP dosyasını açın ve
`Mac-Baslat.command` dosyasını çalıştırın. İzin sorunu yaşarsanız Terminal'e
`bash ` yazıp dosyayı Terminal'e sürükleyin ve Enter'a basın.
İlk çalıştırmada bağımlılıklar `.venv-mac/` içine yüklenir, ardından yerel panel
tarayıcıda açılır. Terminal penceresi açık kalmalıdır; Ctrl+C botu durdurur.
Yeni işlemler yine panelde Başlat onayını bekler. Tarayıcıda Binance'e erişmek,
Python'un tüm fiyat/mum uç noktalarına erişimini tek başına kanıtlamaz;
panelde veri yaşı ve tarama ilerlemesini kontrol edin.

### Komut satırı

Python 3.12 veya üstü gerekir. Depo kökünde:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m lsa serve
```

Windows'ta `.venv/bin/python` yerine `.venv\Scripts\python.exe` kullanılır.
Panel yalnızca yerel makinenin 8765 portunu dinler. Bot veri toplamaya başlar ama
**Başlat** düğmesine basılmadan yeni simülasyon pozisyonu açmaz. Veriler erişilemiyorsa
SAFE_MODE gösterir; örnek fiyat veya uydurulmuş işlem göstermez.

Kalıcı günlük: `data/journal.sqlite` (SQLite WAL). Yedek almak için süreç durdurulmalı
veya SQLite backup API kullanılmalıdır; çalışan veritabanını tek dosya kopyasıyla
yedeklemek güvenli değildir. `data/` Git'e dahil edilmez. Bakiyeyi sıfırlama düğmesi
özellikle eklenmedi; zarar kilidi panelden atlatılamaz.

## Ağ ve çalışma şekli

HTTPS erişimi gerekir:

- `fapi.binance.com`: zaman, sözleşmeler, OHLCV, book ticker, hacim ve funding.
- `api.binance.com`: yaklaşık TL karşılığı için USDT/TRY spot kuru.
- `fstream.binance.com`: TLS WebSocket kapanmış mum akışı (443 portu).
- Kurulum için `pypi.org` ve `files.pythonhosted.org`.

Miras alınan proxy ve CA ayarları korunur; TLS doğrulaması kapatılmaz. Ağ hatasında
canlı veri doğrulanmış sayılmaz. Binance'in bölgesel kısıtları varsa alternatif uç
noktalarla aşılmaz. Kur erişilemezse TL değeri gösterilmez; eski kur etiketlenir.
USDT/TRY, USD/TRY değildir; panelde TL tutarı yaklaşık değerdir.

Genel coin listesi ve REST veri mutabakatı 5 dakikalık döngüde yenilenir;
bu süre girişler için bir bekleme kilidi değildir. En fazla 150 sembol hacme göre
sıralanır. İlk çalıştırmada tarihçe ısınması tamamlanmadan ilgili coinde giriş aranmaz.
Yeni kapanmış mumlar WebSocket ile önbelleğe gelir ve analizi yeniden tetikler.
Hâlâ oluşmakta olan mumlar kullanılmaz. 1sa/4sa trend; 3/5/15/30dk giriş;
günlük bağlam değerlendirilir. Bağlantı yenilenince tekrar abone olunur;
mum boşluğu varsa REST mutabakatı tamamlanmadan o coinin adayı işleme alınmaz.

Geçerli adaylar her yeni REST fiyat güncellemesinde (normal koşullarda yaklaşık
2 saniye + istek gecikmesi) kontrol edilir. Uygun girişe gelmeyen adaylar süreleri
bitene veya yeni mum analizi onları geçersiz kılana kadar bekler. Aynı sinyal
kimliğiyle yeniden giriş yapılmaz. Başlat onayı ve bütün risk kontrolleri korunur.
Tam tick-by-tick veya sıfır gecikmeli işlem garantisi yoktur. Funding/kur istekleri
ayrı iş parçacığındadır ve fiyat takibini bekletmez. Panelde mum bağlantısı sayısı
ve bekleyen aday sayısı görünür. Fiyat güvenlik sınırı yine 15 saniyedir.

Paneli kapatmak ayrı çalışan Python sürecini durdurmaz. Bilgisayar kapanınca
çalışması için Python sürecinin kalıcı bir sunucuda çalışması gerekir. Bu depo
bulut geliştirme oturumunu 7/24 üretim sunucusuna dönüştürmez. Dış erişim için
kimlik doğrulamalı TLS reverse proxy veya SSH tüneli ve süreç gözetimi ayrıca
kurulmalıdır; mevcut yerel HTTP sunucusu internete açık yayın için tasarlanmamıştır.

## Araştırma araçları

Örnek (uzun sürebilir; komutlar burada gerçek veriyle çalıştırılmış sayılmaz):

```bash
.venv/bin/python -m lsa download --symbols BTCUSDT --start 2023-01-01 --end 2026-01-01
.venv/bin/python -m lsa backtest --symbols BTCUSDT --start 2023-01-01 --end 2026-01-01 --output data/research.json
```

İndirme 1dk yürütme mumlarını ve yedi analiz zaman aralığını aylık Parquet
dosyalarına kaydeder; tekrar indirme yinelenen mum oluşturmaz, çelişen veri reddedilir.
İndirme kesilirse aynı komut veriyi bozmaz, ancak başlangıçtan tekrar istek yapar.
24 ayın tamamını değerlendirmek için günlük EMA200 ısınması nedeniyle daha eski
veri gerekir. Yeni listelenen coinler yeterli geçmiş olmadan değerlendirilmez.

Replay: kronolojik üç walk-forward değerlendirme dilimi, son 183 günlük holdout
ve iki kat slippage/spread ile maliyet stresi üretir. İlk 365 gün ısınma/eğitim
alanıdır; optimizasyon yapılmaz. Geçmiş funding, anlık tarihsel likidite evreni,
gerçek miktar filtrelerinin tarihsel sürümleri ve emir defteri henüz replay'e bağlı
değildir. Bu nedenle araç sonuçları **strateji doğrulaması sayılamaz**; rapor bu
engelleri taşır. 300 işlem/24 ay/PF/expectancy/drawdown eşikleri koddadır fakat
henüz gerçek veri üzerinde değerlendirilmemiştir. Açık pozisyonlar veri sonunda
DATA_END olarak kapatılır. Gerçek Binance likidasyon motoru modellenmez.

## Dosyalar

- `docs/SPEC.md`: onaylanan kararlar, uygulama ayrıntıları ve tamamlanmamış işler.
- `lsa/market.py`: yalnızca public veri; `strategy.py`: deterministik analiz.
- `lsa/risk.py`: paper pozisyonlar, maliyetler, günlük ve toplam risk.
- `lsa/storage.py`, `reporting.py`: SQLite günlüğü ve performans.
- `lsa/engine.py`: tarama, fiyat izleme, SAFE_MODE ve manuel başlatma.
- `lsa/stream.py`: kapanmış mum abonelikleri, bağlantı yenileme ve doğrulama.
- `lsa/web.py`, `lsa/static/`: yerel kontrol paneli.
- `lsa/history.py`, `backtest.py`: Parquet ve sınırlı araştırma replay'i.

Strateji/konfigürasyon hash'i sinyallerde, SQLite'ta ve panelde saklanır.
Otomatik parametre optimizasyonu veya kendiliğinden kural değişikliği yoktur.

## Pozisyonlarda USDT tutarları

Açık pozisyonlarda coin adının yanında **Teminat (USDT)** ve **Pozisyon tutarı
(USDT)** gösterilir. Örneğin 6× kaldıraçlı 180 USDT pozisyon, 30 USDT teminat
kullanır. Bu tutarlar zarar sınırı değildir; stop riski ayrı hesaplanır.
Pozisyon tutarı giriş fiyatı × kalan miktardır, güncel fiyatla değerleme değildir.
TP1 sonrası kalan teminat ve tutar azalır; ilk giriş rakamları alt satırda korunur.
Komisyonlar teminat sütununa dahil değildir. Toplam kullanılan teminat üst kartta,
ilk giriş teminatı ve tutarı kapanan işlemler tablosunda da görünür. Bu alanlar
mevcut kayıtlardan hesaplanır; veritabanı sıfırlaması veya strateji değişikliği yoktur.

## Giriş grafiği ve formasyon benzerliği

Yeni simülasyon pozisyonu açılırken giriş zaman aralığının son 120 kapanmış mumu,
giriş anının alış/satış fiyatı, ilk giriş/stop/TP seviyeleri ve kullanılan tutarlar
SQLite'a pozisyon günlüğüyle aynı işlemde kaydedilir. **Giriş grafiği** düğmesi
açık ve kapanmış işlemlerde bu kaydı açar. **Yeni girişte grafiği göster** seçeneği
varsayılan olarak açıktır. Bu görünüm canlı grafik değildir; sonraki mumlar veya
TP1 sonrası taşınan stop giriş anının kaydını değiştirmez. Eski sürümde açılmış
işlemler için geçmişe dönük giriş grafiği uydurulmaz; kaydın olmadığı belirtilir.

Grafikte mumlar, hacim, ilk giriş/stop/TP seviyeleri ve isteğe bağlı şablon izdüşümü
gösterilir. Yanında en yakın klasik formasyonun şeması ve iki alternatif bulunur.
Karşılaştırma, kapanış fiyatlarının normalize edilmiş şekliyle **17 şablon**
arasında yapılır; son 24/40/60/90/120 mumdan en yakın pencere seçilir. Bu,
fotoğraflarla eğitilmiş bir model veya doğrulanmış formasyon tespiti değildir.
0–100 benzerlik puanı kazanma olasılığı değildir. Zayıf ve yakın sonuçlar ayrıca
etiketlenir; düz/yetersiz veride eşleşme zorlanmaz. Sarı izdüşüm gerçek destek veya
direnç çizgisi değildir. İşlem yönü ve hedefler bu şablonlardan çıkarılmaz.

Bayrak/flama, üçgen/kama, ikili/üçlü tepe-dip, OBO/TOBO, çanak ve fincan-kulp
şablonları vardır. Harmonik Fibonacci oranları, tekil mum formasyonları, hacimle
kırılım doğrulaması bu karşılaştırmanın kapsamında değildir. Modül sadece
açıklamadır; mevcut strateji, puanlama ve risk kurallarını etkilemez.
