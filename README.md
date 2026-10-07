# JURIS-UQ — Phase A: the instrument and the E1 diagnostic

Phase A is one experiment and one question:

> **Can only-sample-uncertainty methods detect a wrong legal answer at all, and
> do they collapse on questions whose correct answer changed in July 2024?**

Everything else in the project (legal relation clustering, material probes,
calibration, abstention) only makes sense if the answer to that question is
"they collapse". Phase A is therefore the smallest complete experiment that can
kill or confirm the premise, and it is designed to be finished in **two weeks**.

Deliverable of Phase A: `runs/<run_id>/` containing the sampled answers, the
E1 report (JSON), and the figure — plus one paragraph stating the gate verdict.
Gate **G1** passes when, on the diagnostic slice L7:

1. the best sample-only method stays at or below **0.70 AUROC** for detecting
   incorrect answers, **and**
2. either the L1-minus-L7 AUROC gap has a 95 % bootstrap interval excluding
   zero, **or** the share of *unanimously wrong* answers (zero semantic entropy,
   wrong answer) exceeds the L1 share by at least 20 points with non-overlapping
   Wilson intervals.

---

## 0. What is in this repository

```
jurisuq_code/
├── jurisuq/                  # the package (no heavy dependencies)
│   ├── config.py             # one JSON config per run, CLI overrides
│   ├── normalize.py           # conservative text normalisation + provision extraction
│   ├── metrics.py            # AUROC, AURC, nAURC, ECE, kappa, bootstraps
│   ├── cluster.py            # discrete + entailment clustering, entropy in bits
│   ├── generators.py         # LM Studio / llama-server client, and a mock model
│   └── judge.py              # correctness resolver (provision rules + optional LLM judge)
├── scripts/
│   ├── 00_env_check.py       # does this machine have what Phase A needs?
│   ├── 01_make_data.py       # builds the L7 / L1 diagnostic slice
│   ├── 02_run_inference.py   # the sampling harness (the expensive step)
│   ├── 03_analyze_e1.py      # E1 report + G1 verdict
│   └── 04_make_figure.py     # the figure for the paper
├── tests/                    # 40 unit tests + a stub OpenAI server
├── configs/phase_a.json      # your real run
├── configs/phase_a_smoke.json# plumbing run, no model needed
├── requirements.txt          # requests, numpy, matplotlib, pytest
├── requirements-nli.txt      # torch + transformers (optional, for standard SE)
└── run_phase_a.sh            # smoke | laptop | analyze | tests
```

No step needs the internet. The only network call is to the generator on your
own machine.

---

## 1. Day 0 — install (about 60 minutes)

### 1.1 Python and VS Code

1. Install **Python 3.11 or 3.12** from python.org. Tick *"Add python.exe to
   PATH"* in the installer. (3.13 also works; 3.11/3.12 have the widest wheel
   coverage for `torch`.)
2. Install **VS Code**, then install these extensions:
   * Python (Microsoft)
   * Jupyter (only if you want notebooks later)
   * Even Better TOML / JSON (cosmetic)
3. Open a terminal in VS Code (`Ctrl` + `` ` ``) and check:

```bash
python --version          # 3.11.x or 3.12.x
```

### 1.2 Get the code in place and make a virtual environment

```bash
# put the folder anywhere; this example uses D:\work
cd D:\work\jurisuq_code

python -m venv .venv
# Windows PowerShell:
.venv\Scripts\activate
# Windows cmd:
#   .venv\Scripts\activate.bat
# macOS / Linux:
#   source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

In VS Code, press `Ctrl+Shift+P` → *Python: Select Interpreter* → pick
`.venv`. Every command below is run from the repository root with the
environment active.

Optional, for standard semantic entropy (NLI clustering) — ~700 MB download:

```bash
pip install -r requirements-nli.txt
```

If you skip this, the harness still runs: it uses a clearly labelled lexical
proxy instead and records `nli_backend: lexical-proxy` in the run metadata, so
a proxy number can never be mistaken for a published method.

### 1.3 Install a generator (choose one)

**Option A — LM Studio (easiest, recommended for Phase A).**

1. Download LM Studio, install, open it.
2. Search and download a model. For this machine:
   * `Qwen2.5-7B-Instruct` **Q4_K_M** (~4.7 GB) — the default target; or
   * `Qwen2.5-3B-Instruct` **Q4_K_M** (~2 GB) if you want a faster first pass.
3. Load the model, set **context length 4096**, and in *Developer* tab start the
   **local server** (default port 1234).
4. Note the **model identifier** exactly as the server reports it — you will put
   it in the config. Verify:

```bash
curl http://127.0.0.1:1234/v1/models
```

**Option B — llama.cpp `llama-server`** (better on Intel Arc via SYCL/Vulkan
once you are comfortable):

```bash
llama-server -m path\to\Qwen2.5-7B-Instruct-Q4_K_M.gguf --port 1234 -c 4096 -ngl 99
```

Both expose the same OpenAI-compatible API, so nothing else changes.

---

## 2. Step 1 — point the config at your model

Open `configs/phase_a.json` and replace one line:

```json
"model": "REPLACE_WITH_YOUR_MODEL_ID"
```

with the id from `curl .../v1/models` (for LM Studio it usually looks like
`qwen2.5-7b-instruct`). Leave everything else as it is for the first run.

---

## 3. Step 2 — environment check

```bash
python scripts/00_env_check.py
```

Expected: all required packages `[ok]`, optional packages listed as warnings if
absent, and — with LM Studio running —

```
[ok]   generator endpoint reachable at http://127.0.0.1:1234/v1
       models: qwen2.5-7b-instruct
RESULT: ready. Next: python scripts/01_make_data.py
```

If the endpoint is not reachable, the rest still works: the data and analysis
scripts never touch the network.

---

## 4. Step 3 — build the diagnostic slice

```bash
python scripts/01_make_data.py --n-per-slice 100
```

Creates 200 items (100 L7 + 100 L1), 10 offences each, six question frames, six
neutral procedural contexts, so no two questions share the same text.

**Do this one task before you trust the numbers** (about an hour):

> Open `jurisuq/facts.py`. Each offence carries `old_act/old_provision` and
> `new_act/new_provision`. Check those rows against the official IPC → BNS
> successor mapping (the Schedule to the Bharatiya Nyaya Sanhita) and fill in
> `punishment` only where you have verified the successor's punishment text.
> Then set `"verified": True` in `scripts/01_make_data.py`.
>
> This is the only place in the whole pipeline where a quiet mistake would
> corrupt every number downstream, so it is the first thing to do — and it is
> exactly the kind of check a reviewer will ask about. The harness, metrics and
> analysis do not depend on it; the *slice* does.

---

## 5. Step 4 — the smoke test (5 minutes, no model)

Always do this before the expensive run. It exercises sampling, judging,
clustering, metrics, gate logic and the figure using a synthetic model whose
error behaviour is known.

```bash
bash run_phase_a.sh smoke          # or run the four commands individually
```

Expected on a healthy install: all four stages run, and the E1 report ends with
a verdict that reads sensibly. On a real 100+100 slice using the mock model the
gate logic prints **PASS** with a collision-population contrast around
`0.45 vs 0.03` — that is the mock's designed bias being detected, not a result.
If you see that, the instrument works end to end.

Also run the unit tests once:

```bash
bash run_phase_a.sh tests          # 40 passed
```

---

## 6. Step 5 — the real run

Budget first, because this is the expensive step. With M samples per item,
200 items and ~200 output tokens:

| samples M | tokens generated per item | 7B INT4 on the iGPU (≈12 tok/s) | 3B INT4 (≈22 tok/s) |
|-----------|---------------------------|--------------------------------|---------------------|
| 8         | ≈1,600                    | ≈7.5 h                         | ≈4 h                |
| 10        | ≈2,000                    | ≈9.3 h                         | ≈5 h                |

The sampling stage is **resumable**: every finished item is flushed to
`runs/<run_id>/items.jsonl` immediately. If the machine sleeps, the server
dies or you stop the run, just launch the same command again — it will skip the
items already recorded and continue from where it stopped.

Advice: start it before you sleep, leave the laptop plugged in, and stop Windows
from sleeping (Settings → System → Power → *Screen and sleep* → *Never* when
plugged in).

**Before the full run, pilot it.** `06_pilot.py` samples 12 items per slice with
3 samples each, prints what the model actually answered and how the judge scored
it, and refuses to bless a run whose judge does not work. It takes minutes.

```bash
python scripts/06_pilot.py --set model=qwen2.5-7b-instruct
```

Pass → start the full run. Fail → fix the cause first; the messages name it.

```bash
python scripts/02_run_inference.py --config configs/phase_a.json
```

Progress prints every 5 items with an ETA. Two knobs, if you need to cut the
budget in half: `--set n_samples=6` and `--set max_tokens=160`. Decide once,
before the run, and write down what you chose — do not tune it after seeing
results.

While it runs, the NLI channel (if installed) will download its checkpoint on
first use; that is a one-time ~700 MB.

---

## 7. Step 6 — analysis and figure

```bash
python scripts/03_analyze_e1.py --run-id phaseA-laptop
python scripts/04_make_figure.py  --run-id phaseA-laptop
```

The report prints four blocks:

* **per slice, per method** — AUROC with a bootstrap 95 % interval, normalised
  AURC, selective risk at 50 % coverage, and the accuracy of the returned
  answer;
* **the collision population** — items where every sample was identical
  (zero semantic entropy): how often that unanimous answer is wrong. This is
  the operational definition of a shared mistake and the number to quote;
* **L1 minus L7 gap per method** — positive means the method works on ordinary
  items and collapses on the superseded-provision items;
* **the G1 verdict** — the two conditions, each with its own line, and prose
  saying how to read the outcome.

Outputs: `runs/<run_id>/e1_report.json`, `fig_e1.png`, `fig_e1.svg`.
The figure has three panels: AUROC by slice, risk against coverage on L7, and
the unanimously-wrong share per slice.

---

## 8. Step 7 — record the result before you interpret it

Fill in `docs/results_phase_a.md` (template in this repo) with the run id, the
model, M, temperature, the four numbers per method, and the verdict. Write the
numbers down **before** discussing what they mean; this is the discipline that
keeps Phase D honest later, and it is what makes the E1 table in the paper
trustworthy.

---

## 9. Step 8 — the gate decision

* **PASS.** You have the diagnostic result that the whole project rests on.
  Freeze the L7 slice, note the run id, and move to Phase B (the legal relation
  model). The E1 table and figure go straight into Part VI of the guide.
* **Ceiling met, contrast not.** The model may simply not share the bias.
  Before changing anything: repeat the run with a smaller checkpoint (3B) and
  with `--set temperature=0.7`, keep the items identical, and compare. If the
  contrast still does not appear, the L7 slice needs items where the transition
  genuinely tempts the model (add the "which IPC section did it replace"
  framing, already template T4) or more items.
* **Ceiling not met (a sample-only method scores above 0.70 on L7).** Then
  sampling already detects the error and the diagnostic claim is weaker than
  designed. Do not force it. The honest move is report that result, and re-aim
  the paper at the calibration and abstention contributions — the instrument
  you built still serves those directly, and a negative result about
  consistency-based UQ in law is publishable when the measurement is clean.
* **AUROC undefined.** Every item fell in one correctness class (the model got
  the whole slice right or the whole slice wrong). Record more items, or use a
  second checkpoint; the report says so explicitly.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `generation request failed after 3 tries` | server stopped, model unloaded, or wrong port | reload the model; check `curl .../v1/models`; raise `--set retries=5` |
| Every sample identical on L7 *and* L1 | temperature 0, or the server ignores `temperature` | `--set temperature=1.0`, `--set top_p=1.0`; confirm in the server logs |
| `logprob_source: none`, `p_true` is `null` | your server does not return logprobs | expected; the four other methods are unaffected. `p_true` stays out of the paper |
| `nli backend: lexical-proxy` | `transformers`/`torch` not installed | `pip install -r requirements-nli.txt`, or report the discrete channel only |
| `AUROC ... nan` in the report | all items in one correctness class | add items or a second model — see §9 |
| Many `unresolved` verdicts | answers name no provision | run with `--set judge=llm` (uses your generator as a prompted judge), or shorten `max_tokens` so answers stay on point |
| Run died midway | sleep, crash, ctrl-c | re-run the identical command; it resumes |
| Out-of-memory on the laptop | context or batch too large | `--set max_tokens=160`, reduce LM Studio context to 4096, close the browser |

Result files are plain JSONL. If something looks wrong, open the first bad
record and read `sample_texts`, `sample_correct`, `sample_verdict_labels`: every
decision the instrument made is visible there, and that is what to paste when
asking for help.

---

## 11. What Phase A deliberately does not do

* no legal relation model, no legal polarity, no defeasibility (that is Phase B);
* no material perturbations and no internal model signals (Phase C);
* no calibrator, no conformal threshold, no abstention policy (Phase D);
* no annotation beyond the crosswalk verification — 200 items are enough to
  decide the premise, and annotation time is spent in Phase D where it changes
  the calibrated numbers.

Put differently: Phase A produces the measurement that tells you whether the
rest of the project is worth building. Two weeks now saves six weeks later.

---

## 12. Command reference

```bash
python scripts/00_env_check.py                                  # machine + endpoint
python scripts/01_make_data.py --n-per-slice 100                # build the slice
python scripts/02_run_inference.py --config configs/phase_a.json # sample (hours)
python scripts/03_analyze_e1.py --run-id phaseA-laptop           # E1 + gate
python scripts/04_make_figure.py  --run-id phaseA-laptop         # figure
python -m pytest -q                                             # tests

# cheap plumbing runs
python scripts/02_run_inference.py --config configs/phase_a_smoke.json
python tests/stub_openai_server.py --port 1234     # fake model, for client testing

# useful overrides (no file edits needed)
--set n_samples=8 --set temperature=0.7 --set clusterer=discrete
--set slices='["L7"]' --set limit=20 --set run-id=try2
```

---

## 13. The judge, and `05_rejudge.py` (read this if accuracy looks impossible)

The correctness resolver ("judge") decides 1/0 for every sampled answer, **after**
sampling. It has three outcomes, not two:

| Outcome | Meaning | Effect on metrics |
|---|---|---|
| correct | the operative provision in the answer is the in-force one | counts as 1 |
| incorrect | the answer asserts a provision other than the in-force one | counts as 0 |
| unresolved | no provision recognised, or several named without saying which applies | **excluded**, and counted in the report |

If accuracy comes out at exactly `0.000` on both slices with `nan` AUROC, the
judge could not read the answers — that is a judge problem, not a model problem,
and it does **not** require re-sampling. The answers are stored in
`runs/<run_id>/items.jsonl`, so re-score them:

```powershell
python scripts\05_rejudge.py --run-id phaseA-laptop --inspect   # what went wrong
python scripts\05_rejudge.py --run-id phaseA-laptop             # re-score stored answers
python scripts\03_analyze_e1.py --run-id phaseA-laptop-rejudged
python scripts\04_make_figure.py  --run-id phaseA-laptop-rejudged
```

The new run directory never overwrites the original. If the judge coverage stays
low (>10–15 % unresolved) after re-judging, either the model's answers genuinely
name no provision (then check `max_tokens` — the answer is being cut off) or you
should route the unresolved ones to the prompted judge with `--set judge=llm`.

What the judge now handles, each of which was a real failure mode:

* "…Section 103 of the BNS (formerly IPC 302, repealed w.e.f. 1 July 2024)" → correct;
* "…Section 302 IPC applies, and Section 103 BNS also applies" → unresolved, not
  guessed (guessing would flatter the model);
* `Section 103(1)` when the gold is `103` → correct; a *different* subsection of
  the right section → not that provision;
* a mention attributed to the wrong act → not a mention of that provision.


---

## 14. Revision 2 — what changed after the first real run, and why

The first laptop run (Qwen2.5-7B-Instruct, 200 items x 10 samples) reported
0.000 accuracy on both slices and `nan` AUROC. Diagnosis, from the stored
answers, found three separate defects. All three are fixed here.

**1. The judge counted "cannot resolve" as "wrong".** Every unresolved answer was
scored 0, which turned a parsing limitation into a fake accuracy of zero. The
judge now returns three outcomes — correct, incorrect, unresolved — and
unresolved answers are *excluded* and *counted* (the run prints the coverage,
and every report states how many items were excluded).

**2. The judge had no rule for act-level or foreign answers.** Answers like
"The Indian Penal Code would apply" name no section; one answer cited a South
African statute. Both are wrong answers, not unresolvable ones. The judge now
classifies them: `stale_law` (a provision of a code repealed on 1 July 2024),
`premature_law` (a BNS provision on a question about 2023), `wrong_section`
(same act, different section), `non_indian_act`, plus the unresolved kinds.

**3. The control slice was not a control.** L1 also asked about *today's* law,
which this model cannot answer at all, so L1 produced no correct answers and the
L7-versus-L1 comparison was degenerate — nothing to contrast against. L1 now
asks the **same facts, same frame, as the law stood immediately before 1 July
2024**, with the IPC section as the gold answer and the BNS successor as the
tempting answer. Each L7 item now has an L1 twin (`pair_id`), so the difference
between the slices isolates *staleness* from general inability.

A fourth change is not a bug fix but a measurement decision: the prompt is now
structured (`Provision: <Act>, section <n>` on the first line) and forbids citing
non-Indian law. The provision is then read from a field rather than parsed out of
prose, and the failure being measured is the temporal one rather than a mixture
of temporal and jurisdictional confusion. The non-Indian citations seen in
revision 1 remain on record and are reported separately — they are a finding, not
a discarded number.

**Do I have to re-run the model?** Yes, once: the questions changed (L1) and the
prompt changed, so the old answers cannot serve the new design. The old run is
kept: `runs/phaseA-laptop` remains the record of the staleness evidence
(40.9 % of L7 samples asserted the repealed provision as law in force).

**New order of work**

```powershell
python scripts\01_make_data.py --n-per-slice 100          # revision-2 slice
python scripts\06_pilot.py --set model=<your model>       # minutes: judge + prompt check
python scripts\02_run_inference.py --config configs\phase_a.json   # the full run
python scripts\03_analyze_e1.py --run-id phaseA-laptop
python scripts\04_make_figure.py  --run-id phaseA-laptop
```

The pilot exists because the first run's failure was discoverable in minutes and
was instead discovered after a night. If the pilot says the control slice is
unanswerable for your model, change the checkpoint then — not after a full run.

**When the ceiling is undefined.** If the model fails *every* scored item on L7,
AUROC has no second class to rank and is undefined. That is not a missing result:
the gate reads the ceiling from the collision statistic instead — the zero-entropy
answers are themselves wrong — and says so in the verdict. What it will not do is
report a number it cannot compute.


---

## 15. Revision 3 — measuring agreement at the provision level

The second laptop run (200 items, Qwen2.5-7B-Instruct, structured prompt) produced
the result the design was built to find:

```
L1 control (law before 1 July 2024):  accuracy 0.434   AUROC ~0.54  (chance)
L7 target  (law in force today)    :  accuracy 0.000   AUROC undefined
```

A 43-point accuracy collapse across the transition, on identical facts and
identical question frames, with agreement-based scores at chance. But the run
also reported *no zero-entropy items*, which is a measurement failure, not an
absence of the phenomenon.

**Why.** ``disc_se`` and the old collision statistic compared answer **strings**.
With the structured prompt the model paraphrases freely, so ten samples that all
assert `IPC 302` produced ten different sentences, zero text-level collisions and
a text entropy of 3.3 bits - looking like maximum uncertainty while being
perfectly unanimous about the law. The phenomenon is *one wrong provision
repeated*, so it has to be measured on provisions.

**What changed.**

1. The judge now returns, with every verdict, the **provision the answer
   asserts** (``asserted = {"act": ..., "provision": ...}``, ``FOREIGN`` for
   another legal order, ``None`` when nothing is named).
2. The pipeline clusters samples by that key and writes provision-level
   statistics into every record: ``prov_se`` (entropy in bits over asserted
   provisions), ``prov_agreement``, ``prov_all_same``, ``prov_majority``,
   ``prov_counts``, ``repealed_code_share``.
3. ``03_analyze_e1.py`` computes the collision population at the **provision
   level** by default (the text level is kept and printed for comparison, so the
   under-count is visible), reports the **accuracy contrast** with a bootstrap
   interval, and prints **what the model actually asserted** - the six most
   frequent modal provisions per slice, and the share of answers asserting a
   provision of a code repealed on 1 July 2024.
4. The figure's third panel is now "unanimous (same provision) and wrong".

**Do I have to re-run the model?** No. This is a scoring change, and the answers
are stored. Re-score them:

```powershell
python scripts\05_rejudge.py --run-id phaseA-laptop-v2
python scripts\03_analyze_e1.py --run-id phaseA-laptop-v2-rejudged
python scripts\04_make_figure.py --run-id phaseA-laptop-v2-rejudged
```

**What to expect in the re-judged report.** The L7 slice should now show a large
unanimous population (items where every sample asserted the same provision, very
likely the repealed one) with a high confidently-wrong share, and the gate's
collision contrast should separate L7 from L1 by a wide margin. Those two
numbers - the accuracy collapse and the confidently-wrong share - are the
diagnostic contribution of Part VI, and they are what Phase B improves on.

**One honest caveat to keep.** The control slice's AUROC is ~0.54, i.e. chance:
on the *old* law, where the model does have knowledge, its errors are ordinary
(individual samples deviate) and sampling still cannot rank them. That is a
second, independent piece of evidence for the same thesis, and it belongs in the
paper rather than being treated as a nuisance.

---

## 16. Phase B — the legal relation model (implemented, not yet trained)

Phase B adds one learned component — a classifier that decides the legal relation
between two answers — and four rules around it. The rules are what make the
component safe: identity is applied first and cannot be undone, a learned
equivalence can only merge, and a merge that would contradict a blocking relation
is skipped and counted.

### 16.1 What was added

| Path | What it is |
|---|---|
| `jurisuq/relations/schema.py` | the closed label set, the pair record and its validation |
| `jurisuq/relations/pairs.py` | template pair generation + the structural verifier |
| `jurisuq/relations/cluster_typed.py` | typed clustering: constraint, learned merge, cycle repair, canonicalisation |
| `jurisuq/relations/stats.py` | typed statistics (entropy, agreement, contradiction mass) and classification metrics |
| `jurisuq/relations/model.py` | pair serialisation, encoder + head, training, threshold selection, checkpoints |
| `scripts/10_build_relations.py` | builds, verifies and splits the pair dataset; writes the manifest |
| `scripts/11_train_relation.py` | fine-tunes the encoder, selects tau on dev, writes checkpoint metadata |
| `scripts/12_eval_relation.py` | test metrics, the E2 separation test on stored Phase A records, gate G2 |
| `configs/phase_b_relations.json` | dataset, encoder, training and gate settings |
| `data/relations/crosswalk_v1.jsonl` | provision link table (successor_of, different_offence) |
| `tests/test_relations.py` | 23 tests; 22 run without torch |

Phase B reads the Phase A artefacts and never writes into them: script 12 hashes
the whole Phase A run directory before and after evaluation and reports
`phase_a_untouched`. The Phase A code path is unchanged — if torch is not
installed, everything in `jurisuq/` still imports and the Phase A suite passes.

### 16.2 Install and run

```powershell
pip install -r requirements-relations.txt        # ~450 MB encoder download
python -m pytest tests -q                        # expect 76 passed, 1 skipped -> 0 skipped
python scripts\10_build_relations.py             # 330 pairs, 214/58/58, manifest + hashes
python scripts\11_train_relation.py --run-id phaseB-relations-01 --epochs 1 --limit 200
python scripts\12_eval_relation.py --run-id phaseB-relations-01 --phase-a-run phaseA-laptop-v2-rejudged
```

The one-epoch limited fine-tune is a smoke test: record the seconds per step it
prints, because that number — not any estimate — decides whether the full run is
an overnight job or an hour-long one.

Without a checkpoint, the harness still runs and is still informative:

```powershell
python scripts\12_eval_relation.py --run-id phaseB-relations-selftest --no-model --phase-a-run phaseA-laptop-v2-rejudged
```

It then labels relations by rule (identical key merges, a declared crosswalk link
merges, anything else splits). In the build sandbox that scored macro-F1 0.247 and
merge precision 0.7895 against an exact-key baseline of 0.776, and reported GATE
G2 NOT YET — which is the correct outcome: rule-only relations cannot beat exact
matching, and overturning that is the whole job of the learned model.

### 16.3 What is not verified here

Training, the encoder forward pass and the relation metrics have not been run on
your machine, and the numbers they produce are yours to record. The synthetic
pair set is also smaller than its design target and its test split is
template-generated: `manifest.json` carries `human_verified_test: false` until
1,500 pairs have been verified by hand, and no relation metric may be reported as
human-level until then.

### 16.4 Phase B on the target laptop — what was measured

Numbers from the first real runs on the Lenovo (Qwen not involved; encoder-only):

| Step | Setting | Result |
|---|---|---|
| InLegalBERT download | first `11_train_relation.py` | ~1.1 GB total (`.bin` + `safetensors`), cached under `%USERPROFILE%\.cache\huggingface` |
| `11` smoke | 1 epoch, `--limit 200` | 73 s for the epoch; dev macro-F1 0.333 vs exact-key baseline 0.776 (expected: undertrained) |
| `11` full | 3 epochs, 198 pairs | 161 s total (55.7 / 50.3 / 48.3 s per epoch); dev macro-F1 **0.777**, merge precision **0.903**, τ = 0.45 |
| `12` | — | crashed on two defects in the harness (fixed below) |

Three things follow from that table and are recorded in `configs/phase_b_relations.json`:

1. **CPU training is cheap here** — under three minutes for three epochs, so the design target of
   6,000 pairs is an overnight job, not a week. `epochs` is now 12: at 3 epochs the loss was still
   1.06 and the model was level with the exact-key baseline.
2. **A tie is not a pass.** 0.777 vs 0.776 is inside the noise of a 66-pair dev split; gate G2's
   "beats exact key" condition needs a real margin, which comes from more epochs *and* more data.
3. **The E2 pass must not spend the encoder on pairs the constraint already decides.** Samples
   asserting the identical provision are merged by rule, so those pairs are filled without a
   forward pass (`identity_pairs` in `cluster_typed.py`); the run prints both counts.

### 16.5 Fixes applied after the first `12_eval_relation.py` run

| Defect | Symptom | Fix |
|---|---|---|
| `UnboundLocalError: m` | E2 crashed whenever a checkpoint was loaded, because the sample count was assigned only in the rule branch | `m = len(texts)` hoisted above the branch; regression test in `tests/test_e2.py` |
| silent long run | no output while the encoder walked 200 items, so the run looked hung | progress line every N items with elapsed, items/s and ETA (`--progress`, default 10) |
| wasted forward passes | all M(M−1) ordered pairs sent to the encoder, including the ones step 1 decides | `identity_pairs` shortcut; the report records `encoder_pairs` and `rule_pairs` |
| no partial E2 | had to wait for the full pass to see anything | `--limit-items N` for a quick pass, `--skip-e2` for metrics only |
| `--source both` unusable | observed Phase A pairs stored `asserted: null`, so every one failed verification | assertions are now parsed from the stored text and the contribution is capped per item (`per_item=6`) |
