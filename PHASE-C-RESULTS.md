# JURIS-UQ Phase C Results

This is the single consolidated Phase C record. It supersedes the earlier
pre-verification section that reported 0/48 and records the current state
without treating secondary-source corroboration as primary-source verification.

## Status

**Partially complete.** The verification workflow, table rebuild, schema
validation, context-pack integrity checks, and automated tests pass. The legal
verification is not complete because India Code could not be inspected from
this environment, and eight rows contain unresolved subsection or crosswalk
issues.

## 1. Identity and scope

| Field | Value |
|---|---|
| Source run (read-only) | `runs/phaseA-laptop-v2-rejudged` (200 items) |
| Output run | `runs/phaseA-laptop-v2-rejudged+ctx` |
| As-of date / jurisdiction | `2026-10-01` / `IN` |
| Statute table | `data/statutes/statutes_v1.jsonl` |
| Link table | `data/relations/crosswalk_v1.jsonl` |
| Scope | 10 frozen offence clusters; not a complete Indian criminal-law corpus |

The table currently contains **48 rows: 24 IPC and 24 BNS**. All rows parse as
JSON and validate against the closed schema used by `jurisuq.context.statute`.
The schema is unchanged: `act`, `section`, `title`, `text_excerpt`,
`in_force_from`, `in_force_until`, `successor`, `predecessor`,
`offence_cluster`, `consequence_class`, and `verified`.

## 2. Verification evidence and counts

The command
`python scripts\22_verify_statutes.py --apply` read all 48 checklist rows:
40 were marked `verified_ok=yes` and 8 were marked `verified_ok=no`. The table
was then rebuilt with
`python scripts\20_build_statutes.py --out data\statutes\statutes_v1.jsonl`.

| Evidence category | Rows | Interpretation |
|---|---:|---|
| Primary-source verified | 0 | No India Code provision text or Gazette text was directly inspected in this environment. |
| Secondary-source supported | 40 | Checklist and overrides record devgan.in and other legal-reference pages, including MHA S.O. 850(E) commencement evidence; these are not independent primary-source verification. |
| Unresolved | 8 | Mapping/subsection issues listed in §3; these remain `verified: false`. |
| Total | 48 | No rows were deleted or omitted. |

Recorded secondary-source references include the devgan.in IPC/BNS section
pages and, where noted in the checklist, iPleaders, Drishti Judiciary,
Indian Kanoon, WritingLaw, VakeelSaab, LawRato, Ramsnehi Mishra, LawNotes,
PrimeLegal, and MHA notification S.O. 850(E), dated 23-Feb-2024. The checklist
is the authoritative record of which reference was associated with each row.

Direct official URLs attempted during this audit included:

* India Code IPC sections 344, 345, 409, and 468:
  `https://indiacode.nic.in/show-data?actid=AC_CEN_5_23_00001_186045_1523266833514&sectionId=...`
* India Code BNS act page:
  `https://www.indiacode.nic.in/handle/123456789/7055`

Those requests returned HTTP 403, so they are recorded as access attempts, not
as inspected evidence. No row is described here as officially verified.

## 3. Unresolved rows and required decisions

| Row | Current mapping/content | Reason unresolved |
|---|---|---|
| `IPC 409` | successor `BNS 316(4)` | Secondary sources consistently indicate the public-servant/banker provision is BNS 316(5); the frozen crosswalk says 316(4). |
| `BNS 316(4)` | public-servant/banker text | The row label conflicts with the text under the secondary-source numbering; changing it would alter the frozen crosswalk. |
| `IPC 468` | successor `BNS 336` | The excerpt corresponds specifically to BNS 336(3), while the table uses the root section. |
| `BNS 336` | forgery-for-cheating text | Root-section versus subsection convention is unresolved; the specific provision may be 336(3). |
| `IPC 344` | successor `BNS 127(4)` | Exact BNS subsection numbering was not confirmed from an inspected primary text. |
| `BNS 127(4)` | ten-day confinement text | Same subsection-numbering uncertainty. |
| `IPC 345` | successor `BNS 127(5)` | Exact BNS subsection numbering was not confirmed from an inspected primary text. |
| `BNS 127(5)` | writ-related confinement text | Same subsection-numbering uncertainty. |

The existing values were deliberately preserved. No mapping was changed during
this audit. The earlier `IPC 506` / `BNS 351(2)` concern remains resolved in
the checklist based on the recorded secondary evidence, but it is likewise
not counted as primary-source verification.

## 4. Integrity measurements

| Measurement | Current result |
|---|---:|
| Rows / IPC / BNS | 48 / 24 / 24 |
| Verified flags in JSONL | 40 / 48 (0.8333333333333334) |
| JSONL line endings | LF |
| Current SHA-256 | `20c98b74c0855c5ec4c8cda2b2d52388ea5f3e8d2514376f56db425bdd90b21e` |
| Expected post-verification SHA-256 | `20c98b74c0855c5ec4c8cda2b2d52388ea5f3e8d2514376f56db425bdd90b21e` |
| Hash comparison | **MATCH** |
| Canonical no-overrides hash | `7be783e38c21effb24734a8be5400b9bd0c358d63130bb896aa13220ea09b61f` |

The current hash intentionally differs from the no-overrides hash because 40
rows have `verified: true`. The JSONL was serialized by script 20 using UTF-8,
`ensure_ascii=True`, one JSON object per line, and explicit LF newlines; the
hash is SHA-256 over the resulting bytes. The CRLF backup remains untouched.

The context-pack measurements remain 200 items, 611 assertion lookups, 421
known, 190 unknown, coverage `0.689034`, and 17 excluded sentinel assertions.
The recorded `in_force` counts are False 492, True 208, and None 190.
`phaseA-laptop-v2-rejudged` was not modified.

## 5. Commands and test results

Executed from `E:\PROJECTS\JURIS-UQ\jurisuq_code`:

```powershell
.\.venv\Scripts\python.exe scripts\22_verify_statutes.py --apply
.\.venv\Scripts\python.exe scripts\20_build_statutes.py --out data\statutes\statutes_v1.jsonl
.\.venv\Scripts\python.exe -m pytest tests\test_context.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Results:

* Verification apply: 40 yes, 8 no, 48 checked; no unmatched keys.
* Rebuild: 48 rows, 10/10 offence clusters, 40 verified; hash matched above.
* Focused Phase C suite: **31 passed**.
* Full suite: **112 passed**.

The initial focused-test attempt used an absolute test path from the parent
directory and failed import collection (`ModuleNotFoundError: jurisuq`); it was
rerun from the project root and passed. This was an invocation-location issue,
not a code or test failure.

## 6. Remaining blockers and next action

Before Phase C can be called complete or a Phase D result can rely on these
rows, inspect the enacted BNS text through an accessible official source and:

1. Decide and document whether `IPC 409` maps to `BNS 316(4)` or `316(5)`.
2. Confirm the exact BNS 127 subsections for IPC 344 and 345.
3. Decide whether the crosswalk convention uses `BNS 336` or `BNS 336(3)`.
4. If any value changes, update the frozen crosswalk and table through the
   project scripts, record the primary URL/text inspected, rerun both test
   suites, and recompute the hash.

Only after those decisions and primary-source checks should the Phase C files
be committed. No commit, push, reset, clean, or discard operation was run.
