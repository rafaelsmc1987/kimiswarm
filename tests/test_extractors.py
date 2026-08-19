"""T-05-05: extractors por formato — texto real ou falha declarada, nunca falso."""

from __future__ import annotations

import importlib.util

import pytest

from kdrx.extractors import ExtractionError, extract_text
from kdrx.retrieval import FileCorpus


def test_markdown_extractor_strips_syntax(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(
        "# Título\n**Resultado**: accuracy de 90%.\n"
        "[link texto](https://x.org) e ```\ncode block\n```\n",
    )
    text, kind = extract_text(p)
    assert kind == "markdown"
    assert "#" not in text and "**" not in text
    assert "Resultado" in text and "accuracy de 90%" in text
    assert "link texto" in text and "https://x.org" not in text
    assert "code block" not in text  # fence removido (não é prosa citável)


def test_html_extractor_strips_tags_and_script(tmp_path):
    p = tmp_path / "doc.html"
    p.write_text(
        "<html><head><title>Hidden</title></head><body>"
        "<p>Visible <b>accuracy</b> 85%.</p>"
        "<script>alert('no')</script>"
        "</body></html>",
    )
    text, kind = extract_text(p)
    assert kind == "html"
    assert "Visible" in text and "accuracy" in text
    assert "alert" not in text and "<p>" not in text and "Hidden" not in text


def test_code_passthrough_preserves_content(tmp_path):
    p = tmp_path / "snippet.py"
    code = "def f(x):\n    return x * 2  # latency helper\n"
    p.write_text(code)
    text, kind = extract_text(p)
    assert kind == "code"
    assert text == code  # passthrough exato


def test_pdf_extractor_fails_explicitly_without_pypdf(tmp_path):
    p = tmp_path / "paper.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    if importlib.util.find_spec("pypdf") is None:
        with pytest.raises(ExtractionError, match="pypdf"):
            extract_text(p)
    else:  # dependência presente → extrai texto real ou falha declarada
        try:
            text, kind = extract_text(p)
            assert kind == "pdf" and isinstance(text, str)
        except ExtractionError as exc:  # PDF inválido: falha DECLARADA também
            assert "PDF parse falhou" in str(exc)


def test_scan_records_extraction_failures(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ok.md").write_text("Some accuracy content here.\n")
    (corpus / "bad.pdf").write_bytes(b"%PDF-1.4 fake")
    fc = FileCorpus(corpus)
    docs = fc.scan()
    names = {d.doc_id for d in docs}
    if importlib.util.find_spec("pypdf") is None:
        assert names == {"ok.md"}  # PDF não vira fonte fantasma
        assert len(fc.extraction_failures) == 1
        assert fc.extraction_failures[0]["file"] == "bad.pdf"
        assert "pypdf" in fc.extraction_failures[0]["reason"]
    else:
        assert "ok.md" in names


def test_scan_uses_format_extractors(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("# Heading\nText accuracy 90%.\n")
    (corpus / "b.html").write_text("<p>Latency 5 ms <i>reported</i>.</p>")
    (corpus / "c.py").write_text("x = 42  # energy constant\n")
    fc = FileCorpus(corpus)
    docs = {d.doc_id: d for d in fc.scan()}
    assert set(docs) == {"a.md", "b.html", "c.py"}
    assert docs["a.md"].source.metadata["extractor"] == "markdown"
    assert docs["b.html"].source.metadata["extractor"] == "html"
    assert docs["c.py"].source.metadata["extractor"] == "code"
    assert all(d.source.extraction_status == "extracted" for d in docs.values())
    assert "# Heading" not in docs["a.md"].text
    assert "<i>" not in docs["b.html"].text
    assert docs["c.py"].text == "x = 42  # energy constant\n"
    assert fc.extraction_failures == []


def test_extract_unknown_extension_raises(tmp_path):
    p = tmp_path / "weird.xyz"
    p.write_text("hi")
    with pytest.raises(ExtractionError, match="não extraível"):
        extract_text(p)
