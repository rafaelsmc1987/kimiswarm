"""FASE 5 — retrieval de produção (T-05-01..07).

T-05-04: EvidenceSpan com char offsets exatos — verbatim preservado.
"""

from __future__ import annotations

from kdrx.retrieval import FileCorpus


def _corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "findings.md").write_text(
        "The New Model improves Accuracy by 12.5% on three datasets.\n"
        "Latency: 5 ms (p99) under load!\n"
        "Second paragraph, with Mixed-CASE Tokens;\n",
        encoding="utf-8",
    )
    (corpus / "method.md").write_text(
        "Training used 8 GPUs.\nSee the appendix.\n", encoding="utf-8"
    )
    return corpus


def test_spans_are_verbatim_with_exact_char_offsets(tmp_path):
    corpus = FileCorpus(_corpus(tmp_path))
    docs = {d.doc_id: d for d in corpus.scan()}
    spans = corpus.retrieve_evidence_spans("accuracy latency", top_k=3, window=20)
    assert spans, "esperava spans"
    for sp in spans:
        doc = docs[sp["locator"]["file"]]
        cs = sp["locator"]["char_start"]
        ce = sp["locator"]["char_end"]
        # o texto citado é EXATAMENTE o slice do arquivo original
        assert sp["verbatim_span"] == doc.text[cs:ce]
        # e é substring do documento (não rejoin de tokens normalizados)
        assert sp["verbatim_span"] in doc.text
        # offsets coerentes
        assert 0 <= cs < ce <= len(doc.text)


def test_spans_preserve_casing_and_punctuation(tmp_path):
    corpus = FileCorpus(_corpus(tmp_path))
    corpus.scan()
    spans = corpus.retrieve_evidence_spans("accuracy", top_k=1, window=10)
    assert spans
    txt = spans[0]["verbatim_span"]
    # "Accuracy" com A maiúsculo e "12.5%" com pontuação preservados
    assert "Accuracy" in txt
    assert "12.5%" in txt


def test_spans_have_line_numbers(tmp_path):
    corpus = FileCorpus(_corpus(tmp_path))
    docs = {d.doc_id: d for d in corpus.scan()}
    spans = corpus.retrieve_evidence_spans("latency", top_k=1, window=12)
    assert spans
    loc = spans[0]["locator"]
    doc = docs[loc["file"]]
    lines = doc.text.splitlines()
    # conteúdo da linha reportada contém parte do span
    assert 1 <= loc["line_start"] <= loc["line_end"] <= len(lines)


# --------------------------------------------------------------------------- #
# T-05-03: rank fusion lexical + dense-proxy + source-specific (RRF)
# --------------------------------------------------------------------------- #
def test_fused_search_is_deterministic(tmp_path):
    corpus = FileCorpus(_corpus(tmp_path))
    corpus.scan()
    first = [(d.doc_id, round(s, 8)) for d, s, _ in corpus.fused_search("accuracy")]
    second = [(d.doc_id, round(s, 8)) for d, s, _ in corpus.fused_search("accuracy")]
    assert first == second


def test_fused_search_breakdown_reports_channels(tmp_path):
    corpus = FileCorpus(_corpus(tmp_path))
    corpus.scan()
    results = corpus.fused_search("accuracy latency", top_k=2)
    assert results
    for _doc, _score, br in results:
        assert set(br) == {
            "bm25",
            "dense",
            "source",
            "rank_bm25",
            "rank_dense",
            "rank_source",
        }


def test_zero_weights_reduce_to_bm25_order(tmp_path):
    from kdrx.retrieval import FusionWeights

    corpus = FileCorpus(_corpus(tmp_path))
    corpus.scan()
    fused = corpus.fused_search(
        "accuracy latency", weights=FusionWeights(bm25=1.0, dense=0.0, source=0.0)
    )
    bm25 = corpus.search("accuracy latency", top_k=len(fused))
    assert [d.doc_id for d, _, _ in fused] == [d.doc_id for d, _ in bm25]


def test_fusion_recalls_typo_doc_bm25_misses(tmp_path):
    """Benchmark: typo no doc zera o canal lexical; o canal dense (char-ngram)
    recupera — fusion > BM25 puro em recall@1 neste fixture."""
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "typo.md").write_text("Model accurcy improved a lot.\n")  # typo!
    (root / "other.md").write_text("Completely unrelated content here.\n")
    corpus = FileCorpus(root)
    corpus.scan()

    assert [d.doc_id for d, s in corpus.search("accuracy") if s > 0] == []
    top = corpus.fused_search("accuracy", top_k=1)
    assert top and top[0][0].doc_id == "typo.md"

    spans_bf25 = corpus.retrieve_evidence_spans("accuracy", fused=False)
    spans_fused = corpus.retrieve_evidence_spans("accuracy", fused=True)
    assert spans_bf25 == []
    assert spans_fused and spans_fused[0]["fused_score"] is not None
    assert "accurcy" in spans_fused[0]["verbatim_span"]


# --------------------------------------------------------------------------- #
# T-05-02 + T-05-07: QueryGraph dirigindo o pipeline + saturação de evidência
# --------------------------------------------------------------------------- #
def test_query_graph_drives_pipeline_and_persists(tmp_path):
    import json as _json

    from kdrx.runner import run_file_research

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("Accuracy improves by 12 percent here.\n")
    (corpus / "b.md").write_text("Latency is 5 ms under heavy load.\n")
    (corpus / "c.md").write_text("Energy draw is 40 watts at peak.\n")

    summary = run_file_research(
        corpus, "accuracy and latency and energy", tmp_path / "runs"
    )
    assert summary["exit_code"] == 0
    run_dir = tmp_path / "runs" / summary["run_id"]
    qg = _json.loads(
        (run_dir / "retrieval" / "query_graph.json").read_text(encoding="utf-8")
    )
    # o grafo dirigiu queries: seed + cláusulas derivadas
    assert len(qg["nodes"]) >= 2
    assert qg["nodes"][0]["node_id"] == "Q-seed"
    assert any(n["parent"] == "Q-seed" for n in qg["nodes"])
    for node in qg["nodes"]:
        assert "marginal_gain" in node
        assert isinstance(node["results"], list)
    # decisão de parada registrada com razão conhecida
    assert qg["decision"]["reason"] in {"saturated", "budget_ceiling", "continue"}
    # spans produzidos por MAIS de um nó (cláusulas têm hits próprios)
    hit_nodes = [n for n in qg["nodes"] if n["results"]]
    assert len(hit_nodes) >= 2


def test_saturation_stops_before_exhausting_nodes(tmp_path):
    """Se o seed já cobre todas as fontes e termos, cláusulas não trazem
    ganho marginal — o loop PARA antes de esgotar os nós do grafo."""
    import json as _json

    from kdrx.runner import run_file_research

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(4):
        (corpus / f"doc{i}.md").write_text(
            "Accuracy latency energy throughput all measured together "
            f"in document {i} with solid numbers like 42 percent.\n"
        )
    summary = run_file_research(
        corpus,
        "accuracy and latency and energy and throughput",
        tmp_path / "runs",
    )
    run_dir = tmp_path / "runs" / summary["run_id"]
    qg = _json.loads(
        (run_dir / "retrieval" / "query_graph.json").read_text(encoding="utf-8")
    )
    assert len(qg["nodes"]) >= 4  # seed + 4 cláusulas
    assert qg["decision"]["reason"] == "saturated"
    # parou cedo: menos queries do que nós disponíveis
    assert qg["queries_issued"] < len(qg["nodes"])


# --------------------------------------------------------------------------- #
# T-05-06: dedup/dependency collapse integrado ao pipeline
# --------------------------------------------------------------------------- #
def test_pipeline_collapses_duplicate_sources(tmp_path):
    """Cópias idênticas do mesmo texto colapsam para a fonte canônica:
    sources.jsonl só vê fontes reais, spans citam a canônica, claims não se
    duplicam — e o collapse fica registrado em corpus/dedup.json."""
    import json as _json

    from kdrx.runner import run_file_research

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    text_a = "Accuracy improves by 12 percent on the benchmark dataset.\n"
    (corpus / "a.md").write_text(text_a)
    (corpus / "copy.md").write_text(text_a)  # duplicata exata
    (corpus / "other.md").write_text("Latency is 5 ms under heavy load.\n")

    summary = run_file_research(corpus, "accuracy and latency", tmp_path / "runs")
    assert summary["exit_code"] == 0
    assert summary["sources"] == 2, "copy.md não pode inflar a contagem de fontes"

    run_dir = tmp_path / "runs" / summary["run_id"]
    dedup = _json.loads((run_dir / "corpus" / "dedup.json").read_text(encoding="utf-8"))
    assert dedup["scanned_documents"] == 3
    assert dedup["canonical_count"] == 2
    assert dedup["duplicates"] == {"file:copy.md": "file:a.md"}
    assert set(dedup["families"]) == {"file:a.md", "file:other.md"}

    spans = [
        _json.loads(x)
        for x in (run_dir / "evidence" / "spans.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    assert spans, "esperava spans"
    assert all(sp["source_id"] != "file:copy.md" for sp in spans)

    claims = [
        _json.loads(x)
        for x in (run_dir / "claims" / "claims.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x.strip()
    ]
    keys = [
        (c["statement"].strip().lower(), tuple(sorted(c["support_edges"])))
        for c in claims
    ]
    assert len(keys) == len(set(keys)), "claims gêmeos de cópias proibidos"
