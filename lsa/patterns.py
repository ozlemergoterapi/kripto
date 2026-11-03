"""Descriptive shape comparison only; never imported by the trading strategy.

Templates describe the formation, not the future target arrows in reference art.
Scores are normalized shape distances, not calibrated probabilities.
"""
from math import sqrt

TEMPLATES = {
    "Boğa bayrağı": [0, 1, .66, .9, .56, .8, .46, .7],
    "Boğa flaması": [0, 1, .45, .88, .55, .77, .62, .7],
    "Yükselen üçgen": [0, 1, .2, 1, .4, 1, .6, 1],
    "Simetrik üçgen": [1, 0, .85, .15, .73, .27, .62, .38, .55],
    "Yükselen kama": [0, .5, .26, .68, .49, .83, .7, .95, .86, 1],
    "İkili tepe": [0, 1, .4, .98, .4],
    "Üçlü tepe": [0, 1, .4, .98, .4, 1, .35],
    "Omuz baş omuz": [0, .65, .25, 1, .25, .65, .2],
    "Çanak": [1, .7, .35, .1, 0, .1, .35, .7, 1],
    "Fincan kulp": [1, .5, .15, 0, .15, .5, 1, .7, .85],
}
for original, name in [("Boğa bayrağı", "Ayı bayrağı"), ("Boğa flaması", "Ayı flaması"),
                       ("Yükselen üçgen", "Alçalan üçgen"), ("Yükselen kama", "Alçalan kama"),
                       ("İkili tepe", "İkili dip"), ("Üçlü tepe", "Üçlü dip"),
                       ("Omuz baş omuz", "Ters omuz baş omuz")]:
    TEMPLATES[name] = [1-v for v in TEMPLATES[original]]


def resample(values, count=64):
    result = []
    for i in range(count):
        x = i * (len(values)-1) / (count-1)
        left = int(x)
        right = min(left+1,len(values)-1)
        result.append(values[left] + (values[right]-values[left]) * (x-left))
    return result


def compare_shapes(candles):
    valid = len(candles) >= 24 and all(c.valid() for c in candles)
    if not valid:
        return {"version":"shape-v1", "status":"insufficient", "best":None, "alternatives":[],
                "note":"En az 24 geçerli kapanmış mum gerekli.", "is_trade_signal":False}
    candidates = {}
    for size in (24, 40, 60, 90, 120):
        if len(candles) < size:
            continue
        closes = [c.close for c in candles[-size:]]
        low, high = min(closes), max(closes)
        if high-low <= max(high * 1e-6, 1e-12):
            continue
        normalized = resample([(v-low)/(high-low) for v in closes])
        for name, anchors in TEMPLATES.items():
            template = resample(anchors)
            distance = sqrt(sum((a-b)**2 for a,b in zip(normalized,template))/len(template))
            score = round(max(0, 100 * (1 - 3 * distance)),1)
            item = {"name":name, "score":score, "window_length":size,
                    "window_start_index":len(candles)-size, "anchors":anchors,
                    "price_low":low, "price_high":high}
            if name not in candidates or candidates[name]["score"] < score:
                candidates[name] = item
    ordered = sorted(candidates.values(), key=lambda c:(-c["score"],c["name"]))
    best = ordered[0] if ordered else None
    status = "weak"
    if best and best["score"] >= 75:
        status = "ambiguous" if len(ordered)>1 and best["score"]-ordered[1]["score"] < 6 else "similar"
    return {"version":"shape-v1", "status":status, "best":best,
            "alternatives":ordered[1:3], "is_trade_signal":False,
            "note":"Geometrik şablon benzerliği; formasyon/kırılım doğrulaması veya kazanma olasılığı değildir.",
            "limitations":["Yalnızca kapanış fiyatı şekli karşılaştırılır; hacim ve boyun çizgisi doğrulanmaz.",
                           "Harmonik Fibonacci oranları ve tekil mum formasyonları bu eşleştirmede yoktur.",
                           "En yakın şablon zayıf veya belirsiz olabilir; yön ve hedef çıkarılmaz."]}
