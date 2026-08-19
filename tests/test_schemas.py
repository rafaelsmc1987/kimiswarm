"""Schema round-trip, gate composition and JSON-schema export."""

from __future__ import annotations

import json

from kdrx.schemas import SCHEMAS, export_json_schemas
from kdrx.schemas.enums import GateKind
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.request import ResearchContract


def test_all_15_canonical_schemas_present():
    assert set(SCHEMAS) == {
        "ResearchRequest",
        "ResearchContract",
        "ResearchPlan",
        "TaskSpec",
        "AgentBrief",
        "AgentResult",
        "SourceRecord",
        "EvidenceSpan",
        "Claim",
        "ClaimEvidenceEdge",
        "ContradictionCluster",
        "GateDecision",
        "ArtifactRecord",
        "RunManifest",
        "DeliveryManifest",
    }


def test_contract_round_trip():
    c = ResearchContract(
        contract_id="C1",
        objective="x",
        languages=["en", "pt"],
        route="R1",
    )
    data = c.model_dump_json()
    c2 = ResearchContract.model_validate_json(data)
    assert c2.contract_id == "C1"
    assert c2.languages == ["en", "pt"]
    assert c2.route.value == "R1"


def test_extra_fields_are_forbidden():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResearchContract(contract_id="C1", objective="x", not_a_field=1)


def test_gate_compose_pass_and_fail():
    passed = GateDecision.compose(
        "g", GateKind.PLAN, [GateCheck(check_id="c", description="d", passed=True)]
    )
    assert passed.verdict.value == "pass"
    assert passed.passed() and not passed.blocking()

    failed = GateDecision.compose(
        "g", GateKind.PLAN, [GateCheck(check_id="c", description="d", passed=False)]
    )
    assert failed.verdict.value == "fail"
    assert failed.blocking()


def test_gate_compose_warn_is_pass():
    warn = GateDecision.compose(
        "g",
        GateKind.CITATION,
        [GateCheck(check_id="c", description="d", passed=False)],
        warn_is_pass=True,
    )
    assert warn.verdict.value == "warn"
    assert warn.passed()


def test_export_json_schemas(tmp_path):
    written = export_json_schemas(tmp_path)
    assert len(written) == 15
    for name, path in written.items():
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema.get("type") == "object"
        assert schema.get("title") == name
