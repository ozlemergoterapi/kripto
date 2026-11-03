# LSA Trader — şartname v0.3

Durum: Kullanıcının bu görüşmede onayladığı kapsam için simülasyon geliştirme sürümü.
Önceki "yalnızca sinyal / Telegram" metninin yerini aşağıdaki kararlar alır.

## Onaylanan ürün ve risk kararları

- Nihai hedef Binance otomatik işlem; ilk sürüm yalnızca gerçek veriyle paper işlem.
  Gerçek para ayrıca açık onay, ayrı emir adaptörü ve testnet doğrulaması gerektirir.
- Binance USDⓈ-M; USDT teminatlı PERPETUAL. LONG ve SHORT.
- Kullanıcının yeni onayıyla temiz simülasyon başlangıcı 1.000 USDT;
  tek işlem azami %2, toplam açık risk azami %4.
- En fazla 5 eşzamanlı pozisyon; kullanıcının son talebiyle simülasyondaki
  sabit 10× uygulama tavanı kaldırıldı. Kaldıraç teminat bütçesine göre dinamik;
  yalnızca izole teminat modeli. Binance'in coin/pozisyon bazlı gerçek tavanları
  sınırsız değildir ve bu paper modelinde henüz doğrulanmamaktadır.
- Gün başı varlığına göre günlük %6 kayıpta tüm pozisyonlardan çıkış ve yeni giriş kilidi.
  Açık P&L ve maliyetler dahildir. Ani fiyat hareketlerinde sınır aşılabilir.
- Türkiye saatiyle 00.00 yeni günlük baz; günlük ve haftalık kayıtlar.
- EMA50/200 trend (1sa/4sa), RSI momentum, ATR14, hacim ve fiyat yapısı.
  3/5/15/30dk giriş değerlendirmesi, günlük yön bağlamı. Yalnızca kapanmış mumlar.
- TP1 1R: %50 çıkış, kalan stopu maliyet karşılayan başabaş seviyesine taşıma.
  TP2 2R: kalan çıkış. Stop ve hedefler ATR/piyasa yapısına göre.
- Sinyal ömrü azami 10 dakika; pozisyon azami 4 saat.
- En fazla 150 likit sözleşme; 7/24 veri/pozisyon takibi. Coin evreni ve REST
  mutabakatı 5 dakikada bir; giriş adayları her fiyat güncellemesinde kontrol edilir.
  Yeni kapanmış mumlar WebSocket ile analizi tetikler (kullanıcının sürekli giriş
  takibi talebi). Mum kapanışı ve risk kuralları değişmez.
- 15 saniye güncel veri yoksa SAFE_MODE ve çıkış isteği. Eski fiyatla hayali çıkış yok.
- Yeniden açılışta Başlat onayı gerekir; mevcut paper pozisyonların risk yönetimi sürer.
- Acil durdur: yeni girişleri durdurur ve tüm pozisyonların kapatılmasını ister.
- Türkçe bilgisayar paneli; USDT + yaklaşık güncel TL; Telegram yok.
- Bot kuralları kendi kendine değiştirmez. Puan 0–100; olasılık değildir.
- Başlangıç maliyetleri: her yönde %0,05 komisyon, minimum %0,02 slippage;
  canlı spread alış/satış fiyatına gömülüdür. Funding ayrı kaydedilir.
- Doğrulama hedefi: 24+ ay veri, walk-forward + bağımsız son 6 ay holdout,
  en az 300 değerlendirme işlemi, expectancy > 0, PF >= 1,20, drawdown <= %15,
  maliyet stresi. Geçmiş sonuç gelecek getiri garantisi değildir.

## v0.1 uygulama ayrıntıları (optimize edilmemiş başlangıç değerleri)

Bunlar başarıya göre seçilmemiş, açıkça sürümlenmiş araştırma varsayımlarıdır.
Canlı emir verme izni veya kanıtlanmış strateji anlamına gelmez.

- 24sa quote hacmi >= 50 milyon USDT; spread <= %0,10.
- Her zaman aralığında en az 220 kesintisiz, geçerli mum; EMA için son 260 mum.
- 1sa/4sa fiyat > EMA50 > EMA200 ve yükseliş yapısında LONG; tersinde SHORT.
  Yapı: son kapanış önceki 5 mumun tepesini/dibini aşar veya son mumun dibi/tepesi
  daha önceki 5 mumun dip/tepesine göre yükselir/düşer.
- Giriş: önceki 20 mumun kırılımı veya EMA20'ye dokunup trend yönünde kapanış;
  LONG RSI 50–70, SHORT 30–50; son hacim önceki 20 ortalamasının en az 1,2 katı.
- Puan: trend/yapı 50, kırılım 15 veya geri çekilme 10, hacim 10 (>=1,5× ise 15),
  momentum 10, günlük EMA50 bağlamı uyumluysa 10. Eşik 75; en yüksek güncel aday seçilir.
- Stop mesafesi en az 1,5 ATR; son 6 mum swing + 0,1 ATR tamponu da hesaba katılır.
  Mesafe 3 ATR'yi aşarsa sinyal reddedilir.
- Giriş fiyatı sinyal fiyatından 0,25 ATR'den fazla uzaklaşırsa işlem açılmaz.
- Aynı yönlü pozisyonlarda 15dk ortak zamanlı en fazla 96 getirinin Pearson
  korelasyonu >= 0,80 ise giriş reddedilir; 48 ortak örnek yoksa da reddedilir.
- Pozisyon miktarı stop, komisyon ve varsayılan stop slippage'ıyla hesaplanır.
  Borsa LOT_SIZE ve MIN_NOTIONAL filtreleri giriş ve yarım çıkışta uygulanır.
  En düşük uygun kaldıraç, pozisyon başına yaklaşık varlığın pozisyon sayısı
  tavanına bölünmesiyle oluşan teminat bütçesiyle seçilir (şimdi beşte biri);
  uygulama tavanı ayrıca tanımlanmışsa o tavan aşılmaz. Gerçek likidasyon hesabı yoktur;
  yaklaşık likidasyon mesafesine %1 tampon bırakılır.
- Günlük kilit ertesi gün açılır; ancak yeniden Başlat gerekir. Sayacın sıfırlanması
  tek başına işlem açtırmaz. Mevcut pozisyonlar sırf gece yarısı diye kapanmaz.

## Doğruluk ve çalışma sınırları

- Stop emirleri bu sürümde simülasyondur. Binance'te gerçek koruyucu emir yoktur.
- Veri yokken çıkış fiyatı bilinmez; açık pozisyon çıkış bekler. İlk geçerli fiyatta
  çıkış simüle edilir. Bu arada zarar büyüyebilir. Eski değerleme panelde eskilik yaşıyla görünür.
- Fiyat güncellemesi public REST polling ile yaklaşık 2 saniye + ağ gecikmesi;
  kapanmış mumlar public WebSocket üzerinden alınır. İlk tarihçe, boşluk onarımı
  ve düzenli veri mutabakatı REST ile yapılır. Süresi dolan, yeni mumla geçersiz
  kalan ve daha önce işleme girilmiş adaylardan yeni pozisyon açılmaz. Başlat
  öncesi adaylar saklanabilir ama emir simülasyonu yapılamaz.
- 150 coin × yedi zaman aralığı tek anda değil, hız bütçesi içinde sırayla taranır.
  Bir coin veya zaman aralığı hatalıysa o coin için yeni işlem yoktur.
- SQLite ledger her değişimde atomik kaydedilir; process crash'te Başlat durumu geri yüklenmez.
- Funding public geçmiş endpoint'inden periyodik alınır ve event kimliğiyle tek kez uygulanır.
  Son iki dakikada kapanmış işlemlere geç yayınlanan funding de işlenebilir.
  Daha uzun kesintide eski kapanmış işlemlerin funding mutabakatı henüz eksiktir.
- Günlük baz gece yarısı sonrası ilk geçerli değerlemedir; tam 00.00 fiyatı
  alınamamışsa bu örnekleme farkı olabilir. Kesinti boyunca günlük kayıt tamamlanamaz.
- Trade metrikleri kapanan işlemlere aittir; drawdown açık P&L'li örneklenmiş varlıktan
  hesaplanır. TP1 sonrası SL ile kapanış hem TP1 hem SL sayılır. Daily-limit/emergency
  çıkışları SL oranına eklenmez, çıkış nedeni ayrı saklanır.
- Günlük net sonuç varlık değişimidir; açık pozisyonu kapsar. Komisyon/funding maliyet
  sütunu nettir, funding geliri negatif maliyet olabilir. Spread/slippage P&L'ye gömülüdür.

## Yayına geçmeden tamamlanacak işler

1. Bu ortamda Binance domain erişimi ve gerçek veriyle uçtan uca simülasyon doğrulaması.
2. Tarihsel funding, point-in-time likidite evreni, delist ve yeni listeleme etkileri,
   gerçek filtreler ve hassas fiyat/miktar yuvarlama ile backtest'i tamamlama.
3. Gerçek geçmiş veriyle walk-forward, holdout ve maliyet stresi; 300 işlem ve
   tüm kabul eşikleri. Şu anda hiçbir getiri/doğruluk sonucu üretilmedi.
   Araştırma replay'i henüz v0.2 sürekli aday denemelerini modellemiyor; eski
   replay sonuçları bu yürütme davranışını doğrulamaz.
4. Binance testnet emir adaptörü, idempotent client order IDs, emir/pozisyon mutabakatı,
   reduce-only çıkışlar, exchange-side stoplar, funding ve likidasyon doğrulaması.
5. Sürekli sunucu, kimlik doğrulama/TLS, süreç gözetimi, yedekleme ve kesinti testleri.
6. Kullanıcının ayrıca açık onayı olmadan gerçek para modu eklenmeyecek/açılmayacak.
