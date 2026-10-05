#!/usr/bin/env python3
"""04 - E1 figure: three panels, grayscale, print-ready for the paper.

Panel (a)  AUROC per method on L7 and L1 with bootstrap intervals.
Panel (b)  Selective risk against coverage on L7, deduplicated, against the
           always-answer reference.
Panel (c)  The direct measurement: share of items answered with a single
           self-consistent value *and* wrongly ("confidently wrong") on each
           slice, with Wilson intervals.

    python scripts/04_make_figure.py --run-id phaseA-laptop
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jurisuq.config import Config, ROOT
from jurisuq.metrics import risk_coverage

METHOD_LABEL = {
    "prov_se": "Provision-level SE",
    "prov_agreement": "1 - prov. agreement",
    "disc_se": "Discrete SE",
    "se": "Standard SE",
    "selfcheck": "SelfCheckGPT",
    "agreement": "1 - agreement",
    "p_true": "1 - p_true",
}
INK = "#1a1a1a"
GREY = "#9a9a9a"
STYLES = [dict(color=INK, lw=1.5),
          dict(color=INK, lw=1.0, ls="--"),
          dict(color="#4d4d4d", lw=1.1, ls="-"),
          dict(color="#4d4d4d", lw=1.1, ls="--"),
          dict(color="#4d4d4d", lw=1.1, ls=":"),
          dict(color="#b0b0b0", lw=1.1, ls="-.")]


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def confidently_wrong(recs: list[dict]) -> tuple[float, float, float, int]:
    """Share of items whose answer is wrong *and* unanimous at the provision level."""
    key = "prov_all_same" if any("prov_all_same" in r for r in recs) else "all_same"
    n = len(recs)
    k = sum(1 for r in recs if r.get(key) == 1 and int(r["majority_correct"]) == 0)
    p, lo, hi = wilson(k, n)
    return p, lo, hi, k


def dedupe_series(curves: dict[str, list[float]]) -> list[str]:
    """Keep the first method for each distinct risk-coverage curve."""
    kept: list[str] = []
    seen: set[tuple] = set()
    for name, curve in curves.items():
        key = tuple(round(v, 3) for v in curve)
        if key in seen:
            continue
        seen.add(key)
        kept.append(name)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="phaseA-smoke")
    ap.add_argument("--analysis-run", default=None, help="run id that holds e1_report.json")
    ap.add_argument("--out", default=None)
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    cfg = Config.load()
    run_dir = ROOT / cfg.out_dir / args.run_id
    rep_path = ROOT / cfg.out_dir / (args.analysis_run or args.run_id) / "e1_report.json"
    if not rep_path.exists():
        raise SystemExit(f"{rep_path} not found - run scripts/03_analyze_e1.py first")
    rep = json.loads(rep_path.read_text())
    recs = [json.loads(l) for l in (run_dir / "items.jsonl").read_text().splitlines() if l.strip()]
    recs = [r for r in recs if "error" not in r]

    slices = rep["slices"]
    methods = [m for m in METHOD_LABEL if m in rep["per_slice"].get(slices[0], {}).get("methods", {})]
    if not methods:
        raise SystemExit("no methods found in the report")

    fig, axes = plt.subplots(1, 3, figsize=(15.2, 3.9), dpi=args.dpi,
                             gridspec_kw={"width_ratios": [1.25, 1.15, 0.75]})

    # ---- panel (a): AUROC bars --------------------------------------
    ax = axes[0]
    x = np.arange(len(methods))
    w = 0.36
    for k, s in enumerate(slices):
        st = rep["per_slice"][s]["methods"]
        vals = [st[m]["auroc"] for m in methods]
        err_lo = [max(0.0, st[m]["auroc"] - (st[m].get("auroc_lo") or st[m]["auroc"])) for m in methods]
        err_hi = [max(0.0, (st[m].get("auroc_hi") or st[m]["auroc"]) - st[m]["auroc"]) for m in methods]
        ax.bar(x + (k - 0.5) * w, vals, width=w,
               color=INK if k == 0 else "white",
               edgecolor=INK, linewidth=0.8, zorder=3,
               yerr=[err_lo, err_hi], capsize=2,
               error_kw=dict(elinewidth=0.7, ecolor=INK),
               label=f"{s}  (n = {rep['per_slice'][s]['n_items']})")
    ax.axhline(0.5, color=GREY, linewidth=0.8, linestyle=":", zorder=2)
    ax.text(0.02, 0.505, "chance", fontsize=6.5, color="#555555", ha="left", va="bottom",
            transform=ax.get_yaxis_transform())
    ax.axhline(rep["gate_auroc_max"], color=GREY, linewidth=0.8, linestyle="--", zorder=2)
    ax.text(0.02, rep["gate_auroc_max"] - 0.015, "gate ceiling",
            fontsize=6.5, color="#555555", ha="left", va="top",
            transform=ax.get_yaxis_transform())
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("AUROC detecting incorrect answers", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([METHOD_LABEL[m] for m in methods], fontsize=7.5, rotation=12, ha="right")
    ax.tick_params(axis="y", labelsize=7.5)
    ax.legend(fontsize=7, frameon=False, loc="upper left", bbox_to_anchor=(0.18, 1.0))
    ax.set_title("(a)  Sample-only uncertainty, by slice", fontsize=8.5, loc="left", color=INK)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.6, zorder=0)

    # ---- panel (b): risk-coverage on L7 ------------------------------
    ax = axes[1]
    l7 = [r for r in recs if r["slice"] == "L7"]
    curves: dict[str, list[float]] = {}
    for m in methods:
        pairs = [(r["methods"][m], int(r["majority_correct"])) for r in l7
                 if r["methods"].get(m) is not None and r["methods"][m] == r["methods"][m]]
        if not pairs:
            continue
        rc = risk_coverage([c for _, c in pairs], [u for u, _ in pairs])
        curves[m] = rc["risk"]
    for name, style in zip(dedupe_series(curves), STYLES):
        pairs = [(r["methods"][name], int(r["majority_correct"])) for r in l7
                 if r["methods"].get(name) is not None and r["methods"][name] == r["methods"][name]]
        rc = risk_coverage([c for _, c in pairs], [u for u, _ in pairs])
        ax.plot(rc["coverage"], rc["risk"], label=METHOD_LABEL[name], **style)
    base = sum(1 - int(r["majority_correct"]) for r in l7) / max(1, len(l7))
    ax.axhline(base, color=GREY, lw=0.8, ls="--")
    ax.text(0.02, base + 0.008, f"always-answer risk = {base:.3f}", fontsize=6.5,
            color="#555555", ha="left", va="bottom", transform=ax.get_yaxis_transform())
    ax.set_xlabel("coverage (fraction of questions answered)", fontsize=8)
    ax.set_ylabel("selective risk (fraction incorrect)", fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, max(0.35, base * 1.6))
    ax.tick_params(labelsize=7.5)
    ax.legend(fontsize=7, frameon=False, loc="lower left", bbox_to_anchor=(0.30, 0.02))
    ax.set_title("(b)  L7: risk against coverage", fontsize=8.5, loc="left", color=INK)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(color="#e6e6e6", linewidth=0.6)

    # ---- panel (c): confidently wrong ---------------------------------
    ax = axes[2]
    xs = np.arange(len(slices))
    vals, los, his, ks, ns = [], [], [], [], []
    for s in slices:
        sub = [r for r in recs if r["slice"] == s]
        p, lo, hi, k = confidently_wrong(sub)
        vals.append(p)
        los.append(max(0.0, p - lo))
        his.append(max(0.0, hi - p))
        ks.append(k)
        ns.append(len(sub))
    ax.bar(xs, vals, width=0.5, color=[INK if s == "L7" else "white" for s in slices],
           edgecolor=INK, linewidth=0.9, zorder=3,
           yerr=[los, his], capsize=3, error_kw=dict(elinewidth=0.8, ecolor=INK))
    for xi, (v, k, n) in enumerate(zip(vals, ks, ns)):
        ax.text(xi, v + max(his) + 0.04, f"{k}/{n}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(xs)
    ax.set_xticklabels(slices, fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("share confidently wrong", fontsize=8)
    ax.tick_params(axis="y", labelsize=7.5)
    ax.set_title("(c)  Unanimous (same provision) and wrong", fontsize=8.5, loc="left", color=INK)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.6, zorder=0)

    fig.tight_layout()
    out = Path(args.out) if args.out else run_dir / "fig_e1.png"
    fig.savefig(out, dpi=args.dpi, bbox_inches="tight", facecolor="white")
    fig.savefig(out.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")
    print(f"wrote {out.with_suffix('.svg')}")
    print("panel (c): " + "; ".join(
        f"{s}: {v:.3f} ({k}/{n})" for s, v, k, n in zip(slices, vals, ks, ns)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
