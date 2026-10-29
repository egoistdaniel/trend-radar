#!/usr/bin/env python3
"""Trend Radar - 무료/키 불필요. 실행하면 docs/index.html 을 만든다.
소스: Google News RSS(도메인×지역), Hacker News 프론트페이지.
'새로 뜸' 점수 = 오늘 등장한 헤드라인 수 / (과거 평균 + 1). 과거 기록은 history.json 에 누적."""
import json, re, math, html, datetime as dt, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

# ── 여기만 고치면 됩니다: 도메인 → 지역별 검색어 ─────────────────────────
DOMAINS = {
    "뷰티": {"US": "beauty skincare", "KR": "뷰티 신제품", "JP": "美容 コスメ"},
    "식음료": {"US": "food beverage trend", "KR": "식음료 신제품", "JP": "新商品 飲料"},
    "AI·테크": {"US": "AI consumer app", "KR": "AI 서비스 출시", "JP": "生成AI サービス"},
    "모빌리티": {"US": "electric vehicle", "KR": "전기차 신차", "JP": "EV 新型"},
}
REGIONS = {  # 지역 → (hl, gl, ceid)
    "US": ("en-US", "US", "US:en"),
    "KR": ("ko", "KR", "KR:ko"),
    "JP": ("ja", "JP", "JP:ja"),
}
KEEP_DAYS, MIN_COUNT, TOP_N = 14, 3, 8
STOP = set("the and for with that this from are was will new has have its into over after about more than your you "
           "says say how why what who when out not but can all one two".split())
OUT, HIST = Path("docs/index.html"), Path("history.json")
UA = {"User-Agent": "Mozilla/5.0 (trend-radar personal)"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
        return r.read()


def news(query, region):
    hl, gl, ceid = REGIONS[region]
    q = urllib.parse.quote(f"{query} when:1d")
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
    try:
        items = ET.fromstring(get(url)).iter("item")
        return [(i.findtext("title", ""), i.findtext("link", "")) for i in items][:40]
    except Exception as e:
        print("feed fail", region, query, e)
        return []


def hn():
    try:
        d = json.loads(get("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=15"))
        return [(h["title"], h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}") for h in d["hits"]]
    except Exception as e:
        print("hn fail", e)
        return []


def tokens(title, skip):
    title = re.sub(r"\s[-|–]\s[^-|–]+$", "", title)  # 끝의 매체명 제거
    out = set(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}|[가-힣]{2,}", title))
    for run in re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]{2,}", title):  # 일/중: 2글자 조각
        out |= {run[i:i + 2] for i in range(len(run) - 1)}
    return {t for t in out if t not in STOP and t not in skip}


def main():
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    hist = json.loads(HIST.read_text()) if HIST.exists() else {}
    past = [hist[d] for d in sorted(hist) if d != today][-KEEP_DAYS:]
    sections, snap = [], {}
    feeds = {d: [(r, *x) for r, q in rs.items() for x in news(q, r)] for d, rs in DOMAINS.items()}
    feeds["Hacker News"] = [("US", *x) for x in hn()]
    for dom, rows in feeds.items():
        skip = {w.lower() for q in DOMAINS.get(dom, {}).values() for w in re.findall(r"\w+", q)}
        cnt, ex = Counter(), {}
        for reg, title, link in rows:
            for t in tokens(title, skip):
                cnt[t] += 1
                ex.setdefault(t, []).append((reg, title, link))
        snap[dom] = {t: c for t, c in cnt.items() if c >= 2}
        scored = []
        for t, c in cnt.items():
            if c < MIN_COUNT and dom != "Hacker News":
                continue
            base = [p.get(dom, {}).get(t, 0) for p in past]
            avg = sum(base) / len(base) if base else 0
            regs = {r for r, _, _ in ex[t]}
            scored.append((c / (avg + 1) * math.log(1 + c) * (1 + 0.3 * (len(regs) - 1)), t, c, avg, regs))
        scored.sort(reverse=True)
        sections.append((dom, scored[:TOP_N], ex))
    hist[today] = snap
    HIST.write_text(json.dumps({d: hist[d] for d in sorted(hist)[-KEEP_DAYS:]}, ensure_ascii=False))
    render(today, len(past), sections)


def render(today, ndays, sections):
    note = "" if ndays >= 3 else f"<p class='note'>누적 기록 {ndays}일: 3일 전까지는 '새로움'이 아니라 단순 빈도에 가깝습니다.</p>"
    body = []
    for dom, top, ex in sections:
        cards = []
        for score, t, c, avg, regs in top:
            lines = "".join(f"<li><span>{r}</span><a href='{html.escape(l)}' target='_blank' rel='noopener'>{html.escape(ti)}</a></li>"
                            for r, ti, l in ex[t][:3])
            cards.append(f"<div class='card'><b>{html.escape(t)}</b><small>점수 {score:.1f} · 오늘 {c}건 · 평소 {avg:.1f} · {'/'.join(sorted(regs))}</small><ul>{lines}</ul></div>")
        body.append(f"<h2>{html.escape(dom)}</h2><div class='grid'>{''.join(cards) or '<p>데이터 없음</p>'}</div>")
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Trend Radar {today}</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--card:#f4f4f5;--mut:#666;--ac:#2563eb}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--card:#1d1d1f;--mut:#9a9a9a;--ac:#7aa2ff}}}}
body{{font:15px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1100px;margin:0 auto;padding:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}}
.card{{background:var(--card);border-radius:10px;padding:12px}}.card small{{display:block;color:var(--mut)}}
ul{{padding-left:0;list-style:none;margin:8px 0 0}}li{{margin:4px 0;font-size:13px}}li span{{color:var(--mut);margin-right:6px}}
a{{color:var(--ac);text-decoration:none}}.note{{color:var(--mut)}}</style></head><body>
<h1>Trend Radar</h1><p class="note">{today} (UTC) 기준 · 점수는 오늘 헤드라인 수 대비 평소 평균이 얼마나 급증했는지를 나타냅니다.</p>
{note}{''.join(body)}</body></html>"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
