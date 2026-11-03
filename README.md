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
- Kurulum için `pypi.org` ve `files.pythonhosted.org`.

Miras alınan proxy ve CA ayarları korunur; TLS doğrulaması kapatılmaz. Ağ hatasında
canlı veri doğrulanmış sayılmaz. Binance'in bölgesel kısıtları varsa alternatif uç
noktalarla aşılmaz. Kur erişilemezse TL değeri gösterilmez; eski kur etiketlenir.
USDT/TRY, USD/TRY değildir; panelde TL tutarı yaklaşık değerdir.

Tarama 5 dakikalık UTC sınırlarında yapılır; ilk veri geldiğinde ilk tur başlar.
En fazla 150 sembol hacme göre sıralanır. Veri istekleri hız sınırlıdır;
taramanın tamamlanması zaman alır ve ilerleme/hatalar panelde gösterilir.
Canlı alış/satış fiyatları yaklaşık 2 saniyede bir public REST ile alınır;
bu sürüm tick-by-tick WebSocket terminali değildir. Mum analizi sadece kapanmış
mumları kullanır. 1sa/4sa trend; 3/5/15/30dk giriş; günlük bağlam değerlendirilir.

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
- `lsa/web.py`, `lsa/static/`: yerel kontrol paneli.
- `lsa/history.py`, `backtest.py`: Parquet ve sınırlı araştırma replay'i.

Strateji/konfigürasyon hash'i sinyallerde, SQLite'ta ve panelde saklanır.
Otomatik parametre optimizasyonu veya kendiliğinden kural değişikliği yoktur.
