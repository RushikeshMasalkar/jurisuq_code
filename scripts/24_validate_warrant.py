"""24_validate_warrant.py -- Phase D experiment E4 and Gate G4.

    python scripts/24_validate_warrant.py \
        --run-id phaseA-laptop-v2-rejudged+ctx+warrant

Validates the detector on the frozen Phase A records, which already
carry the ground truth about which unanimous answers were wrong.
Every number is reproduced from the stored ``warrant_*`` fields
alone -- no re-detection, no model, no network -- which is what
makes the ablation runs cheap.

The validation isolates the unanimous provision-level collision
population and asks, per the engineering guide (section 18.2):

* on the unanimously-wrong target-slice items, does the detector
  fire, with ``stale_provision`` the dominant flag?
* on the unanimously-correct control items, does it stay silent?
* on everything else, what is the false-alarm base rate?

Gate G4 then asks three things, all of which must hold: the common
mode score separates correct from incorrect unanimous answers
(AUROC > 0.5, bootstrap interval excluding 0.5); the temporal
factor alone recovers at least half the separation (factor
attribution by ablation); and the alarm rate on unanimously-correct
items is below the alarm rate on unanimously-wrong items.

Outputs, under the run directory:

    warrant_validation.json   the E4 record and the G4 verdict
    fig_warrant.png / .svg    the paper-ready validation figure
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from jurisuq.warrant.detector import WarrantResult  # noqa: E402
from jurisuq.warrant.validate import validate  # noqa: E402


def _correct_of(rec: dict) -> int:
    """Offline correctness label: the majority outcome among samples.

    Read only by the validation, never by the detector.
    """
    return int(rec.get("majority_correct") or 0)


def make_figure(report: dict, out_png: pathlib.Path,
                out_svg: pathlib.Path) -> None:
    """The three-panel E4 figure: separation, factors, base rate."""
    pop = report["collision_population"]
    groups = pop["by_group"]
    ablation = pop["factor_ablation"]["ablations"]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))

    # (a) common-mode score by group over the collision population
    ax = axes[0]
    order = [k for k in sorted(groups)
             if k.startswith("L7|correct=0")] + \
            [k for k in sorted(groups) if k.startswith("L1|correct=1")] + \
            [k for k in sorted(groups)
             if k not in ("L7|correct=0", "L1|correct=1")]
    labels, cms = [], []
    for k in order:
        g = groups[k]
        labels.append(k.replace("|correct=", "\ncorrect="))
        cms.append(g.get("cm_mean"))
    colors = ["#c0392b" if "L7" in k else
              ("#27ae60" if "correct=1" in k else "#e67e22")
              for k in order]
    bars = ax.bar(range(len(labels)),
                  [c if c is not None else 0.0 for c in cms],
                  color=colors, alpha=0.85)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("mean common-mode score CM = A - W")
    ax.set_title("(a) CM score, collision population\n"
                 "(red = wrong target, green = correct control)",
                 fontsize=9)
    ax.set_ylim(0, 1.05)
    for b, c in zip(bars, cms):
        ax.text(b.get_x() + b.get_width() / 2,
                (c or 0.0) + 0.02,
                "n/a" if c is None else f"{c:.2f}",
                ha="center", fontsize=7)

    # (b) factor attribution: AUROC when each factor is pinned
    ax = axes[1]
    full = pop["factor_ablation"]["full_auroc"]
    names = ["full"] + [a["factor"] for a in ablation]
    vals = [full] + [a["auroc_when_pinned"] for a in ablation]
    cols = ["#2c3e50"] + ["#7f8c8d"] * len(ablation)
    ax.bar(range(len(names)),
           [v if v == v else 0.0 for v in vals], color=cols, alpha=0.85)
    ax.axhline(0.5, color="#c0392b", ls="--", lw=1)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(["full\n(composite)"] +
                       [a["factor"] + "\npinned" for a in ablation],
                       fontsize=7)
    ax.set_ylabel("AUROC on collision population")
    ax.set_title("(b) factor attribution by ablation\n"
                 "(pinning a factor to its warrant-max value)",
                 fontsize=9)
    ax.set_ylim(0, 1.05)
    for i, v in enumerate(vals):
        ax.text(i, (v if v == v else 0.0) + 0.02,
                "n/a" if v != v else f"{v:.2f}",
                ha="center", fontsize=7)

    # (c) alarm rate by correctness, collision vs rest
    ax = axes[2]
    br = report["base_rate"]
    conf = pop["binary_confusion"]
    cats = ["collision\nwrong", "collision\ncorrect",
            "rest\nwrong", "rest\ncorrect"]
    rates = [conf["tp"] / (conf["tp"] + conf["fn"])
             if conf["tp"] + conf["fn"] else 0.0,
             conf["fp"] / (conf["fp"] + conf["tn"])
             if conf["fp"] + conf["tn"] else 0.0,
             br.get("wrong_item_alarm_rate", 0.0),
             br.get("correct_item_alarm_rate", 0.0)]
    ax.bar(range(4), rates,
           color=["#c0392b", "#27ae60", "#e67e22", "#27ae60"],
           alpha=0.85)
    ax.set_xticks(range(4))
    ax.set_xticklabels(cats, fontsize=7)
    ax.set_ylabel("detector fire rate")
    ax.set_title("(c) alarm rate: fires on wrong, silent on correct",
                 fontsize=9)
    ax.set_ylim(0, 1.05)
    for i, v in enumerate(rates):
        ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=7)

    fig.suptitle("Phase D (E4): common-mode failure detector -- "
                 "warranted vs repeated agreement", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(out_png, dpi=160)
    fig.savefig(out_svg)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id",
                    default="phaseA-laptop-v2-rejudged+ctx+warrant",
                    help="the Phase D run produced by "
                         "23_detect_warrant.py")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--out", default=None,
                    help="validation report path "
                         "(default: <run>/warrant_validation.json)")
    args = ap.parse_args()

    runs_dir = pathlib.Path(args.runs_dir)
    if not runs_dir.is_absolute():
        runs_dir = ROOT / runs_dir
    run = runs_dir / args.run_id
    items = run / "items.jsonl"
    if not items.exists():
        print(f"ERROR: no such run: {items}")
        print("       run first: python scripts/23_detect_warrant.py "
              f"--run-id <source> --out-suffix +warrant")
        return 1

    records = [json.loads(l) for l in items.read_text().splitlines()
               if l.strip()]
    results = [(rec, WarrantResult.from_record(rec))
               for rec in records]

    report = validate(None, records, _correct_of, results=results)
    report["run_id"] = args.run_id
    report["phase"] = "D"
    # the source run is the Phase C +ctx run this one was
    # packed from, recorded by 23_detect_warrant.py
    meta_path = run / "meta.json"
    if meta_path.exists():
        report["source_run"] = json.loads(
            meta_path.read_text()).get("source_run")
    # NOTE: this validation report is deliberately free of any
    # timestamp, so it is byte-identical on every regeneration
    # and its sha256 can be cited as the integrity anchor for
    # the E4 result.  The operational detect report
    # (warrant_report.json) carries generated_utc and is the
    # one file whose hash is generation-specific.

    out_path = pathlib.Path(args.out) if args.out else \
        run / "warrant_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n",
                            encoding="utf-8", newline="\n")

    fig_png = run / "fig_warrant.png"
    fig_svg = run / "fig_warrant.svg"
    make_figure(report, fig_png, fig_svg)

    gate = report["gate_g4"]
    pop = report["collision_population"]
    sep = pop["separation"]
    conf = pop["binary_confusion"]
    print(f"E4 validation on {report['n_records']} records "
          f"({pop['n']} in the collision population)")
    print(f"  CM-score AUROC = "
          f"{sep['auroc']:.4f}"
          f"  95% CI [{sep['ci']['lo']:.4f}, {sep['ci']['hi']:.4f}]"
          f"  (n={sep['n_scored']}, "
          f"{sep['n_excluded_undefined']} undefined-CM excluded)")
    print(f"  binary detector: TP={conf['tp']} FP={conf['fp']} "
          f"TN={conf['tn']} FN={conf['fn']}  "
          f"(precision {conf['precision']:.3f}, "
          f"recall {conf['recall']:.3f}, "
          f"false-alarm {conf['false_alarm_rate']:.3f})")
    for k, v in pop["by_group"].items():
        print(f"    {k}: n={v['n']} fires={v['fires']} "
              f"({v['fire_rate']:.2f})  flags={v['flags']}")
    print(f"  factor ablation (AUROC drop):")
    for a in pop["factor_ablation"]["ablations"]:
        drop = a["auroc_drop_from_full"]
        print(f"    pin {a['factor']}={a['pinned_to']}: "
              f"AUROC {a['auroc_when_pinned']:.4f} "
              f"(drop {drop:.4f})" if drop == drop else
              f"    pin {a['factor']}: AUROC "
              f"{a['auroc_when_pinned']}")
    br = report["base_rate"]
    print(f"  base rate over {br['non_collision_items']} "
          f"non-collision items: fire "
          f"{br['non_collision_fire_rate']:.3f}; "
          f"correct-item alarm {br['correct_item_alarm_rate']:.3f}, "
          f"wrong-item alarm {br['wrong_item_alarm_rate']:.3f}")
    print(f"  GATE G4: {gate['verdict']}  "
          f"{gate['conditions']}")
    print(f"  wrote {out_path}, {fig_png.name}, {fig_svg.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
