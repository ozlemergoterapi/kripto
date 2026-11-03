"use strict";
const $ = id => document.getElementById(id);
const money = x => Number(x).toLocaleString("tr-TR", {minimumFractionDigits:2, maximumFractionDigits:2});
const price = x => x == null ? "—" : Number(x).toLocaleString("tr-TR", {maximumFractionDigits:8});
const pct = x => x == null ? "—" : `%${money(x * 100)}`;
const date = ts => new Date(ts * 1000).toLocaleString("tr-TR", {timeZone:"Europe/Istanbul"});
const esc = x => String(x ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function entryChartButton(p) {
  return p.chart_available ? `<br><button class="chart-button secondary" data-chart-id="${esc(p.id)}">Giriş grafiği ↗</button>` : '<br><span class="muted">Giriş grafiği kaydedilmemiş</span>';
}
let session = null;
let commandPending = false;
function toast(message) { $("toast").textContent = message; $("toast").style.display = "block"; setTimeout(() => $("toast").style.display = "none", 6000); }
function empty(columns, title, text) { return `<tr><td colspan="${columns}" class="empty"><strong>${esc(title)}</strong>${esc(text)}</td></tr>`; }
function render(s) {
  $("clock").textContent = new Date(s.server_time * 1000).toLocaleTimeString("tr-TR", {timeZone:"Europe/Istanbul"});
  const statuses = {SAFE_MODE:"Güvenli mod", PAUSED:"Başlat onayı bekleniyor", RUNNING:"Simülasyon çalışıyor"};
  $("status").textContent = statuses[s.status] || s.status;
  $("status-dot").className = "dot " + (s.status === "RUNNING" ? "" : "amber");
  $("data-age").textContent = s.data_age_seconds == null ? "Henüz canlı veri yok" : `Veri yaşı: ${s.data_age_seconds.toFixed(1)} sn`;
  $("notice").textContent = s.safe_reason || s.error || "SİMÜLASYON · Gerçek para kullanılmıyor. Strateji geçmiş veriyle henüz doğrulanmadı; puanlar kazanma olasılığı değildir.";
  $("start").disabled = commandPending || s.status === "SAFE_MODE" || s.status === "RUNNING" || s.daily_locked;
  $("equity").textContent = `${money(s.equity)} USDT`;
  $("try-equity").textContent = s.rate ? `≈ ${money(s.equity * s.rate.value)} TL${s.rate_stale ? " · eski kur" : ""}` : "TL kuru bekleniyor";
  $("daily-pnl").textContent = `${s.daily_pnl >= 0 ? "+" : ""}${money(s.daily_pnl)} USDT`;
  $("daily-pnl").className = "value " + (s.daily_pnl >= 0 ? "green" : "red");
  $("daily-limit").textContent = `${money(s.daily_loss_limit)} USDT`;
  $("position-count").textContent = s.positions.length;
  $("leverage-policy").textContent = s.config.max_leverage == null ? "İzole teminat · Uygulama kaldıraç tavanı yok" : `İzole teminat · En fazla ${s.config.max_leverage}×`;
  $("position-limit").textContent = ` / ${s.config.max_positions}`;
  $("initial-balance").textContent = `${money(s.initial_balance)} USDT`;
  $("margin-used").textContent = `Kullanılan teminat: ${money(s.used_margin_usdt)} USDT`;
  $("open-risk").textContent = `${money(s.open_risk)} USDT`;
  $("universe").innerHTML = `${s.universe_size}<small> / 150</small>`;
  $("scan-progress").textContent = s.scan.at ? `${s.scan.active ? "Taranıyor" : "Son tarama"}: ${s.scan.done}/${s.scan.total} · ${s.scan.errors} hata` : "Güncel veri ve ilk tarama bekleniyor";
  const monitor = s.entry_monitor;
  $("entry-status").textContent = monitor ? `Mum akışı: ${monitor.candles.connected}/${monitor.candles.required} · Bekleyen aday: ${monitor.pending}` : "Mum akışı bekleniyor";
  $("position-rows").innerHTML = s.positions.length ? s.positions.map(p => `<tr><td><b>${esc(p.symbol)}</b><br><span class="${p.side === "LONG" ? "green" : "red"}">${esc(p.side)} · ${esc(p.timeframe)}</span><br><button class="chart-button" data-chart-id="${esc(p.id)}" data-chart-mode="live">Canlı grafik ↗</button>${entryChartButton(p)}</td><td><b>${money(p.used_margin_usdt)}</b>${p.remaining < p.quantity ? `<br><span class="muted">Başlangıç: ${money(p.initial_margin_usdt)}</span>` : ""}</td><td><b>${money(p.remaining_notional_usdt)}</b>${p.remaining < p.quantity ? `<br><span class="muted">Giriş: ${money(p.entry_notional_usdt)}</span>` : ""}</td><td>${price(p.entry)}</td><td>${p.quote ? price((p.quote.bid + p.quote.ask) / 2) : "Veri bekleniyor"}</td><td>${price(p.stop)}${p.tp1_hit ? " · Başabaş" : ""}</td><td>${price(p.tp1)} / ${price(p.tp2)}</td><td>${price(p.remaining)} / ${p.leverage}×</td><td>${Math.floor((s.server_time - p.opened_at) / 60)} dk</td></tr>`).join("") : empty(9,"Henüz açık pozisyon yok", "Uygun koşul bulunmadan işlem açılmaz. Yeni işlemler için Başlat onayı gerekir.");
  $("candidates").innerHTML = s.candidates.length ? s.candidates.slice(-6).map(c => `<article class="signal"><b>${esc(c.symbol)}</b> <span class="${c.side === "LONG" ? "green" : "red"}">${esc(c.side)}</span> · ${c.score}/100 · ${esc(c.timeframe)}<p>${esc(c.reason)}</p><p>Giriş ${price(c.entry)} · Stop ${price(c.stop)} · TP ${price(c.tp1)} / ${price(c.tp2)}<br>Geçerlilik: ${date(c.expires_at)} · No: ${esc(c.id)}</p></article>`).join("") : '<div class="empty"><strong>Uygun giriş adayı yok</strong>Trend, momentum, hacim ve risk koşulları birlikte aranır.</div>';
  const m = s.metrics;
  const entries = [["Kapanan işlem",m.trades],["Kazanma oranı",pct(m.win_rate)],["Net kâr / zarar",`${money(m.net_pnl)} USDT`],["Profit factor",m.profit_factor == null ? "—" : money(m.profit_factor)],["Beklenti (R)",m.expectancy_r == null ? "—" : money(m.expectancy_r)],["Maksimum drawdown",pct(m.max_drawdown)],["Ortalama süre",m.average_minutes == null ? "—" : `${money(m.average_minutes)} dk`],["TP1 / TP2 / SL",`${pct(m.tp1_rate)} / ${pct(m.tp2_rate)} / ${pct(m.sl_rate)}`]];
  $("metrics").innerHTML = entries.map(([k,v]) => `<div class="metric"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join("");
  $("daily-rows").innerHTML = s.reports.daily.length ? s.reports.daily.slice(0,30).map(d => `<tr><td>${esc(d.day)}</td><td>${money(d.start_equity)}</td><td>${money(d.end_equity)}</td><td class="${d.net_pnl >= 0 ? "green" : "red"}">${money(d.net_pnl)}</td><td>${money(d.costs)}</td></tr>`).join("") : empty(5,"Günlük kayıt henüz yok","İlk güncel değerlemeyle kayıt başlayacak.");
  $("weekly").textContent = s.reports.weekly.map(w => `${w.week}: ${money(w.net_pnl)} USDT (${w.days} gün)`).join(" · ") || "Haftalık kayıt henüz yok.";
  $("closed-rows").innerHTML = s.closed.length ? s.closed.map(p => `<tr><td>${esc(p.symbol)}${entryChartButton(p)}</td><td>${esc(p.side)}</td><td>${money(p.initial_margin_usdt)}</td><td>${money(p.entry_notional_usdt)}</td><td class="${p.net >= 0 ? "green" : "red"}">${money(p.net)} USDT</td><td>${esc(p.exit_reason)}</td><td>${date(p.closed_at)}</td></tr>`).join("") : empty(7,"Henüz kapanan işlem yok","Kazanma oranı veya getiri iddiası yok.");
  $("events").innerHTML = s.events.map(e => `<div class="event"><time>${date(e.at)}</time><span class="${e.level === "ERROR" ? "red" : ""}">${esc(e.level)}</span><span>${esc(e.message)}</span></div>`).join("");
  window.LSACharts.observe(s);
  $("version").textContent = `LSA TRADER · ${s.config.version} · ${s.config_hash}`;
  $("rate-info").textContent = s.rate ? `1 USDT ≈ ${money(s.rate.value)} TL · ${s.rate.source} · ${date(s.rate.at)}${s.rate_stale ? " · GÜNCEL DEĞİL" : ""}` : (s.rate_error || "Kur bekleniyor");
}
async function refresh() {
  try {
    const r = await fetch("/api/state", {signal:AbortSignal.timeout(4000)});
    if (!r.ok) throw new Error("Sunucu hatası");
    render(await r.json());
  } catch (error) {
    $("status").textContent = "Panel bağlantısı kesildi";
    $("notice").textContent = "Sunucuya ulaşılamıyor. Ekrandaki değerler güncel olmayabilir; botun durumu doğrulanamıyor.";
    $("start").disabled = true;
  } finally { setTimeout(refresh, 1000); }
}
for (const action of ["start", "pause", "emergency"]) {
  $(action).addEventListener("click", async () => {
    if (action === "emergency" && !confirm("Tüm simülasyon pozisyonları için çıkış istensin ve yeni işlemler durdurulsun mu?")) return;
    commandPending = true;
    try {
      if (!session) session = (await (await fetch("/api/session")).json()).token;
      const r = await fetch("/api/control", {method:"POST", headers:{"Content-Type":"application/json", "X-LSA-Token":session}, body:JSON.stringify({action}), signal:AbortSignal.timeout(5000)});
      const body = await r.json(); toast(body.message || body.error);
    } catch (e) { session = null; toast("Komutun uygulandığı doğrulanamadı. Bağlantıyı ve sistem günlüğünü kontrol et."); }
    finally { commandPending = false; }
  });
}
refresh();
