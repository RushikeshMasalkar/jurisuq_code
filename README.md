# JURIS-UQ

Legal-aware uncertainty quantification for LLM-based Indian legal question
answering.

> **Research prototype.** JURIS-UQ is not a legal research service and does
> not provide legal advice. Its benchmark is scoped and partly synthetic, and
> Phase C legal verification is incomplete.

## Purpose and scope

JURIS-UQ studies whether agreement among an LLM's sampled answers can hide a
shared legal error. The current benchmark is matched around the transition
from the Indian Penal Code (IPC) to the Bharatiya Nyaya Sanhita (BNS), effective
1 July 2024:

- **L7** asks for current law and uses the repealed IPC provision as the trap.
- **L1** asks for law immediately before the transition and uses the BNS
  successor as the trap.

The five phases are cumulative:

1. **Phase A** builds the sampling, judging, clustering, and sample-only
   uncertainty instrument.
2. **Phase B** adds typed legal relations and re-clusters the frozen Phase A
   answers.
3. **Phase C** adds a deterministic statute store, validity windows,
   IPC/BNS links, and context packs.
4. **Phase D** detects whether agreement is legally warranted using observed
   agreement, temporal validity, jurisdiction fit, and contradiction mass.
5. **Phase E** consumes stored Phase D fields in a monotone uncertainty model
   with an explicit sample-only fallback.

The phases are deliberately separated: Phase C/D/E write sibling runs and
leave their source runs unchanged. Phase E never recomputes Phase D outputs.

## Current status

| Phase | Status | Run or record of reference |
|---|---|---|
| A | Complete and frozen | `runs/phaseA-laptop-v2-rejudged/` |
| B | Implemented; run of record complete | `runs/phaseB-relations-full/` |
| C | Engineering complete; legal verification partial | `runs/phaseA-laptop-v2-rejudged+ctx/` |
| D | Complete and frozen; G4 PASS | `runs/phaseA-laptop-v2-rejudged+ctx+warrant/` |
| E | Implemented pilot; G5 NOT_EVALUABLE | `runs/phaseA-laptop-v2-rejudged+ctx+warrant+uq/` |

Phase E's target holdout contains only incorrect L7 answers, so its L7 AUROC
is undefined and no G5 pass is claimed. The score is an uncalibrated risk
ranking, not a probability.

## Documentation map

Canonical phase guides, each containing implementation details and the complete
historical results record:

- [Phase A guide](PHASE-A.md) — sampling, judging, analysis, reproduction,
  E1/G1 results, dataset hash, and historical run notes.
- [Phase B guide](PHASE-B.md) — relation data, training, evaluation, E2,
  metrics, confusion matrix, G2 interpretation, and limitations.
- [Phase C guide](PHASE-C.md) — statute store, context-pack workflow,
  verification evidence, hashes, coverage, and test records.
- [Phase D guide](PHASE-D.md) — warrant detector, E4 metrics, confidence
  interval, ablation, G4, integrity hashes, and legal limits.
- [Phase E guide](PHASE-E.md) — legal-aware scoring, fallback behavior, paired
  AUROC interval, G5 status, and separate environment test records.

[Deployment and troubleshooting](DEPLOYMENT-GUIDE.md) contains operational
setup notes and known environment issues. The machine-readable source records
remain under `runs/`; do not replace them with README summaries.

## Architecture

```text
Phase A: generator -> normalization/judge -> clustering -> metrics
              |
Phase B: typed relation dataset/model -> re-clustering of frozen A answers
              |
Phase C: statute table + IPC/BNS links -> immutable context-packed run
              |
Phase D: context + stored answers -> A/T/J/K, W, CM, flags
              |
Phase E: sample statistics + stored W/CM/K -> monotone risk score/fallback
```

Primary modules are in [`jurisuq/`](jurisuq/): core pipeline and metrics,
`relations/` for Phase B, `context/` for Phase C, `warrant/` for Phase D, and
`uncertainty/` for Phase E. Scripts are numbered by phase:
`00`–`06` (A), `10`–`12` (B), `20`–`22` (C), and `23`–`27` (D/E).

## Requirements and installation

Supported runtime: Python 3.11 or newer (3.11/3.12 generally have the widest
binary-wheel compatibility), Git, and a virtual environment. The repository
is not packaged as an installable wheel.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate`.

`requirements.txt` contains shared/core packages (`requests`, `numpy`,
`matplotlib`, and `pytest`). Install optional or phase-specific packages only
when needed:

```bash
# Phase A standard semantic-entropy/NLI backend
python -m pip install -r requirements-phase-a.txt

# Phase B relation model (install the suitable PyTorch wheel first)
python -m pip install -r requirements-phase-b.txt
```

Phase C and D add no Python packages beyond the shared file. Phase E is also
stdlib-only beyond the shared test/runtime environment. The NLI and relation
files may download model checkpoints at first use; they are not external legal
sources. Real Phase A runs additionally require an OpenAI-compatible local
server such as LM Studio or `llama-server` at the configured endpoint. GPU/XPU
support depends on the platform-specific PyTorch wheel.

## Recommended verification

Run from the repository root:

```bash
python -m pytest -q
python scripts/00_env_check.py --skip-endpoint
```

Focused deterministic checks:

```bash
python -m pytest tests/test_context.py -q
python -m pytest tests/test_warrant.py -q
python -m pytest tests/test_uncertainty.py -q
```

The checked-in Phase E record reports 149 passed and 1 skipped in the sandbox,
147 passed in a historical Windows PowerShell run, and 149 passed in the latest
post-change Windows PowerShell run. These are separate environment-specific
records, not a fresh-environment claim.

## Reproduction entry points

Use a new run suffix for generated outputs; do not overwrite frozen runs.

```bash
# Phase A shipped-run analysis (no new model answers)
python scripts/03_analyze_e1.py --run-id phaseA-laptop-v2-rejudged
python scripts/04_make_figure.py --run-id phaseA-laptop-v2-rejudged

# Phase B dataset verification
python scripts/10_build_relations.py --verify-only

# Phase C
python scripts/20_build_statutes.py --out data/statutes/statutes_v1.jsonl
python scripts/21_attach_context.py --run-id phaseA-laptop-v2-rejudged --out-suffix +ctx-repro --as-of 2026-10-01

# Phase D (requires the Phase C +ctx run)
python scripts/23_detect_warrant.py --run-id phaseA-laptop-v2-rejudged+ctx --out-suffix +warrant-repro
```

The phase guides contain complete commands, inputs, outputs, smoke modes,
Windows variants, and integrity precautions. `run_phase_a.sh smoke` is
non-production plumbing only: it rewrites the checked-in data slice and must
be run in a disposable worktree.

## Historical results that must not be conflated

The project preserves the original metrics rather than normalizing them:

- Phase A L7 AUROC is undefined because all 100 scored L7 answers are wrong;
  its provision-level collision population is 16/100 and all 16 are wrong.
- Phase B test macro-F1 is 0.7770 versus the 0.7765 exact-key baseline;
  all six errors are false merges, and the L7 typed collision population is
  44 with accuracy 0.0000.
- Phase C contains 48 statute rows (40 secondary-source supported, 8
  unresolved), 0/48 independently primary-source verified, and context
  coverage 0.689034 (421 known of 611 lookups).
- Phase D reports CM AUROC 0.9412 with bootstrap 95% CI [0.8529, 1.0000],
  binary TP/FP/TN/FN 16/0/15/2, and G4 PASS; temporal ablation carries all
  above-chance separation.
- Phase E reports 32 legal-aware scores and 168 sample-only fallbacks;
  L1 AUROC 0.9000 versus 0.8714 provision-entropy baseline, paired difference
  +0.0286 with 95% interval [−0.0417, +0.1500], and a legal-aware-only
  subset of three records with AUROC 0.7500. G5 remains NOT_EVALUABLE.

See the linked result documents for counts, source hashes, run IDs, confidence
interval methods, limitations, validation outcomes, and historical execution
records. Unknown legal provisions remain `None`, never stale/false.

## Data, integrity, and limitations

The checked-in 200-item data slice, relation dataset, statute table, manifests,
overrides, run records, and validation JSON files are research artifacts.
Phase C's current statute hash is
`20c98b74c0855c5ec4c8cda2b2d52388ea5f3e8d2514376f56db425bdd90b21e`; the
Phase A and Phase B dataset hashes and Phase D/E run hashes are recorded in
their result documents. Source runs are tree-hashed before and after overlay
steps. Do not modify generated metrics or model outputs when documenting a new
run.

The benchmark is one synthetic 200-item matched construction and one
quantized 7B checkpoint. Phase B labels are rule-generated, not human
annotations. Phase C legal verification is incomplete, and the detector is a
temporal common-mode detector rather than a general correctness oracle. Phase E
does not provide calibration; later calibration and broader evaluation remain
future work.

## License and citation

No project license has been declared. Preserve the research and source
citations in the result records when reusing this code.
