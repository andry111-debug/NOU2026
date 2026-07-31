# -*- coding: utf-8 -*-
"""
Разведка каталога ЕМИСС/Fedstat: ID показателей под пункты роадмапа
через поисковый endpoint /indicators/search?searchText=...

Выход (в git): data/emiss_indicator_candidates.csv (need_id, query, indicator_id, title).
"""
from __future__ import annotations

import re
import ssl
import sys
import time
import urllib.parse
import urllib.request as u
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
OUT_CSV = APP / "data" / "emiss_indicator_candidates.csv"

QUERIES = [
    ("D09", "индекс цен производителей промышленных товаров"),
    ("D10", "производство пищевых продуктов"),
    ("D10", "продукция сельского хозяйства"),
    ("D11", "среднедушевые денежные доходы населения"),
    ("D11", "среднемесячная начисленная заработная плата"),
    ("D12", "уровень безработицы"),
    ("D13", "численность постоянного населения"),
    ("D20", "коллективных средств размещения"),
    ("D22", "число родившихся"),
    ("D22", "число умерших"),
    ("D24", "численность населения по полу и возрасту"),
]

SEARCH = "https://www.fedstat.ru/indicators/search?searchText={q}"


def log(*a):
    print(*a, flush=True)


def main() -> int:
    ctx = ssl._create_unverified_context()
    op = u.build_opener(u.HTTPSHandler(context=ctx), u.HTTPCookieProcessor())
    hdr = {"User-Agent": "Mozilla/5.0 nou2027-research", "Accept-Language": "ru"}

    rows = []
    seen: set[tuple[str, str]] = set()
    for need, query in QUERIES:
        url = SEARCH.format(q=urllib.parse.quote(query))
        try:
            req = u.Request(url, headers=hdr)
            with op.open(req, timeout=180) as r:
                html = r.read(1_500_000).decode("utf-8", "replace")
            links = re.findall(r'href="/indicator/(\d+)"[^>]*>([^<]{5,200})<', html)
            # оставляем ссылки, чей текст пересекается со словами запроса
            words = [w for w in query.lower().split() if len(w) > 4]
            kept = 0
            for ind_id, title in links:
                t = title.strip()
                tl = t.lower()
                if not any(w[:6] in tl for w in words):
                    continue
                key = (need, ind_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"need_id": need, "query": query,
                             "indicator_id": ind_id, "title": t[:200]})
                kept += 1
            log(f"{need} «{query}»: {len(links)} ссылок, оставлено {kept}")
        except Exception as exc:
            log(f"{need} «{query}»: ERR {type(exc).__name__}: {exc}")
        time.sleep(1.0)

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    log(f"saved: {OUT_CSV} rows={len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
