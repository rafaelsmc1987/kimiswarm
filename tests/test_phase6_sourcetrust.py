"""FASE 6: source trust chain — resolver vivo, cache, policies, dimensões."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kdrx.retrieval import FileCorpus
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import GateVerdict, SourceType
from kdrx.verification import (
    DOIResolution,
    DOIResolver,
    LiveMetadata,
    MetadataCache,
    coi_check,
    currency_check,
    live_resolution_checks,
    parse_crossref_metadata,
    policy_for_record,
    record_doi,
    source_dimension_checks,
    source_trust_gate,
    version_check,
)

CSL_OK = {
    "DOI": "10.1000/xyz",
    "title": "Attention Is All You Need",
    "publisher": "NeurIPS",
    "issued": {"date-parts": [[2017]]},
    "URL": "https://papers.nips.cc/paper/7181",
}

CSL_RETRACTED = {
    "DOI": "10.1000/bad",
    "title": "RETRACTED: Miracle results",
    "publisher": "Venue",
    "issued": {"date-parts": [[2020]]},
}

CROSSREF_RETRACTION_UPDATE = {
    "message": {
        "DOI": "10.1000/upd",
        "title": "Some paper",
        "publisher": "Venue",
        "issued": {"date-parts": [[2019]]},
        "update-to": [{"type": "retraction", "DOI": "10.1000/notice"}],
    }
}


class FakeTransport:
    def __init__(self, responses: dict[str, str], fail: bool = False):
        self.responses = responses
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, url, headers=None):
        from kdrx.adapters import AdapterError

        self.calls.append(url)
        if self.fail:
            raise AdapterError("simulated API outage")
        for prefix, body in self.responses.items():
            if url.startswith(prefix):
                return body
        raise AdapterError(f"404 Not Found: {url}")


def make_record(**kw) -> SourceRecord:
    base = dict(
        source_id="s1",
        canonical_uri="https://doi.org/10.1000/xyz",
        title="Attention Is All You Need",
        source_type=SourceType.ACADEMIC_PAPER,
        content_hash="sha256:abc",
        date=datetime(2017, 6, 12, tzinfo=timezone.utc),
    )
    base.update(kw)
    return SourceRecord(**base)


# --------------------------------------------------------------------------- #
# T-06-01: resolver vivo
# --------------------------------------------------------------------------- #
def test_doi_resolver_live_success():
    import json as _json

    t = FakeTransport({"https://doi.org/": _json.dumps(CSL_OK)})
    res = DOIResolver(transport=t).resolve("10.1000/xyz")
    assert res.resolves is True
    assert res.metadata is not None
    assert res.metadata.title == "Attention Is All You Need"
    assert res.metadata.publisher == "NeurIPS"
    assert res.metadata.date and res.metadata.date.year == 2017
    assert res.from_cache is False


def test_fabricated_doi_detected():
    t = FakeTransport({})  # qualquer URL => 404
    res = DOIResolver(transport=t).resolve("10.9999/fabricated")
    assert res.resolves is False
    assert res.error is not None


def test_record_doi_extraction():
    assert record_doi(make_record()) == "10.1000/xyz"
    assert record_doi(make_record(canonical_uri="https://example.org/x")) is None
    assert (
        record_doi(make_record(metadata={"doi": "10.1/a"}, canonical_uri="http://x"))
        == "10.1/a"
    )


# --------------------------------------------------------------------------- #
# T-06-02: cache + outage
# --------------------------------------------------------------------------- #
def test_cache_short_circuits_http_when_fresh():
    import json as _json

    t = FakeTransport({"https://doi.org/": _json.dumps(CSL_OK)})
    resolver = DOIResolver(transport=t)
    resolver.resolve("10.1000/xyz")
    assert len(t.calls) == 1
    res = resolver.resolve("10.1000/xyz")  # cache hit — sem HTTP
    assert len(t.calls) == 1
    assert res.from_cache is True and res.cache_stale is False


def test_stale_cache_answers_during_outage():
    import json as _json

    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t = FakeTransport({"https://doi.org/": _json.dumps(CSL_OK)})
    cache = MetadataCache(ttl_days=30)
    resolver = DOIResolver(transport=t, cache=cache, now=lambda: t0)
    resolver.resolve("10.1000/xyz")

    # 45 dias depois: entrada STALE + API fora do ar => fallback explícito
    t.fail = True
    t_later = t0 + timedelta(days=45)
    resolver2 = DOIResolver(transport=t, cache=cache, now=lambda: t_later)
    res = resolver2.resolve("10.1000/xyz")
    assert res.resolves is True
    assert res.from_cache is True and res.cache_stale is True
    assert res.error is not None and "outage" in res.error
    assert len(t.calls) == 2  # tentou refrescar antes de cair no cache


def test_outage_without_cache_fails_resolution():
    t = FakeTransport({}, fail=True)
    res = DOIResolver(transport=t, cache=MetadataCache()).resolve("10.1000/xyz")
    assert res.resolves is False
    assert res.metadata is None


# --------------------------------------------------------------------------- #
# T-06-03: retraction / version / date
# --------------------------------------------------------------------------- #
def test_crossref_update_to_marks_retraction():
    meta = parse_crossref_metadata(CROSSREF_RETRACTION_UPDATE)
    assert meta.is_retracted is True
    assert meta.registry == "crossref"


def test_live_retraction_blocks():
    import json as _json

    t = FakeTransport({"https://doi.org/": _json.dumps(CSL_RETRACTED)})
    res = DOIResolver(transport=t).resolve("10.1000/bad")
    checks = live_resolution_checks(make_record(title="Miracle results"), res)
    retract = [c for c in checks if c.check_id == "RETRACTION_LIVE"][0]
    assert retract.passed is False
    assert retract.severity == "blocking"


def test_version_check_flags_content_change():
    rec = make_record(metadata={"previous_content_hash": "sha256:OLD"})
    assert version_check(rec).passed is False
    rec2 = make_record(metadata={"previous_content_hash": "sha256:abc"})
    assert version_check(rec2).passed is True


def test_date_consistency_check():
    meta = LiveMetadata(
        registry="crossref", date=datetime(2018, 1, 1, tzinfo=timezone.utc)
    )
    from kdrx.verification import date_consistency_check

    assert date_consistency_check(make_record(), meta).passed is False
    meta2 = LiveMetadata(
        registry="crossref", date=datetime(2017, 5, 1, tzinfo=timezone.utc)
    )
    assert date_consistency_check(make_record(), meta2).passed is True


# --------------------------------------------------------------------------- #
# T-06-04: policy registry por domínio
# --------------------------------------------------------------------------- #
def test_policy_registry_longest_suffix_match():
    arxiv = make_record(canonical_uri="https://export.arxiv.org/abs/1706.03762")
    assert policy_for_record(arxiv).domain == "arxiv.org"
    doi = make_record(canonical_uri="https://doi.org/10.1/x")
    assert policy_for_record(doi).require_live_resolution is True
    unknown = make_record(canonical_uri="https://randoblog.example.com/post")
    assert policy_for_record(unknown).domain == "*"


def test_domain_policy_drives_currency_window():
    old_date = datetime.now(timezone.utc) - timedelta(days=900)
    rec_arxiv = make_record(
        canonical_uri="https://arxiv.org/abs/1706.03762", date=old_date
    )
    rec_blog = make_record(
        canonical_uri="https://randoblog.example.com/post", date=old_date
    )
    # 900d: dentro da janela arxiv (3650d), fora da default (730d)
    assert currency_check(rec_arxiv, policy_for_record(rec_arxiv).max_age_days).passed
    assert not currency_check(rec_blog, policy_for_record(rec_blog).max_age_days).passed
    # e o gate aplica a policy por domínio sozinho
    gate = source_trust_gate(rec_arxiv)
    check = [c for c in gate.checks if c.check_id == "CURRENCY"][0]
    assert check.passed is True
    assert "3650" in check.description or check.details["max_age_days"] == 3650


# --------------------------------------------------------------------------- #
# T-06-05: dimensões separadas com consistência metadata <-> campo tipado
# --------------------------------------------------------------------------- #
def test_dimension_checks_pass_for_consistent_record():
    rec = make_record(metadata={"primary_or_secondary": "secondary"})
    checks = {c.check_id: c for c in source_dimension_checks(rec)}
    # metadata bate com o default tipado (UNKNOWN)? não => mismatch
    assert checks["PRIMARYNESS"].passed is False

    rec2 = make_record(
        primary_or_secondary="primary",  # type: ignore[arg-type]
        metadata={"primary_or_secondary": "primary", "directness": "direct"},
    )
    checks2 = {c.check_id: c for c in source_dimension_checks(rec2)}
    assert checks2["PRIMARYNESS"].passed is True
    assert checks2["DIRECTNESS"].passed is True
    assert checks2["INDEPENDENCE"].passed is True


def test_dimension_checks_fail_on_metadata_mismatch():
    rec = make_record(
        dependencies=["canonical:x"],
        metadata={"directness": "direct", "independence": "independent"},
    )
    checks = {c.check_id: c for c in source_dimension_checks(rec)}
    assert checks["DIRECTNESS"].passed is False  # dependencies => indirect
    assert checks["INDEPENDENCE"].passed is False


def test_coi_metadata_mismatch_fails():
    rec = make_record(metadata={"conflicts_of_interest": ["sponsor-x"]})
    assert coi_check(rec).passed is False  # typed [] != metadata ["sponsor-x"]
    assert coi_check(make_record()).passed is True


# --------------------------------------------------------------------------- #
# T-06-06: currency no gate + content hash + markdown type
# --------------------------------------------------------------------------- #
def test_gate_includes_currency_check():
    gate = source_trust_gate(make_record())
    assert any(c.check_id == "CURRENCY" for c in gate.checks)


def test_file_corpus_populates_identity_and_markdown_type(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "notes.md").write_text("# notes\nsome content here\n")
    docs = FileCorpus(corpus).scan()
    assert len(docs) == 1
    src = docs[0].source
    assert src.source_type is not SourceType.UNKNOWN
    assert src.content_hash and src.content_hash.startswith("sha256:")
    assert src.date is not None


# --------------------------------------------------------------------------- #
# T-06-07: critical fail BLOQUEIA
# --------------------------------------------------------------------------- #
def test_fabricated_doi_fails_gate():
    res = DOIResolution(doi="10.9999/fake", resolves=False, error="404")
    gate = source_trust_gate(make_record(), resolution=res)
    assert gate.verdict == GateVerdict.FAIL
    assert any("DOI_RESOLVES" in r for r in gate.blocking_reasons)


def test_doi_misdirection_is_critical_and_blocks():
    meta = LiveMetadata(
        registry="doi.org", title="A Completely Different Paper", date=None
    )
    res = DOIResolution(doi="10.1000/xyz", resolves=True, metadata=meta)
    gate = source_trust_gate(make_record(), resolution=res)
    assert gate.verdict == GateVerdict.FAIL
    match = [c for c in gate.checks if c.check_id == "DOI_TARGET_MATCHES"][0]
    assert match.passed is False
    assert match.details["critical"] is True
    assert match.severity == "blocking"


def test_pipeline_blocks_on_doi_misdirection(tmp_path):
    """Resolver injetado no executor: DOI misrouted => RuntimeError na wave."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("Accuracy 88% on benchmark x with numbers 42.\n")

    from kdrx.runner import (
        _FileResearchExecutor,
        build_contract,
        build_plan,
        prepare_run_dir,
    )

    contract = build_contract("accuracy")
    plan = build_plan(contract, 1)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")

    class _MisroutedResolver:
        def resolve(self, doi):
            return DOIResolution(
                doi=doi,
                resolves=True,
                metadata=LiveMetadata(registry="doi.org", title="Wrong Paper Entirely"),
            )

    executor = _FileResearchExecutor(
        FileCorpus(corpus), state, "accuracy", doi_resolver=_MisroutedResolver()
    )
    # fonte do corpus ganha DOI para ativar os checks vivos
    executor.sources = [make_record(source_id="file:a.md", title="a.md")]
    from kdrx.scheduler import AgentBrief

    brief = AgentBrief(
        brief_id="BR-T-VERIFY",
        task_id="T-VERIFY",
        role="source_verifier",  # type: ignore[arg-type]
        mission="verify sources",
        outputs=[],
    )
    with pytest.raises(RuntimeError, match="source trust gate FAILED"):
        executor._verify(brief)
