import base64
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from kdrx.application.service import ApplicationService, KernelRequest
from kdrx.state import RunState


def test_parallel_objectives_stay_literal_and_separate(tmp_path):
    objectives = ['Aspas " e ação; $(whoami) & | < >', "Segundo objetivo independente"]

    def submit(text):
        request = KernelRequest(
            operation="plan", objective=text, runs_root=str(tmp_path)
        )
        payload = base64.b64encode(request.model_dump_json().encode()).decode()
        process = subprocess.run(
            [sys.executable, "-m", "kdrx.cli", "request", "--payload-base64", payload],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert process.returncode == 0, process.stderr
        return json.loads(process.stdout)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, objectives))
    assert results[0]["run_id"] != results[1]["run_id"]
    for output, objective in zip(results, objectives):
        state = RunState(tmp_path, output["run_id"])
        contract = json.loads(state.read_text("research_contract.json"))
        assert contract["objective"] == objective
        assert any(
            event.get("receipt_id") == output["receipt_id"]
            for event in state.iter_events()
        )


def test_unknown_capability_never_falls_back_to_fixture(tmp_path):
    import pytest

    request = KernelRequest(
        operation="research", objective="Live question", runs_root=str(tmp_path)
    )
    with pytest.raises(ValueError, match="live backend is disabled"):
        ApplicationService(tmp_path).dispatch(request)
