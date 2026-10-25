"""Consistency tests for the Phase G specification and reports.

These exist because the Phase G documents once asserted that no Phase G
specification or gate existed, which was false. A regression here is a
documentation error with real consequences, so the claim is pinned: the config
must agree with the report, the report must agree with the module's reason
codes, and the numbers printed in `PHASE-G.md` must be the numbers in the JSON.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from jurisuq.evaluation import matrix as matrix_module

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "phase_g_target.json"
GUIDE = ROOT / "PHASE-G.md"
REPORT = ROOT / "runs" / "phaseG_eval_matrix.json"
DEPLOY = ROOT / "runs" / "phaseG_deployment.json"


def _load(path: Path) -> dict:
    if not path.is_file():
        pytest.skip(f"{path.name} not present")
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# the corrected specification status
# ----------------------------------------------------------------------
def test_config_declares_the_gate_as_defined_in_the_guide():
    config = _load(CONFIG)
    status = config["specification_status"]
    assert status["gate_defined_in_guide"] is True
    assert status["gate_defined_in_this_file"] is False
    assert status["gate"]["id"] == "G7"
    assert "§21.2" in " ".join(status["guide_sections"])


def test_config_gate_status_agrees_with_the_report():
    config = _load(CONFIG)
    report = _load(REPORT)
    assert config["specification_status"]["gate"]["status"] == report["gate_g7"]["status"]
    assert report["gate_g7"]["status"] == "NOT_MET"


def test_the_gate_is_recorded_as_failing_not_as_missing():
    config = _load(CONFIG)
    gate = config["specification_status"]["gate"]
    assert gate["status"] == "NOT_MET"
    assert "single correctness class" in gate["status_reason"]
    # a gate with no threshold must not smuggle one in
    assert gate["thresholds_introduced"] == []


def test_the_guide_document_states_the_gate_verdict():
    text = GUIDE.read_text(encoding="utf-8")
    assert "NOT_MET" in text
    assert "Gate G7" in text
    # the retracted claim may appear only inside the explicit correction note
    assert "**no Phase G specification**" not in text
    assert "fails when" in text or "fail condition" in text


# ----------------------------------------------------------------------
# reason codes
# ----------------------------------------------------------------------
def test_every_reason_code_in_the_config_exists_in_the_module():
    config = _load(CONFIG)
    known = {
        matrix_module.SINGLE_CLASS, matrix_module.CONSTANT_SCORE,
        matrix_module.METHOD_UNAVAILABLE, matrix_module.LOGPROBS_ABSENT,
        matrix_module.NO_SCORED_ITEMS, matrix_module.OUTSIDE_UNIT_INTERVAL,
        matrix_module.HARM_ABSENT, matrix_module.DEGENERATE,
    }
    configured = set(config["undefined_reason_codes"])
    assert known <= configured
    assert configured - known == {"not_instrumented", "no_data"}


def test_every_reason_used_in_the_report_is_documented():
    report = _load(REPORT)
    config = _load(CONFIG)
    documented = set(config["undefined_reason_codes"])
    used = set()
    for view in ("headline_matrix", "descriptive_matrix_all_items"):
        for block in report[view]["blocks"].values():
            for cell in block["cells"].values():
                used |= set(cell["undefined"].values())
    assert used <= documented, used - documented


def test_no_undefined_metric_is_silently_null():
    report = _load(REPORT)
    for view in ("headline_matrix", "descriptive_matrix_all_items"):
        for block in report[view]["blocks"].values():
            for key, cell in block["cells"].items():
                for name, value in cell["metrics"].items():
                    if value is None:
                        assert (name in cell["undefined"] or "all" in cell["undefined"]), \
                            f"{view}/{key}/{name} is null with no reason"


# ----------------------------------------------------------------------
# the published table must be the computed table
# ----------------------------------------------------------------------
_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")


def _guide_rows() -> list[list[str]]:
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index("| Method | L1 AUROC | L7 AUROC |")
    rows: list[list[str]] = []
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        match = _TABLE_ROW.match(line)
        if match:
            rows.append([cell.strip() for cell in match.groups()])
    return rows


def test_the_published_table_lists_every_declared_method():
    rows = _guide_rows()
    assert len(rows) == len(matrix_module.METHODS) == 9


def test_published_numbers_match_the_report():
    report = _load(REPORT)
    blocks = report["headline_matrix"]["blocks"]
    rows = _guide_rows()
    assert len(rows) == 9
    for row, method_key in zip(rows, report["headline_matrix"]["method_order"]):
        for cell_text, slice_name in zip(row[1:], ("L1", "L7")):
            published = blocks[slice_name]["cells"][method_key]
            if published["metrics"]["auroc"] is None:
                assert "undefined" in cell_text, f"{method_key}/{slice_name} should be undefined"
            else:
                expected = f"{published['metrics']['auroc']:.4f}"
                assert expected in cell_text, f"{method_key}/{slice_name}: {expected} not in {cell_text!r}"


def test_published_deployment_figures_match_the_report():
    if not DEPLOY.is_file():
        pytest.skip("deployment report not present")
    deployed = json.loads(DEPLOY.read_text(encoding="utf-8"))
    config = _load(CONFIG)["deployment"]["measurements"]["stage1_latency"]
    stage1 = deployed["stage1_latency"]
    assert config["n"] == stage1["n"]
    for documented, measured in (("median_s", "median"), ("p95_s", "p95"), ("max_s", "max")):
        assert config[documented] == pytest.approx(stage1[measured], abs=0.01)


# ----------------------------------------------------------------------
# integrity of the reports themselves
# ----------------------------------------------------------------------
def test_reports_contain_no_nan_or_infinity():
    for path in (REPORT, DEPLOY):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        json.loads(text)                       # parse strictly
        assert " NaN" not in text and "Infinity" not in text


def test_report_records_its_provenance():
    report = _load(REPORT)
    assert report["source_run_id"]
    assert report["inputs"]["dataset_sha256"]
    assert report["inputs"]["sources_unchanged_during_report"] is True
    assert report["split"]["verified_against_stored_split"] is True
    assert report["generated_by"].endswith("42_build_eval_matrix.py")


def test_report_has_no_pooled_block():
    report = _load(REPORT)
    assert report["headline_matrix"]["pooled"] is None
    assert report["descriptive_matrix_all_items"]["pooled"] is None


def test_report_marks_the_all_item_view_as_in_sample():
    report = _load(REPORT)
    descriptive = report["descriptive_matrix_all_items"]
    assert descriptive["out_of_sample_for_every_method"] is False
    assert "in-sample" in descriptive["caveat"]
    assert report["headline_matrix"]["out_of_sample_for_every_method"] is True


def test_report_lists_the_missing_evaluation_arms():
    report = _load(REPORT)
    arms = report["evaluation_arms"]
    missing = [item["arm"] for item in arms["generator"]["missing"]]
    missing += [item["arm"] for item in arms["slices"]["missing"]]
    assert any("API model" in arm for arm in missing)
    assert any("second laptop" in arm for arm in missing)
    assert any("external benchmark" in arm for arm in missing)
    for item in arms["generator"]["missing"] + arms["slices"]["missing"]:
        assert item["status"] == "deferred"
        assert item["reason"]


# ----------------------------------------------------------------------
# the API pilot is on hold — and stays that way until a human decides
# ----------------------------------------------------------------------
STATUS = ROOT / "runs" / "phaseG_pilot_status.json"

#: The approved DeepSeek plan, pinned by content hash. It was approved, then
#: never exercised (HTTP 402). If this changes, an approval was silently reused
#: or re-pointed at another provider, which is exactly what must not happen.
PINNED_PLAN_FILE_SHA256 = "77b5ce7c66c785107e532750ee408a54747c7eac4fb0b91936f3f3960b769f24"
PINNED_PLAN_HASH = "eb06ed62db637c89110a4a2a511f65164d3ff990638c66832c1a6aa16e30ecc9"
PINNED_CONFIG_SHA256 = "fe77951adea8f0a3b3558ad4303c7412ae5973793c0d03f5df60da285d1c4045"


def _sha256_content(path: Path) -> str:
    """SHA-256 of a file's content, with CRLF line endings read as LF.

    The pinned digests fingerprint the content Git stores (LF). A Windows
    checkout with ``core.autocrlf=true`` materialises the same content as CRLF,
    so hashing the raw bytes there reported a mismatch on a file nobody had
    touched. Normalising only ``CRLF -> LF`` makes the check independent of the
    checkout's line-ending policy while still failing on any real edit.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_pilot_status_record_exists_and_says_on_hold():
    status = _load(STATUS)
    assert status["status"] == "ON_HOLD"
    assert status["phase"] == "G"


def test_hold_is_recorded_as_not_a_scientific_finding():
    status = _load(STATUS)
    assert "not a scientific finding" in status["headline"].lower()
    assert "not evidence of a failed detector" in status["headline"].lower()
    assert status["no_network_during_cleanup"]["api_requests_made"] == 0


def test_gate_verdicts_are_unchanged_by_the_hold():
    status = _load(STATUS)["gates_unchanged"]
    assert status == {"G5": "NOT_EVALUABLE", "G6": "NOT_MET", "G7": "NOT_MET"}


def test_the_three_states_are_distinguished():
    status = _load(STATUS)
    assert status["completed"], "completed work must be enumerated"
    assert status["attempted_unsuccessful"]["requests_succeeded"] == 0
    assert status["attempted_unsuccessful"]["generations_obtained"] == 0
    held = {item["item"] for item in status["on_hold"]}
    assert any("smoke" in item.lower() for item in held)
    assert any("240-request" in item for item in held)


def test_the_failed_attempt_is_recorded_honestly():
    attempt = _load(STATUS)["attempted_unsuccessful"]
    assert attempt["http_status"] == 402
    assert attempt["requests_attempted"] == 2
    assert attempt["cost_incurred_usd"] == 0.0
    assert "reported by the principal investigator" in attempt["observation_source"]
    # the report is not in the repo; the record must say so rather than imply it was read
    assert "not present in this repository" in attempt["report_location"]


def test_restart_conditions_are_recorded():
    conditions = _load(STATUS)["restart_conditions"]
    assert len(conditions) >= 5
    assert any("zero-cost" in c for c in conditions)
    assert any("smoke check succeeds" in c for c in conditions)
    assert any("model ID" in c for c in conditions)


def test_hold_reason_names_the_free_tier_shortfall():
    reason = _load(STATUS)["hold_reason"]
    evidence = " ".join(str(e["finding"]) for e in reason["evidence"])
    assert "20 requests per day" in evidence
    assert "402" in evidence


def test_no_substitute_provider_was_wired_in():
    held = {item["item"]: item["status"] for item in _load(STATUS)["on_hold"]}
    provider_entry = [v for k, v in held.items() if "configuration" in k][0]
    assert provider_entry == "NOT IMPLEMENTED"
    assert not (ROOT / "configs" / "phase_g_pilot_free.json").exists(), \
        "a free-provider config must not exist while the pilot is on hold"


def test_the_approved_deepseek_plan_is_byte_identical():
    plan = ROOT / "runs" / "phaseG_pilot_plan.json"
    assert _sha256_content(plan) == PINNED_PLAN_FILE_SHA256
    assert json.loads(plan.read_text())["plan_sha256"] == PINNED_PLAN_HASH


def test_the_deepseek_configuration_is_unmodified_and_still_deepseek():
    config = _load(ROOT / "configs" / "phase_g_pilot.json")
    assert _sha256_content(ROOT / "configs" / "phase_g_pilot.json") == PINNED_CONFIG_SHA256
    assert config["generator"]["model"] == "deepseek-flash"
    assert config["generator"]["base_url"] == "https://api.deepseek.com/v1"
    assert "api_key" not in config["generator"]


def test_integrity_hashes_are_line_ending_agnostic(tmp_path):
    """The same content must hash identically whether checked out LF or CRLF."""
    source = (ROOT / "runs" / "phaseG_pilot_plan.json").read_bytes()
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    lf.write_bytes(source.replace(b"\r\n", b"\n"))
    crlf.write_bytes(lf.read_bytes().replace(b"\n", b"\r\n"))
    # the fixture must really differ on disk, or this test proves nothing
    assert lf.read_bytes() != crlf.read_bytes()
    assert _sha256_content(lf) == _sha256_content(crlf) == PINNED_PLAN_FILE_SHA256


def test_integrity_hash_still_detects_a_real_content_edit(tmp_path):
    """Normalising line endings must not blunt the check it protects."""
    source = (ROOT / "configs" / "phase_g_pilot.json").read_bytes()
    edited = tmp_path / "edited.json"
    edited.write_bytes(source.replace(b'"deepseek-flash"', b'"some-other-model"'))
    assert edited.read_bytes() != source, "fixture edit did not apply"
    assert _sha256_content(edited) != PINNED_CONFIG_SHA256
    # a trailing-newline-only change is also a real change
    denewlined = tmp_path / "denewlined.json"
    denewlined.write_bytes(source.replace(b"\r\n", b"\n").rstrip(b"\n"))
    assert _sha256_content(denewlined) != PINNED_CONFIG_SHA256


def test_status_record_and_config_agree_on_the_plan_hash():
    status = _load(STATUS)["approved_pilot_plan"]
    config = _load(CONFIG)["pilot_status"]
    plan = json.loads((ROOT / "runs" / "phaseG_pilot_plan.json").read_text())
    assert status["plan_sha256"] == config["approved_plan_sha256"] == plan["plan_sha256"]


def test_config_status_block_matches_the_status_record():
    config = _load(CONFIG)["pilot_status"]
    status = _load(STATUS)
    assert config["status"] == status["status"] == "ON_HOLD"
    assert config["generations_obtained"] == status["attempted_unsuccessful"]["generations_obtained"]
    assert config["is_scientific_finding"] is False


# ----------------------------------------------------------------------
# the documentation must not drift back to claiming a live/completed pilot
# ----------------------------------------------------------------------
def test_phase_g_guide_leads_with_the_hold():
    text = GUIDE.read_text(encoding="utf-8")
    assert "## API pilot: ON HOLD" in text
    assert "resource-driven postponement" in text
    # the retracted no-gate claim must not reappear outside the correction note
    assert "no gate number" not in text.split("## Specification status")[1]


def test_readme_states_the_hold_and_the_gate_position():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "API pilot: ON HOLD" in text
    assert "HTTP 402" in text
    assert "No Phase G gate is defined" not in text, "the retracted claim must not reappear"


def test_docs_do_not_claim_the_pilot_completed():
    for path in (GUIDE, ROOT / "README.md", ROOT / "DEPLOYMENT-GUIDE.md"):
        text = path.read_text(encoding="utf-8").lower()
        assert "pilot completed" not in text
        assert "pilot has completed" not in text
        assert "objectives have been met" not in text


def test_deployment_guide_warns_the_paid_paths_are_held():
    text = (ROOT / "DEPLOYMENT-GUIDE.md").read_text(encoding="utf-8")
    assert "API pilot is on hold" in text
    assert "--run" in text and "spend money" in text


def test_the_runner_still_refuses_to_overwrite_a_run_directory():
    source = (ROOT / "scripts" / "44_phase_g_pilot.py").read_text(encoding="utf-8")
    # both the smoke and the pilot path route through the shared guard
    assert source.count("ensure_fresh_run_dir(") == 2, "both paid paths must use the guard"
    # and the runner never falls back to a different provider on failure
    assert "fallback" not in source.lower()


# ----------------------------------------------------------------------
# Stage 2, step 1: the candidate-set contract is documented, not implied
# ----------------------------------------------------------------------
def test_the_guide_documents_the_stage_2_candidate_contract():
    text = GUIDE.read_text(encoding="utf-8")
    assert "Stage 2, step 1" in text
    assert "provenance.verified" in text
    assert "data_sha256" in text


def test_the_guide_does_not_claim_stage_2_ran():
    """No candidate item set exists; the documents must not imply one was made."""
    text = GUIDE.read_text(encoding="utf-8").lower()
    for claim in ("stage 2 is complete", "stage 2 completed", "stage 2 has run",
                  "candidate items were authored"):
        assert claim not in text, f"PHASE-G.md claims {claim!r}"


def test_the_documents_say_no_candidate_set_exists():
    text = GUIDE.read_text(encoding="utf-8")
    assert "does not exist" in text or "no candidate item set" in text.lower()


def test_the_screen_cannot_bypass_the_candidate_contract():
    """The check must run inside the screen, before any generator is built."""
    source = (ROOT / "scripts" / "41_screen_target_yield.py").read_text(encoding="utf-8")
    assert "validate_candidates(" in source
    # validation of the whole set happens before the cap, and before generation
    assert source.index("validate_candidates(") < source.index("make_generator(")


def test_the_published_test_counts_match_the_files():
    """The counts printed in the guide must be the counts the files collect.

    This guard counts itself, so adding a documentation guard means updating
    the published figures in `PHASE-G.md` in the same change. That is the
    point: the guide's test record must not drift from the files.
    """
    import subprocess
    import sys as _sys
    expected = {
        "test_target_population": 34, "test_target_screen": 22,
        "test_target_candidates": 52, "test_eval_matrix": 39,
        "test_deployment_metrics": 32, "test_phase_g_docs": 44,
        "test_pilot_guard": 57,
    }
    text = GUIDE.read_text(encoding="utf-8")
    total = sum(expected.values())
    assert f"| Phase G tests now | {total}" in text
    for name, count in expected.items():
        proc = subprocess.run([_sys.executable, "-m", "pytest",
                               str(ROOT / "tests" / f"{name}.py"), "-q",
                               "--collect-only"],
                              capture_output=True, text=True, cwd=str(ROOT))
        assert f"{count} tests collected" in proc.stdout, \
            f"{name}: guide says {count}; pytest collected " \
            f"{proc.stdout.strip().splitlines()[-1] if proc.stdout else 'nothing'}"


# ----------------------------------------------------------------------
# Phase G Stage 2 report
# ----------------------------------------------------------------------
STAGE2 = ROOT / "PHASE-G-STAGE2.md"


def test_the_stage_2_report_exists_and_is_linked():
    assert STAGE2.is_file()
    assert "PHASE-G-STAGE2.md" in README_TEXT()


def README_TEXT():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_stage_2_report_states_the_blocker_not_a_result():
    text = STAGE2.read_text(encoding="utf-8").lower()
    assert "blocked" in text
    assert "connection refused" in text
    assert "0 generations" in text or "no generation" in text


def test_the_stage_2_report_does_not_claim_g7_moved():
    text = STAGE2.read_text(encoding="utf-8").lower()
    for claim in ("g7 pass", "g7 is met", "gate g7 passed", "g7 now passes"):
        assert claim not in text, f"the report claims {claim!r}"
    assert "not_met" in text


def test_the_stage_2_report_says_the_mock_is_not_evidence():
    text = STAGE2.read_text(encoding="utf-8").lower()
    assert "must never be cited as a yield" in text
    assert "meaningless" in text


def test_the_stage_2_report_distinguishes_review_from_human_approval():
    text = STAGE2.read_text(encoding="utf-8")
    assert "not human legal approval" in text.lower()
    assert "PENDING_HUMAN_REVIEW" in text
