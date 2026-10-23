import importlib.util
import sys

from jurisuq.relations.cluster_typed import typed_cluster


SCRIPT = "scripts/13_attach_typed.py"


def load_script():
    spec = importlib.util.spec_from_file_location("attach_typed", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def partition(keys, labels):
    groups = {}
    for key, label in zip(keys, labels):
        groups.setdefault(label, []).append(key)
    return sorted(sorted(group) for group in groups.values())


def test_typed_clustering_partition_is_order_independent():
    keys = ["IPC 420", "BNS 318", "IPC 420", "NONE"]
    relation = [
        ["SAME_PROVISION", "LEGALLY_EQUIVALENT", "SAME_PROVISION", "AMBIGUOUS"],
        ["LEGALLY_EQUIVALENT", "SAME_PROVISION", "LEGALLY_EQUIVALENT", "AMBIGUOUS"],
        ["SAME_PROVISION", "LEGALLY_EQUIVALENT", "SAME_PROVISION", "AMBIGUOUS"],
        ["AMBIGUOUS", "AMBIGUOUS", "AMBIGUOUS", "SAME_PROVISION"],
    ]
    scores = [[1.0 if i == j else 0.9 for j in range(4)] for i in range(4)]
    first = typed_cluster(keys, relation, scores, 0.5)
    order = [2, 0, 3, 1]
    shuffled_keys = [keys[i] for i in order]
    shuffled_relation = [[relation[i][j] for j in order] for i in order]
    shuffled_scores = [[scores[i][j] for j in order] for i in order]
    second = typed_cluster(shuffled_keys, shuffled_relation, shuffled_scores, 0.5)
    assert partition(keys, first.labels) == partition(shuffled_keys, second.labels)


def test_all_identical_keys_yield_one_cluster():
    keys = ["IPC 420", "IPC 420", "IPC 420"]
    relation = [["SAME_PROVISION"] * 3 for _ in keys]
    scores = [[1.0] * 3 for _ in keys]
    result = typed_cluster(keys, relation, scores, 0.5)
    assert result.labels == [0, 0, 0]
    assert result.canonical == ["IPC 420"]


def test_typed_script_refuses_existing_output_without_force(tmp_path, monkeypatch, capsys):
    script = load_script()
    runs = tmp_path / "runs"
    source = runs / "source"
    source.mkdir(parents=True)
    (source / "items.jsonl").write_text("{}\n", encoding="utf-8")
    (runs / "source+typed").mkdir()
    monkeypatch.setattr(script, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [SCRIPT, "--run-id", "source", "--out-suffix", "+typed",
         "--runs-dir", str(runs)],
    )
    assert script.main() == 1
    assert "already exists" in capsys.readouterr().out
