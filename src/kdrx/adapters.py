"""Production web adapters (T-05-01, plan §18.4): real sources for routes C/D.

Stdlib-only HTTP (``urllib``), egress-gated via ``security.egress_allowed``
and injectable transport for fully offline tests. Adapters implemented:

- ``WebFetchAdapter`` — fetch a URL, HTML strip via extractors, -> Document-like dict
- ``OpenAlexAdapter`` — scholarly works search (api.openalex.org)
- ``CrossrefAdapter`` — DOI metadata lookup (api.crossref.org)
- ``ArxivAdapter`` — Atom query (export.arxiv.org)
- ``GitHubAdapter`` — code/repo search (api.github.com; token opcional via env
  KDRX_GITHUB_TOKEN, nunca impresso/logado)

Sem silent fallback: erro de egress/HTTP/parse vira ``AdapterError`` explícito.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from kdrx.corpus import canonicalize_url
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import SourceType
from kdrx.security import egress_allowed


class AdapterError(Exception):
    """Falha explícita de adapter: egress negado, HTTP ou parse."""


Transport = Callable[[str, dict[str, str] | None], str]


class UrllibTransport:
    """Transporte HTTP real via stdlib (user-agent identificado, timeout)."""

    def __init__(self, timeout: float = 20.0, user_agent: str = "kdr-x/0.1") -> None:
        self.timeout = timeout
        self.user_agent = user_agent

    def __call__(self, url: str, headers: dict[str, str] | None = None) -> str:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", self.user_agent)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except urllib.error.URLError as exc:
            raise AdapterError(f"HTTP falhou para {url}: {exc}") from exc


def _host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


@dataclass
class BaseAdapter:
    """Base com egress gate obrigatório antes de qualquer request."""

    transport: Transport | None = None
    allowlist: set[str] | None = None
    denylist: set[str] | None = None

    def __post_init__(self) -> None:
        if self.transport is None:
            self.transport = UrllibTransport()

    def _gate(self, url: str) -> None:
        host = _host_of(url)
        if not egress_allowed(host, allowlist=self.allowlist, denylist=self.denylist):
            raise AdapterError(
                f"egress bloqueado pela policy para host {host!r} "
                f"(allowlist={sorted(self.allowlist) if self.allowlist else None})"
            )

    def _get(self, url: str, headers: dict[str, str] | None = None) -> str:
        self._gate(url)
        assert self.transport is not None
        return self.transport(url, headers)

    @staticmethod
    def _parse_date(value: str | None) -> datetime | None:
        if not value:
            return None
        value = value.strip().replace("Z", "+00:00")  # ISO Z é literal p/ strptime
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None


# --------------------------------------------------------------------------- #
# WebFetch: URL -> texto extraível + SourceRecord
# --------------------------------------------------------------------------- #
class WebFetchAdapter(BaseAdapter):
    """Fetch de página arbitrária; HTML é stripped com o extractor real."""

    def fetch(self, url: str) -> tuple[str, str, SourceRecord]:
        from kdrx.extractors import html_to_text

        text = self._get(url)
        extracted = html_to_text(text) if "<html" in text[:2000].lower() else text
        now = datetime.now().astimezone()
        canon = canonicalize_url(url) or url
        record = SourceRecord(
            source_id=f"web:{canon}",
            canonical_uri=url,
            title=canon.split("/")[-1] or canon,
            source_type=SourceType.NEWS,
            retrieved_at=now,
            access_path=url,
            metadata={"adapter": "webfetch"},
        )
        return canon, extracted, record


# --------------------------------------------------------------------------- #
# OpenAlex: works search
# --------------------------------------------------------------------------- #
class OpenAlexAdapter(BaseAdapter):
    API = "https://api.openalex.org/works"

    def search(self, query: str, per_page: int = 10) -> list[SourceRecord]:
        url = f"{self.API}?search={urllib.parse.quote(query)}&per-page={per_page}"
        payload = json.loads(self._get(url))
        out: list[SourceRecord] = []
        for item in payload.get("results", []):
            doi = (item.get("doi") or "").removeprefix("https://doi.org/")
            authors = [
                a.get("author", {}).get("display_name", "")
                for a in item.get("authorships", [])
            ]
            out.append(
                SourceRecord(
                    source_id=f"openalex:{item.get('id', '').rsplit('/', 1)[-1]}",
                    canonical_uri=item.get("doi") or item.get("id", ""),
                    title=item.get("title") or "untitled",
                    authors=[a for a in authors if a],
                    publisher=(item.get("primary_location") or {})
                    .get("source", {})
                    .get("display_name"),
                    date=self._parse_date(item.get("publication_date")),
                    source_type=SourceType.ACADEMIC_PAPER,
                    access_path=item.get("id"),
                    metadata={
                        "adapter": "openalex",
                        "cited_by_count": item.get("cited_by_count", 0),
                        "doi": doi,
                    },
                )
            )
        return out


# --------------------------------------------------------------------------- #
# Crossref: DOI metadata
# --------------------------------------------------------------------------- #
class CrossrefAdapter(BaseAdapter):
    API = "https://api.crossref.org/works"

    def lookup_doi(self, doi: str) -> SourceRecord:
        url = f"{self.API}/{urllib.parse.quote(doi)}"
        payload = json.loads(self._get(url))
        m = payload.get("message", {})
        authors = [
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in m.get("author", [])
        ]
        issued = m.get("issued", {}).get("date-parts", [[None]])[0]
        date = None
        if issued and issued[0]:
            date = datetime(issued[0], 1, 1)
        return SourceRecord(
            source_id=f"doi:{doi.lower()}",
            canonical_uri=f"https://doi.org/{doi}",
            title=(m.get("title") or ["untitled"])[0],
            authors=[a for a in authors if a],
            publisher=m.get("publisher"),
            date=date,
            source_type=SourceType.ACADEMIC_PAPER,
            metadata={"adapter": "crossref", "type": m.get("type")},
        )


# --------------------------------------------------------------------------- #
# arXiv: Atom search
# --------------------------------------------------------------------------- #
class ArxivAdapter(BaseAdapter):
    API = "https://export.arxiv.org/api/query"
    NS = {"a": "http://www.w3.org/2005/Atom"}

    def search(self, query: str, max_results: int = 10) -> list[SourceRecord]:
        url = (
            f"{self.API}?search_query=all:{urllib.parse.quote(query)}"
            f"&start=0&max_results={max_results}"
        )
        xml_text = self._get(url)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            raise AdapterError(f"arXiv Atom parse falhou: {exc}") from exc
        out: list[SourceRecord] = []
        for entry in root.findall("a:entry", self.NS):
            raw_id = entry.findtext("a:id", default="", namespaces=self.NS) or ""
            arxiv_id = raw_id.rsplit("/abs/", 1)[-1]
            title = re.sub(
                r"\s+", " ", entry.findtext("a:title", default="", namespaces=self.NS)
            ).strip()
            published = entry.findtext("a:published", default="", namespaces=self.NS)
            authors = [
                (a.findtext("a:name", default="", namespaces=self.NS) or "").strip()
                for a in entry.findall("a:author", self.NS)
            ]
            out.append(
                SourceRecord(
                    source_id=f"arxiv:{arxiv_id}",
                    canonical_uri=raw_id,
                    title=title or "untitled",
                    authors=[a for a in authors if a],
                    publisher="arXiv",
                    date=self._parse_date(published),
                    source_type=SourceType.ACADEMIC_PAPER,
                    metadata={"adapter": "arxiv", "preprint": True},
                )
            )
        return out


# --------------------------------------------------------------------------- #
# GitHub: code/repo search (token opcional via env, nunca logado)
# --------------------------------------------------------------------------- #
class GitHubAdapter(BaseAdapter):
    API = "https://api.github.com"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("KDRX_GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def search_repositories(self, query: str, per_page: int = 10) -> list[SourceRecord]:
        url = f"{self.API}/search/repositories?q={urllib.parse.quote(query)}&per_page={per_page}"
        payload = json.loads(self._get(url, self._headers()))
        out: list[SourceRecord] = []
        for item in payload.get("items", []):
            out.append(
                SourceRecord(
                    source_id=f"github:{item.get('full_name', '')}",
                    canonical_uri=item.get("html_url", ""),
                    title=item.get("full_name", "untitled"),
                    publisher="GitHub",
                    date=self._parse_date(item.get("pushed_at")),
                    source_type=SourceType.CODE_REPOSITORY,
                    metadata={
                        "adapter": "github",
                        "stars": item.get("stargazers_count", 0),
                        "default_branch": item.get("default_branch"),
                    },
                )
            )
        return out

    def fetch_file(self, owner_repo_path: str) -> tuple[str, SourceRecord]:
        """Fetch raw file via contents API (base64-decoded)."""
        import base64

        url = f"{self.API}/repos/{owner_repo_path}"
        payload = json.loads(self._get(url, self._headers()))
        if payload.get("encoding") != "base64":
            raise AdapterError(f"encoding inesperado: {payload.get('encoding')}")
        text = base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
        record = SourceRecord(
            source_id=f"github:{owner_repo_path}",
            canonical_uri=payload.get("html_url", url),
            title=payload.get("path", owner_repo_path),
            publisher="GitHub",
            source_type=SourceType.CODE_REPOSITORY,
            retrieved_at=datetime.now().astimezone(),
            metadata={"adapter": "github", "sha": payload.get("sha", "")},
        )
        return text, record
