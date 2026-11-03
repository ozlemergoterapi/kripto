"use strict";
// Entry snapshots stay immutable; live position charts use a separate endpoint.
window.LSACharts = (() => {
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const number = value => Number(value).toLocaleString("tr-TR", {maximumFractionDigits:8});
  const date = value => new Date(value*1000).toLocaleString("tr-TR", {timeZone:"Europe/Istanbul"});
  let generation = 0;
  const seen = new Set();
  let activeId=null, activeMode="entry", timer=null, overlayEnabled=false;

  function candleChart(s, overlay) {
    const bars = s.candles;
    const width=1100, height=450, left=18, right=900, top=24, bottom=332;
    const levels={...s.levels,...(s.mode==="live" && s.price!=null?{price:s.price}:{})};
    const all = [...bars.flatMap(c => [c.high,c.low]),...Object.values(levels)];
    const low=Math.min(...all), high=Math.max(...all), pad=Math.max((high-low)*.07,high*.0001);
    const y = v => bottom-(v-low+pad)/(high-low+2*pad)*(bottom-top);
    const step=(right-left-22)/bars.length;
    const x = i => left+(i+.5)*step;
    let out=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(s.symbol)} ${s.mode==="live"?"canlı":"giriş anındaki"} mum grafiği">`;
    for (let i=0;i<5;i++) {
      const yy=top+(bottom-top)*i/4;
      out+=`<line x1="${left}" y1="${yy}" x2="${right}" y2="${yy}" stroke="#25303d"/>`;
    }
    const best=s.pattern.best;
    if (best) {
      const start=x(best.window_start_index)-step/2;
      out+=`<rect x="${start}" y="${top}" width="${right-22-start}" height="${bottom-top}" fill="#e9ba6e" opacity=".035"/>`;
      if (overlay) {
        const points=best.anchors.map((v,i) => `${x(best.window_start_index+(best.window_length-1)*i/(best.anchors.length-1))},${y(best.price_low+v*(best.price_high-best.price_low))}`).join(" ");
        out+=`<polyline points="${points}" fill="none" stroke="#e9ba6e" stroke-width="2" stroke-dasharray="5 4" opacity=".8"/>`;
      }
    }
    const volume=Math.max(...bars.map(c=>c.volume),1);
    bars.forEach((c,i) => {
      const color=c.close>=c.open?"#6de3c1":"#f5828e";
      out+=`<line x1="${x(i)}" x2="${x(i)}" y1="${y(c.high)}" y2="${y(c.low)}" stroke="${color}"/><rect x="${x(i)-step*.32}" y="${Math.min(y(c.open),y(c.close))}" width="${Math.max(1,step*.64)}" height="${Math.max(1,Math.abs(y(c.open)-y(c.close)))}" fill="${color}" opacity="${c.forming?.55:1}"/>`;
      out+=`<rect x="${x(i)-step*.32}" y="${405-c.volume/volume*50}" width="${Math.max(1,step*.64)}" height="${c.volume/volume*50}" fill="${color}" opacity=".35"/>`;
    });
    const labels={entry:["GİRİŞ","#6de3c1"],stop:[s.mode==="live"?"GÜNCEL STOP":"İLK STOP","#f5828e"],tp1:["TP1","#86b9f2"],tp2:["TP2","#c2a5fb"],price:["FİYAT",s.price_stale?"#8999ac":"#e9ba6e"]};
    let previous=-100;
    Object.entries(levels).sort((a,b)=>y(a[1])-y(b[1])).forEach(([key,value]) => {
      const yy=y(value), labelY=Math.max(yy,previous+19);
      previous=labelY;
      const [name,color]=labels[key];
      out+=`<line x1="${left}" x2="${right}" y1="${yy}" y2="${yy}" stroke="${color}" stroke-dasharray="4 4" opacity=".6"/><path d="M${right},${yy} L${right+12},${labelY}" stroke="${color}" fill="none"/><text x="${right+16}" y="${labelY+4}" fill="${color}" font-size="11">${name} ${number(value)}</text>`;
    });
    out+=`<circle cx="${right-7}" cy="${y(s.levels.entry)}" r="4" fill="#6de3c1"/><text x="${left}" y="350" fill="#8999ac" font-size="10">Hacim</text>`;
    [0,Math.floor(bars.length/2),bars.length-1].forEach(i => {
      const label=new Date(bars[i].forming?bars[i].open_time:bars[i].close_time).toLocaleString("tr-TR",{timeZone:"Europe/Istanbul",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
      const anchor=i===0?"start":i===bars.length-1?"end":"middle";
      out+=`<text x="${x(i)}" y="430" text-anchor="${anchor}" fill="#8999ac" font-size="10">${esc(label)}</text>`;
    });
    return out+"</svg>";
  }

  function patternCard(pattern) {
    const best=pattern.best;
    const states={similar:"Görece yüksek geometrik benzerlik",ambiguous:"Birden fazla şablona benziyor",weak:"Zayıf benzerlik; belirgin formasyon yok",insufficient:"Yeterli veri yok"};
    let result=`<h3>Fotoğraflardaki yapılardan en yakın şablon</h3>`;
    if (!best) return result+`<p>${esc(states[pattern.status] || "Belirgin şekil bulunamadı")}</p>`;
    const points=best.anchors.map((v,i)=>`${20+340*i/(best.anchors.length-1)},${135-v*110}`).join(" ");
    result+=`<div class="pattern-heading"><strong>${esc(best.name)}</strong><span>${number(best.score)}/100 · geometrik benzerlik</span></div><p>${esc(states[pattern.status])}. Kazanma olasılığı değildir.</p><svg class="pattern-template" viewBox="0 0 380 155" role="img" aria-label="${esc(best.name)} referans şeması"><polyline points="${points}" fill="none" stroke="#e9ba6e" stroke-width="3"/></svg><p>Karşılaştırma: son ${best.window_length} kapanmış mum. Sarı bölge bu pencereyi gösterir.</p>`;
    if (pattern.alternatives.length) result+=`<p>Diğer yakın şablonlar: ${pattern.alternatives.map(v=>`${esc(v.name)} (${number(v.score)}/100)`).join(" · ")}</p>`;
    return result+`<details><summary>Bu eşleştirmenin sınırları</summary><p>${esc(pattern.note)}</p>${(pattern.limitations || []).map(v=>`<p>${esc(v)}</p>`).join("")}</details>`;
  }

  function render(s) {
    const live=s.mode==="live";
    const detailsOpen=$("chart-body").querySelector("details")?.open;
    $("chart-title").textContent=`${s.symbol} · ${s.side} · ${s.timeframe} ${live?"canlı grafik":"giriş grafiği"}`;
    $("chart-caption").textContent=`Giriş: ${date(s.captured_at)} · Son kapanmış mum: ${date(s.last_closed_at)} · No: ${s.id}`;
    const warnings=[];
    if (live) {
      if (s.price_stale) warnings.push("Fiyat güncel değil");
      if (s.candles_stale) warnings.push("Mum akışı güncel değil");
      if (s.history_gap) warnings.push("Mum tarihçesinde boşluk var");
      $("chart-status").textContent=`${warnings.length?warnings.join(" · "):"Canlı takip"} · Fiyat yaşı: ${s.quote_age_seconds==null?"—":s.quote_age_seconds.toFixed(1)+" sn"} · Mum akışı yaşı: ${s.candle_age_seconds==null?"—":s.candle_age_seconds.toFixed(1)+" sn"}${s.candles.some(c=>c.forming)?" · Son mum henüz kapanmadı":""}`;
      $("chart-status").className=warnings.length?"chart-warning":"green";
    } else {
      $("chart-status").textContent="Giriş anının sabit kaydı · Canlı fiyatlarla değiştirilmez";
      $("chart-status").className="muted";
    }
    $("chart-body").innerHTML=`<div class="entry-chart-svg">${candleChart(s,overlayEnabled)}</div><label class="chart-toggle"><input type="checkbox" id="chart-overlay" ${overlayEnabled?"checked":""}> Şablon izdüşümünü grafikte göster (tahmini)</label><div class="entry-chart-info"><div><h3>${live?"Pozisyonun güncel durumu":"Giriş anının kaydı"}</h3><p>${esc(s.signal_reason)}</p><p>${live?"Kalan":"Giriş"} teminatı: <b>${number(live?s.capital.used_margin_usdt:s.capital.initial_margin_usdt)} USDT</b> · İşlem tutarı: <b>${number(live?s.capital.remaining_notional_usdt:s.capital.entry_notional_usdt)} USDT</b> · ${s.leverage}×</p><p>${esc(s.note)}</p><p>${live?"Güncel stop bu görünümde hareket eder. Benzerlik hesabına yalnızca kapanmış mumlar alınır.":"Giriş seviyeleri sabittir; açık pozisyonda taşınan stop bu kaydı değiştirmez. Sonraki fiyatlar burada gösterilmez."}</p></div><div>${patternCard(s.pattern)}</div></div>`;
    const details=$("chart-body").querySelector("details");
    if (details) details.open=!!detailsOpen;
    $("chart-overlay").addEventListener("change",event=>{
      overlayEnabled=event.target.checked;
      $("chart-body").querySelector(".entry-chart-svg").innerHTML=candleChart(s,overlayEnabled);
    });
  }

  async function load(request) {
    let retry=activeMode==="live";
    try {
      const response=await fetch(`/api/${activeMode==="live"?"live-chart":"entry-chart"}/${encodeURIComponent(activeId)}`,{signal:AbortSignal.timeout(6000)});
      const body=await response.json();
      if (request!==generation) return;
      if (!response.ok) {
        if (response.status===410 || response.status===404) retry=false;
        throw new Error(body.error || "Grafik yüklenemedi");
      }
      render(body);
    } catch (error) {
      if (request!==generation) return;
      $("chart-status").textContent=error.message+ (retry?" · Yeniden deneniyor; ekrandaki eski değerler güncel olmayabilir.":"");
      $("chart-status").className="chart-warning";
      if (!$("chart-body").querySelector("svg")) $("chart-body").textContent=error.message;
    } finally {
      if (request===generation && retry) timer=setTimeout(()=>load(request),1000);
    }
  }

  async function open(id, scroll=true, mode="entry") {
    clearTimeout(timer);
    const request=++generation;
    activeId=id;
    activeMode=mode;
    overlayEnabled=false;
    $("entry-chart").hidden=false;
    $("chart-title").textContent=mode==="live"?"Canlı grafik yükleniyor…":"Giriş grafiği yükleniyor…";
    $("chart-caption").textContent="";
    $("chart-body").textContent="";
    $("chart-status").textContent="Veri alınıyor…";
    for (const view of ["live","entry"]) $("chart-"+view+"-tab").setAttribute("aria-pressed",String(view===mode));
    if (scroll) $("entry-chart").scrollIntoView({behavior:"smooth",block:"start"});
    await load(request);
  }

  function observe(state) {
    const fresh=state.positions.filter(p=>!seen.has(p.id));
    state.positions.forEach(p=>seen.add(p.id));
    if (fresh.length && $("chart-auto").checked) open(fresh.sort((a,b)=>b.opened_at-a.opened_at)[0].id,false,"live");
  }

  document.addEventListener("click",event=>{
    const button=event.target.closest("button[data-chart-id]");
    if (button) open(button.dataset.chartId,true,button.dataset.chartMode || "entry");
  });
  for (const view of ["live","entry"]) $("chart-"+view+"-tab").addEventListener("click",()=>{if(activeId)open(activeId,false,view);});
  $("chart-close").addEventListener("click",()=>{generation++;clearTimeout(timer);activeId=null;$("entry-chart").hidden=true;});
  return {open,observe};
})();
