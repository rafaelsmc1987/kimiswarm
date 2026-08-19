"""Run state, corpus canonicalization, and retrieval."""

from __future__ import annotations

from kdrx.corpus import (
    canonicalize_url,
    content_hash_from_text,
    count_independent_sources,
    dedupe_exact,
    normalize_doi,
)
from kdrx.retrieval import (
    BM25,
    Document,
    FileCorpus,
    QueryGraph,
    QueryNode,
    SaturationState,
    StoppingCriterion,
)
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import SourceType
from kdrx.schemas.plan import RunManifest
from kdrx.state import RunState, hash_file


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def test_scaffold_creates_canonical_tree(tmp_path):
    state = RunState(tmp_path, "run-1")
    manifest = RunManifest(
        run_id="run-1", plan_id="p", contract_id="c", route="R1", root_dir=""
    )
    run_dir = state.scaffold(manifest)
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "claims" / "claims.jsonl").exists()
    assert (run_dir / "delivery").exists()
    loaded = state.load_manifest()
    assert loaded.run_id == "run-1"


def test_events_append_only(tmp_path):
    state = RunState(tmp_path, "run-1")
    state.scaffold(
        RunManifest(
            run_id="run-1", plan_id="p", contract_id="c", route="R1", root_dir=""
        )
    )
    state.append_event({"kind": "a"})
    state.append_event({"kind": "b"})
    events = list(state.iter_events())
    assert [e["kind"] for e in events] == ["run_created", "a", "b"]


def test_snapshot_and_verify_hashes(tmp_path):
    state = RunState(tmp_path, "run-1")
    state.scaffold(
        RunManifest(
            run_id="run-1", plan_id="p", contract_id="c", route="R1", root_dir=""
        )
    )
    state.write_text("notes.txt", "hello")
    snapshot = state.snapshot_hashes()
    assert state.verify_hashes(snapshot) == []
    state.write_text("notes.txt", "changed")
    assert state.verify_hashes(snapshot) == ["notes.txt (changed)"]


def test_hash_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("abc")
    assert hash_file(p) == content_hash_from_text("abc")


# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #
def test_canonicalize_url_strips_tracking():
    out = canonicalize_url("https://Example.com/Path?utm_source=x&b=2&a=1#frag")
    assert out == "https://example.com/Path?a=1&b=2"


def test_normalize_doi():
    assert (
        normalize_doi("https://doi.org/10.1038/S41586-020-0000-X")
        == "doi:10.1038/s41586-020-0000-x"
    )
    assert normalize_doi("no doi here") is None


def test_dedupe_exact_by_content_hash():
    a = SourceRecord(
        source_id="a", canonical_uri="https://x", title="t", content_hash="h"
    )
    b = SourceRecord(
        source_id="b", canonical_uri="https://y", title="t", content_hash="h"
    )
    assert [s.source_id for s in dedupe_exact([a, b])] == ["a"]


def test_independence_families_collapse_syndication():
    base = SourceRecord(
        source_id="S0",
        canonical_uri="https://pr",
        title="PR",
        source_type=SourceType.PRESS_RELEASE,
    )
    c1 = SourceRecord(
        source_id="S1",
        canonical_uri="https://a",
        title="copy",
        source_type=SourceType.NEWS,
        dependencies=["S0"],
    )
    c2 = SourceRecord(
        source_id="S2",
        canonical_uri="https://b",
        title="copy",
        source_type=SourceType.NEWS,
        dependencies=["S0"],
    )
    ind = SourceRecord(
        source_id="S3",
        canonical_uri="https://c",
        title="ind",
        source_type=SourceType.ACADEMIC_PAPER,
    )
    assert count_independent_sources([base, c1, c2, ind]) == 2


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def test_bm25_ranks_relevant_doc_first():
    docs = [
        Document(doc_id="rel", text="machine learning improves accuracy on images"),
        Document(doc_id="irr", text="the weather is nice today and the sky is blue"),
    ]
    bm25 = BM25().fit(docs)
    top = bm25.top_docs("machine learning accuracy", top_k=1)
    assert top[0].doc_id == "rel"


def test_file_corpus_search(tmp_path):
    (tmp_path / "a.txt").write_text("neural networks and deep learning")
    (tmp_path / "b.txt").write_text("gardening tips for spring")
    fc = FileCorpus(tmp_path)
    fc.scan()
    hits = fc.search("deep learning", top_k=2)
    assert hits[0][0].doc_id == "a.txt"


def test_query_graph_parent_child():
    g = QueryGraph()
    g.add(QueryNode(query="what is X", node_id="Q0"))
    child = g.child_of("Q0", query="X primary sources")
    assert child.parent == "Q0"
    assert len(g) == 2


def test_stopping_criterion_saturates():
    crit = StoppingCriterion()
    saturated = SaturationState(
        critical_claim_coverage=0.95,
        marginal_source_gain=0.01,
        marginal_evidence_gain=0.01,
        unresolved_blockers=0,
        diversity_sources=4,
    )
    assert crit.evaluate(saturated)["reason"] == "saturated"


def test_stopping_criterion_budget_ceiling():
    crit = StoppingCriterion(max_queries=10)
    state = SaturationState(queries_issued=10)
    assert crit.evaluate(state)["reason"] == "budget_ceiling"
