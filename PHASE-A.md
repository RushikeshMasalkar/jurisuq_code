# JURIS-UQ Phase A: sampling and common-mode diagnostic

Phase A is the diagnostic instrument. It builds a matched 200-item L1/L7
slice, samples answers from an OpenAI-compatible local model, extracts asserted
provisions, resolves correctness, computes sample-only uncertainty statistics,
and evaluates the E1 common-mode premise.

## Compute and cost

Inference runs locally through LM Studio on this machine. No accelerator is
used: PyTorch reports `2.9.1+cpu`, with CUDA, MPS, and XPU unavailable, so
inference and relation-model training run on CPU. The project spent nothing:
there were no paid API calls, subscriptions, or billing.

The primary frozen Phase A run remains `qwen2.5-7b-instruct`; all Phase A
results and every Phase B-E number derive from its frozen `p2-structured`
prompt and 2,000 stored samples. `Qwen3-14B Q4_K_M` (about 9 GB) was screened
locally with reasoning on and off: it answered IPC 379 to a post-1-July-2024
theft question and scored 0% on L7. It is a screen only; no slice was
regenerated with it. Gemini API screening found 2.5-flash unavailable,
3.8-flash returning 503, and 3.6-flash exhausting the free-tier daily quota
(HTTP 429), so no API model was used under the zero-cost constraint.

## Components and data

- `jurisuq/generators.py`: mock and OpenAI-compatible local generators.
- `jurisuq/normalize.py` and `jurisuq/judge.py`: conservative extraction and
  provision-based correctness resolution.
- `jurisuq/cluster.py` and `jurisuq/metrics.py`: clustering and AUROC,
  risk-coverage, AURC, ECE, bootstrap, and kappa metrics.
- `scripts/00_env_check.py` through `06_pilot.py`: environment, data,
  inference, analysis, plotting, re-judging, and pilot workflows.
- `data/lexuq_slice.jsonl`: 200 records, 100 matched L1/L7 pairs.
- `runs/phaseA-laptop-v2-rejudged/`: frozen run of record.

The authoritative Phase A dataset on disk has sha256
`89bc1180a4df76287768ce59432aa7ff0aa9d38c16d5f296ed16c3e45449bd53`
(decision recorded 2026-10-22). It regenerates byte-for-byte from
`scripts/01_make_data.py` with seed `20261005`; all 200 frozen item IDs and
their content fields match, and re-scoring the 2,000 stored answers reproduces
all 200 stored verdict-label arrays. The previously registered
`45b2d194e9c2f623457481c0d7d02f36c6267ec65c0b75ee3df2be4c0d1d010a` value is
stale and remains visible here as a historical value. Line-ending conversion
does not produce it, so the discrepancy is a re-serialization artifact.
All later run metadata must record the authoritative digest.

## Reproduce or inspect

Install the shared requirements and, for the optional standard NLI backend,
`requirements-phase-a.txt`. For a report-only analysis of the shipped run:

```bash
python scripts/03_analyze_e1.py --run-id phaseA-laptop-v2-rejudged
python scripts/04_make_figure.py --run-id phaseA-laptop-v2-rejudged
```

For a new local-model run, start LM Studio or `llama-server`, check it, pilot,
then run the resumable inference:

```bash
python scripts/00_env_check.py --model qwen2.5-7b-instruct
python scripts/06_pilot.py --config configs/phase_a.json --run-id phaseA-pilot --set model=qwen2.5-7b-instruct
python scripts/02_run_inference.py --config configs/phase_a.json --run-id phaseA-my-run --set model=qwen2.5-7b-instruct
python scripts/03_analyze_e1.py --run-id phaseA-my-run
```

Use `python scripts/00_env_check.py --skip-endpoint` for a local-only check.
`run_phase_a.sh smoke` uses a mock generator but rewrites the data slice, so
run it only in a disposable worktree. Re-judging uses stored answers and does
not resample:

```bash
python scripts/05_rejudge.py --config configs/phase_a.json --run-id phaseA-my-run --out-suffix=-rejudged
```

## Result record

[The results section below is authoritative. It preserves the E1 AUROC
single-class limitation, collision counts, confidence
intervals, G1 PASS, historical v1/re-judged runs, and the frozen dataset note.
Phase B consumes the stored answers without changing this run.

---

## Complete experimental results and validation record

### Merged record: `PHASE-A.md`

# Phase A results — E1 common-mode diagnostic

Run of record. The numbers below are transcribed from the run report produced by
`scripts/03_analyze_e1.py` for the run named in the first row, on the dataset named in
the freeze note. Fields the run report did not contain are marked **not reported**
rather than filled in. The authoritative machine-readable source is
`runs/phaseA-laptop-v2-rejudged/e1_report.json`.

## Run identity

| Field | Value |
|---|---|
| Run id | phaseA-laptop-v2-rejudged |
| Date / machine | not reported (Windows laptop, Lenovo IdeaPad Slim 5, Intel Core Ultra with Intel Arc graphics) |
| Generator (name + quantisation) | Qwen2.5-7B-Instruct, Q4_K_M quantisation, served by LM Studio on an OpenAI-compatible endpoint at localhost |
| Sampling: M, temperature, top_p, max_tokens | M = 10, temperature 1.0, top_p 1.0, max_tokens 220 |
| Clustering channels used | discrete / entailment configured (`clusterer = both`; `nli_backend:` not reported). The primary diagnostic reported here is the provision-level agreement statistic, which does not depend on the entailment channel. |
| Correctness resolver | provision (`judge = provision`, `judge_scope = representatives`) |
| Slice sizes | L7 = 100, L1 = 100 (100 matched pairs, matched on `pair_id`) |
| Crosswalk verified (facts.py) | no — entries carry `provenance.verified = false`; verification is outstanding |
| Total wall time | not reported |

## Per method (from `runs/<run_id>/e1_report.json`)

L7 AUROC is undefined for every method: all 100 scored L7 answers are incorrect, so the
slice has a single correctness class and no ranking exists. The value is undefined, not
zero. Risk at 50 % coverage on L7 is 1.000 for every method, which is the operational
form of the failure.

| Method | L7 AUROC [95% CI] | L1 AUROC [95% CI] | L1−L7 gap [95% CI] | L7 risk@50% | L7 nAURC |
|---|---|---|---|---|---|
| Discrete semantic entropy | undefined (single class) | 0.543 [0.487, 0.612] | undefined | 1.000 | undefined |
| Standard semantic entropy | undefined (single class) | 0.445 [0.333, 0.559] | undefined | 1.000 | undefined |
| SelfCheckGPT-style | undefined (single class) | 0.471 [0.356, 0.591] | undefined | 1.000 | undefined |
| 1 − majority agreement | undefined (single class) | 0.543 [0.487, 0.611] | undefined | 1.000 | undefined |
| 1 − p_true (v1 run provenance) | undefined (single class) | 0.574 [0.455, 0.684] | undefined | 1.000 | undefined |
| **Provision-level entropy (this work)** | undefined (single class) | **0.766 [0.670, 0.853]** | undefined | 1.000 | undefined |
| **1 − provision-level agreement (this work)** | undefined (single class) | **0.729 [0.622, 0.825]** | undefined | 1.000 | undefined |

## The two headline numbers

| Quantity | L7 | L1 |
|---|---|---|
| Collision population n (all samples assert the same provision) | 16 of 100 | 17 of 100 |
| Accuracy within the collision population | **0.000** | 0.882 |
| **Share unanimously wrong** (Wilson 95 % CI) | **1.000** [0.000, 0.194] (accuracy) | 0.118 [0.657, 0.967] (accuracy) |

Difference in the share unanimously wrong (L1 − L7): **0.882**, intervals non-overlapping.

Accuracy contrast: L1 0.434 (n = 99 scored, 1 excluded) − L7 0.000 (n = 100 scored)
= **+0.434**, bootstrap 95 % interval **[+0.333, +0.525]**.

Wording rule for any summary: correct is “16 of 100 L7 items entered the unanimous
provision-level collision population, and within that population 16 of 16 answers were
wrong.” Incorrect is “16 % of L7 answers are confidently wrong”, which applies a
subpopulation property to the whole slice.

## Gate G1

| Condition | Threshold | Measured | Met |
|---|---|---|---|
| Best sample-only AUROC on L7 | ≤ 0.70 | undefined for every method; the ceiling is therefore read from the collision statistic — L7 accuracy 0.000 with 16 unanimous provision-level items, all wrong (`ceiling_basis = collision-statistic`) | MET |
| Contrast: gap CI excludes 0 **or** unanimously-wrong difference | ≥ 0.20, non-overlapping intervals | AUROC gap not computable (L7 single class); unanimously-wrong difference +0.882 | MET |

**Verdict:** PASS

## One-paragraph reading

> On a matched-pair slice where the control and the target differ only in the era asked
> about, the model answered 43.4 % of the control questions correctly and none of the
> target questions; on the target slice every sample-only uncertainty score has undefined
> ranking ability and accepts only wrong answers in its most confident half. The
> provision-level statistic changes what is visible: unanimity that looks like
> confidence is, on the target slice, unanimity of a repeated legal error. This is an
> observed difference on one checkpoint and one slice, not a causal estimate, and the
> next run is the Phase B relation model, which asks whether typed legal relations change
> the cluster structure these numbers rest on.

## Failures and anomalies to carry forward

| What happened | How many items / which method | Suspected cause | Action |
|---|---|---|---|
| v1 run (`runs/phaseA-laptop`): 79.5 % of samples unresolved, 99.9 % on L1; apparent 0.000 accuracy on both slices | whole run | naive judge could not resolve answers to a provision, so correctness was never established | kept as a methods artifact; superseded by the re-judged run of record |
| Exact-text collision under-counts unanimity | L1 2 of 100, L7 0 of 100 at text level versus 17 and 16 at provision level | models paraphrase; agreement is legal, not lexical | provision-level statistics are the headline; text level is a printed diagnostic only |
| L7 AUROC undefined | all methods | every scored L7 answer is wrong: one correctness class | gate falls back to the collision statistic; undefined is reported as undefined |
| Repealed-code share of asserted codes | 98.4 % (L1), 83.2 % (L7) | aggregate share over samples, not items | flagged for validation; not a headline finding |
| Crosswalk entries unverified | `jurisuq/facts.py` | crosswalk not yet checked against the official successor schedule | verification outstanding; recorded in the guide's Section 11 |

## Freeze note

* L7 item ids frozen: **yes**. Hash of the dataset:
  `certutil -hashfile data/lexuq_slice.jsonl SHA256` →
  `45b2d194e9c2f623457481c0d7d02f36c6267ec65c0b75ee3df2be4c0d1d010a`
  (200 items, 100 L1 / 100 L7, matched pairs).
* Anything changed after seeing results? **Yes, declared.** Two changes were made after
  the first full run, and both are recorded here rather than edited away:
  1. the slice was rebuilt to revision 2 (era-reversed control: L7 = law in force today
     with gold BNS and the repealed IPC as the trap; L1 = law before 1 July 2024 with
     gold IPC and BNS as the trap), because the revision-1 same-era control produced
     almost no correct answers and nothing to contrast against;
  2. the judge was revised to extract the asserted provision per answer
     (`Verdict.asserted`) and the analysis was re-run over the stored answers with
     `scripts/05_rejudge.py` — no re-sampling was performed, and the pre-revision run
     lives at `runs/phaseA-laptop-v2` unchanged.
  No change was made to the metric definitions, the sampling configuration, or the
  frozen slice after the run of record.
## Structural composition of the frozen slices

The frozen instrument has `majority_correct = 43/100` on L1 and `0/100` on
L7. Every L7 item is resolved by the judge (`frac_unresolved = 0.000` on all
100 items). Across the 1,000 L7 stored answers, the verdict mix is
`stale_law = 832`, `wrong_section = 150`, and `other_provision = 18`.

The 150 `wrong_section` answers are exactly the 15 L7 items whose modal key is
BNS. They cite sections that mostly exceed BNS 2023's 358 sections, treating
IPC numbers as if they were BNS sections. The missing second correctness class
on L7 is therefore a property of the model under test, not of the judge and
not of the statute store.

## Model-cutoff explanation for the L7 result

The frozen Phase A run was generated by `qwen2.5-7b-instruct`, with provider
`openai-compat:qwen2.5-7b-instruct`, temperature `1.0`, `max_tokens = 220`,
and `n_samples = 10` (see `runs/phaseA-laptop-v2-rejudged/meta.json`). The
model's training data ends near the IPC/BNS transition, and it answers IPC
379 to a post-1 July 2024 theft question.

Accordingly, the L7 result — 0/100 items correct and 832/1,000 stored answers
labelled `stale_law` — is partly a model-cutoff artefact, not purely a
legal-reasoning failure. A model with post-2024 training data is required
before any L7-based gate, including G5, can be evaluated. This limitation is
a property of the model under test, not a defect in the instrument.
