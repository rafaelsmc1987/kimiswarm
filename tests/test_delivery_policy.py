import json

from kdrx.cli import main
from kdrx.reporting import citation_integrity_gate
from kdrx.runner import run_file_research
from kdrx.state import RunState


def test_invented_qualitative_statement_blocks():
    gate = citation_integrity_gate(
        "The treatment is effective for every patient.", sources=[], claims=[], spans=[]
    )
    assert gate.blocking()
    assert any(
        c.check_id == "MATERIAL_UNREGISTERED" and not c.passed for c in gate.checks
    )


def test_revalidation_revokes_obsolete_seal(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    result = run_file_research(corpus, "latency under load", tmp_path / "runs")
    assert result["exit_code"] == 0
    state = RunState(tmp_path / "runs", result["run_id"])
    assert main(["seal", "--run-dir", str(state.run_dir), "--json"]) == 0
    state.write_text("delivery/report.md", "An invented treatment cures every disease.")
    assert main(["seal", "--run-dir", str(state.run_dir), "--json"]) == 1
    assert state.load_manifest().metadata["seal"]["eligible"] is False
    delivery = json.loads(state.read_text("delivery-manifest.json"))
    assert delivery["final_integrity_pass"] is False
    assert main(["verify-delivery", "--run-dir", str(state.run_dir)]) == 1


def test_verified_boolean_cannot_override_wrong_span_or_missing_commits(tmp_path):
    from kdrx.application.delivery import verify_snapshot

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    result = run_file_research(corpus, "latency under load", tmp_path / "runs")
    state = RunState(tmp_path / "runs", result["run_id"])
    assert verify_snapshot(state).deliverable
    spans = [
        json.loads(line)
        for line in state.read_text("evidence/spans.jsonl").splitlines()
    ]
    spans[0]["verified"] = True
    spans[0]["locator"]["char_start"] = 1
    state.write_text(
        "evidence/spans.jsonl", "\n".join(json.dumps(span) for span in spans)
    )
    assert verify_snapshot(state).gate_results["evidence_provenance"] == "fail"
    with state.store.transaction() as db:
        db.execute("DELETE FROM tasks WHERE run_id=?", (state.run_id,))
    assert verify_snapshot(state).gate_results["task_commits"] == "fail"
