"""Consistency tests for the Phase G specification and reports.

These exist because the Phase G documents once asserted that no Phase G
specification or gate existed, which was false. A regression here is a
documentation error with real consequences, so the claim is pinned: the config
must agree with the report, the report must agree with the module's reason
codes, and the numbers printed in `PHASE-G.md` must be the numbers in the JSON.
"""
from __future__ import annotations

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
