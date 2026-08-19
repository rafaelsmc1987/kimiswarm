"""T-05-01: web adapters reais — transporte injetável, egress gate, zero rede."""

from __future__ import annotations

import json

import pytest

from kdrx.adapters import (
    AdapterError,
    ArxivAdapter,
    CrossrefAdapter,
    GitHubAdapter,
    OpenAlexAdapter,
    WebFetchAdapter,
)


class FakeTransport:
    """Transporte fake: responde por prefixo de URL, registra chamadas."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    def __call__(self, url: str, headers: dict[str, str] | None = None) -> str:
        self.calls.append((url, headers))
        for prefix, body in self.responses.items():
            if url.startswith(prefix):
                return body
        raise AdapterError(f"no canned response for {url}")


OPENALEX_JSON = json.dumps(
    {
        "results": [
            {
                "id": "https://openalex.org/W123456",
                "doi": "https://doi.org/10.1000/abc",
                "title": "Attention Is All You Need",
                "publication_date": "2017-06-12",
                "authorships": [
                    {"author": {"display_name": "Ashish Vaswani"}},
                    {"author": {"display_name": "Noam Shazeer"}},
                ],
                "primary_location": {"source": {"display_name": "NeurIPS"}},
                "cited_by_count": 99999,
            }
        ]
    }
)

CROSSREF_JSON = json.dumps(
    {
        "message": {
            "title": ["Deep Residual Learning"],
            "author": [{"given": "Kaiming", "family": "He"}],
            "publisher": "IEEE",
            "issued": {"date-parts": [[2016]]},
            "type": "proceedings-article",
        }
    }
)

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is   All You Need</title>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
  </entry>
</feed>
"""

GITHUB_JSON = json.dumps(
    {
        "items": [
            {
                "full_name": "pallets/flask",
                "html_url": "https://github.com/pallets/flask",
                "pushed_at": "2025-01-02T03:04:05Z",
                "stargazers_count": 70000,
                "default_branch": "main",
            }
        ]
    }
)


def test_openalex_search_parses_real_payload():
    t = FakeTransport({"https://api.openalex.org/works": OPENALEX_JSON})
    records = OpenAlexAdapter(transport=t).search("attention mechanism")
    assert len(records) == 1
    r = records[0]
    assert r.source_id == "openalex:W123456"
    assert r.title == "Attention Is All You Need"
    assert r.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert r.publisher == "NeurIPS"
    assert r.date is not None and r.date.year == 2017
    assert r.metadata["cited_by_count"] == 99999
    # URL real construída com query escapada
    assert "attention%20mechanism" in t.calls[0][0]


def test_crossref_lookup_parses_real_payload():
    t = FakeTransport({"https://api.crossref.org/works": CROSSREF_JSON})
    r = CrossrefAdapter(transport=t).lookup_doi("10.1109/CVPR.2016.90")
    assert r.source_id == "doi:10.1109/cvpr.2016.90"
    assert r.title == "Deep Residual Learning"
    assert r.authors == ["Kaiming He"]
    assert r.publisher == "IEEE"
    assert r.date is not None and r.date.year == 2016


def test_arxiv_search_parses_atom_feed():
    t = FakeTransport({"https://export.arxiv.org/api/query": ARXIV_XML})
    records = ArxivAdapter(transport=t).search("transformers")
    assert len(records) == 1
    r = records[0]
    assert r.source_id == "arxiv:1706.03762v7"
    assert r.title == "Attention Is All You Need"  # whitespace normalizado
    assert r.authors == ["Ashish Vaswani"]
    assert r.date is not None and r.date.year == 2017
    assert r.metadata["preprint"] is True


def test_github_search_parses_payload():
    t = FakeTransport({"https://api.github.com/search": GITHUB_JSON})
    records = GitHubAdapter(transport=t).search_repositories("flask")
    assert len(records) == 1
    r = records[0]
    assert r.source_id == "github:pallets/flask"
    assert r.metadata["stars"] == 70000
    # sem token no ambiente, nenhum Authorization header é enviado
    assert "Authorization" not in (t.calls[0][1] or {})


def test_webfetch_strips_html_like_extractor():
    html = "<html><head><title>X</title></head><body><p>Accuracy 88% real</p><script>evil()</script></body></html>"
    t = FakeTransport({"https://example.org/page": html})
    canon, text, record = WebFetchAdapter(transport=t).fetch(
        "https://example.org/page?utm_source=spam"
    )
    assert "Accuracy 88% real" in text
    assert "evil" not in text and "<p>" not in text
    assert record.source_type == "news"
    # tracking param removido na identidade canônica
    assert "utm_source" not in canon


def test_egress_denied_raises_before_any_request():
    t = FakeTransport({})
    adapter = CrossrefAdapter(transport=t, allowlist={"api.openalex.org"})
    with pytest.raises(AdapterError, match="egress bloqueado"):
        adapter.lookup_doi("10.1000/xyz")
    assert t.calls == [], "egress gate deve disparar ANTES do transporte"


def test_transport_error_surfaces_as_adapter_error():
    class _Failing:
        def __call__(self, url, headers=None):
            raise AdapterError("HTTP falhou para x: boom")

    with pytest.raises(AdapterError, match="HTTP falhou"):
        OpenAlexAdapter(transport=_Failing()).search("q")
