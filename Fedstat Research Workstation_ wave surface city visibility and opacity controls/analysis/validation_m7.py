# -*- coding: utf-8 -*-
"""
Валидация M7: устойчивость передачи (adj_l1) вне единого окна подбора.

1. Подпериоды: 2015-2019 (спокойный), 2020-2021 (ковид), 2022-2025 (санкции).
2. Скользящее окно 36 мес., шаг 6 мес.: путь коэффициента adj_l1 с 95% ДИ.
3. Плацебо: 100 случайных перестановок регионов в W (соседи перемешаны) —
   распределение adj_l1 на ложных сетях против истинного значения
   (эмпирический p-уровень). Если связь настоящая — на ложной сети рушится.

Выходы: index_lab_output/base_model/validation_m7.json, rolling CSV,
        validation_m7.png (путь коэффициента + плацебо-гистограмма).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from linearmodels.panel import PanelOLS

sys.path.insert(0, str(Path(__file__).resolve().parent))
import base_spatial_model as bsm

APP = Path(__file__).resolve().parent.parent
OUT = APP / "index_lab_output" / "base_model"

LAGS = [1, 2, 3, 6]
ROLL_WIN = 36
ROLL_STEP = 6
N_PLACEBO = 100
RNG = np.random.default_rng(2027)


def fit_adj(panel: pd.DataFrame, W: np.ndarray, p0: str, p1: str):
    """M3_adj на окне [p0, p1]; возвращает (coef, se, nobs) для adj_l1."""
    sub = panel.loc[(panel.index >= p0) & (panel.index <= p1)]
    cols = {"infl": None}
    frames = {"infl": sub.stack()}
    for L in LAGS:
        frames[f"own_l{L}"] = sub.shift(L).stack()
        frames[f"adj_l{L}"] = bsm.transported(sub, W, L).stack()
    frame = pd.DataFrame(frames).dropna()
    if len(frame) < 1500:
        return None
    frame.index = frame.index.set_names(["period", "subject"])
    periods = sorted(frame.index.get_level_values("period").unique())
    tmap = {p: i for i, p in enumerate(periods)}
    frame = frame.reset_index()
    frame["t"] = frame["period"].map(tmap)
    frame = frame.set_index(["subject", "t"])
    regs = [f"own_l{L}" for L in LAGS] + [f"adj_l{L}" for L in LAGS]
    try:
        res = PanelOLS(frame["infl"], frame[regs], entity_effects=True,
                       time_effects=True, drop_absorbed=True
                       ).fit(cov_type="clustered", cluster_entity=True)
    except Exception:
        return None
    return (float(res.params["adj_l1"]), float(res.std_errors["adj_l1"]), int(res.nobs))


def main() -> int:
    panel, meta = bsm.load_panel()
    W = bsm.build_weights(meta)["adj"]

    report: dict = {}

    # --- 1. подпериоды ---
    eras = {"2015-2019 спокойный": ("2015-01", "2019-12"),
            "2020-2021 ковид": ("2020-01", "2021-12"),
            "2022-2025 санкции": ("2022-01", "2025-12")}
    report["subperiods"] = {}
    print("=== подпериоды ===")
    for name, (p0, p1) in eras.items():
        r = fit_adj(panel, W, p0, p1)
        if r:
            c, se, n = r
            report["subperiods"][name] = {"adj_l1": round(c, 4), "se": round(se, 4),
                                          "t": round(c / se, 2), "nobs": n}
            print(f"  {name}: adj_l1={c:+.3f} (se={se:.3f}, t={c/se:+.1f}, n={n})")

    # --- 2. скользящее окно ---
    months = [p for p in panel.index if p >= bsm.START]
    rolls = []
    print("=== скользящее окно 36 мес. ===")
    i = 0
    while i + ROLL_WIN <= len(months):
        p0, p1 = months[i], months[i + ROLL_WIN - 1]
        r = fit_adj(panel, W, p0, p1)
        if r:
            c, se, n = r
            rolls.append({"start": p0, "end": p1, "adj_l1": c, "se": se, "nobs": n})
        i += ROLL_STEP
    roll_df = pd.DataFrame(rolls)
    roll_df.to_csv(OUT / "validation_m7_rolling.csv", index=False, encoding="utf-8-sig")
    sig_share = float((roll_df["adj_l1"] / roll_df["se"] > 1.96).mean())
    report["rolling"] = {"windows": len(roll_df),
                        "coef_min": round(float(roll_df["adj_l1"].min()), 4),
                        "coef_max": round(float(roll_df["adj_l1"].max()), 4),
                        "share_significant": round(sig_share, 3)}
    print(f"  окон: {len(roll_df)}; adj_l1 в [{roll_df['adj_l1'].min():+.3f}, "
          f"{roll_df['adj_l1'].max():+.3f}]; значимых (t>1.96): {sig_share:.0%}")

    # --- 3. плацебо-перестановки W ---
    true_fit = fit_adj(panel, W, bsm.START, bsm.END)
    true_c = true_fit[0]
    n = W.shape[0]
    placebo = []
    print(f"=== плацебо ({N_PLACEBO} перестановок W) ===")
    for k in range(N_PLACEBO):
        perm = RNG.permutation(n)
        Wp = W[np.ix_(perm, perm)]
        r = fit_adj(panel, Wp, bsm.START, bsm.END)
        if r:
            placebo.append(r[0])
    placebo = np.array(placebo)
    emp_p = float((np.abs(placebo) >= abs(true_c)).mean())
    report["placebo"] = {"true_adj_l1": round(true_c, 4),
                        "n_placebo": int(len(placebo)),
                        "placebo_mean": round(float(placebo.mean()), 4),
                        "placebo_q95_abs": round(float(np.quantile(np.abs(placebo), 0.95)), 4),
                        "empirical_p": emp_p}
    print(f"  истинный adj_l1={true_c:+.3f}; плацебо mean={placebo.mean():+.4f}, "
          f"q95|coef|={np.quantile(np.abs(placebo), 0.95):.4f}; эмпирический p={emp_p:.3f}")

    (OUT / "validation_m7.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- график ---
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    ax = axes[0]
    x = range(len(roll_df))
    ax.plot(x, roll_df["adj_l1"], marker="o", color="#c0392b", lw=2)
    ax.fill_between(x, roll_df["adj_l1"] - 1.96 * roll_df["se"],
                    roll_df["adj_l1"] + 1.96 * roll_df["se"], alpha=0.2, color="#c0392b")
    ax.axhline(0, color="#555", lw=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{r['start'][:7]}—{r['end'][:7]}" for _, r in roll_df.iterrows()],
                       rotation=45, ha="right", fontsize=8)
    ax.set_title("Передача между соседями во времени: adj_l1 в окнах 36 мес. (95% ДИ)")
    ax.set_ylabel("коэффициент adj_l1")

    ax = axes[1]
    ax.hist(placebo, bins=25, color="#95a5a6", edgecolor="#555")
    ax.axvline(true_c, color="#c0392b", lw=2.5,
               label=f"истинная сеть: {true_c:+.3f}")
    ax.set_title(f"Плацебо: {len(placebo)} перемешанных сетей соседства "
                 f"(эмпирический p={emp_p:.3f})")
    ax.set_xlabel("adj_l1 на ложной сети")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "validation_m7.png", dpi=200)
    plt.close(fig)
    print(f"saved: {OUT/'validation_m7.json'} | validation_m7_rolling.csv | validation_m7.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
