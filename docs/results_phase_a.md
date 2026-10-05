# Phase A results — E1 common-mode diagnostic

Fill this in the same day the run finishes, before interpreting anything.
Copy the file to `results_phase_a_<date>.md` and keep it; these are the numbers
that go into the E1 table of the paper.

## Run identity

| Field | Value |
|---|---|
| Run id | |
| Date / machine | |
| Generator (name + quantisation) | |
| Sampling: M, temperature, top_p, max_tokens | |
| Clustering channels used | discrete / entailment (`nli_backend:` ______) |
| Correctness resolver | provision / cascade(provision+LLM) |
| Slice sizes | L7 = ____, L1 = ____ |
| Crosswalk verified (facts.py) | yes / no |
| Total wall time | |

## Per method (from `runs/<run_id>/e1_report.json`)

| Method | L7 AUROC [95% CI] | L1 AUROC [95% CI] | L1−L7 gap [95% CI] | L7 risk@50% | L7 nAURC |
|---|---|---|---|---|---|
| Discrete semantic entropy | | | | | |
| Standard semantic entropy | | | | | |
| SelfCheckGPT-style | | | | | |
| 1 − majority agreement | | | | | |
| 1 − p_true (if logprobs) | | | | | |

## The two headline numbers

| Quantity | L7 | L1 |
|---|---|---|
| Collision population n (all samples identical) | | |
| Accuracy within the collision population | | |
| **Share unanimously wrong** (Wilson 95 % CI) | | |

## Gate G1

| Condition | Threshold | Measured | Met |
|---|---|---|---|
| Best sample-only AUROC on L7 | ≤ 0.70 | | |
| Contrast: gap CI excludes 0 **or** unanimously-wrong difference | ≥ 0.20, non-overlapping intervals | | |

**Verdict:** PASS / NOT YET

## One-paragraph reading (write in your own words)

> What the numbers say, what they do not say, and what the next run is if this
> one is negative. Two or three sentences. No adjectives.

## Failures and anomalies to carry forward

| What happened | How many items / which method | Suspected cause | Action |
|---|---|---|---|
| | | | |

## Freeze note

* L7 item ids frozen: yes / no. If yes, record the file hash:
  `certutil -hashfile data/lexuq_slice.jsonl SHA256` →
* Anything changed after seeing results? If yes, say exactly what and why.
  (A change made after seeing results is legitimate but must be declared.)
