"""Corpus layer: source canonicalization and de-duplication (plan §19, §20).

Every external document is normalized into a :class:`SourceRecord` with a
canonical identity. Exact and near-duplicate detection prevent a single press
release syndicated across five outlets from being counted as five independent
sources (§24's critical rule).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from kdrx.schemas.corpus import SourceRecord
from kdrx.state import hash_bytes

#: Query-string keys dropped during canonicalization (pure tracking noise).
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "gclsrc",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
    "source",
}

_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"']+", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def canonicalize_url(url: str) -> str:
    """Normalize a URL to its canonical form.

    - lowercase scheme + host;
    - drop a trailing slash on empty paths;
    - drop fragment;
    - drop known tracking parameters;
    - sort remaining query parameters;
    - drop default ports.
    """
    url = url.strip()
    if not url:
        return ""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    # drop default ports
    if port is not None and (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        port = None
    netloc = host
    if port is not None:
        netloc = f"{host}:{port}"
    if parts.username:
        netloc = f"{parts.username}@{netloc}"
    path = parts.path or "/"
    qs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(qs))
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_doi(doi: str) -> str | None:
    """Return a canonical, lowercased DOI without a ``doi:`` or URL prefix.

    Returns ``None`` if the input does not contain a well-formed DOI.
    """
    if not doi:
        return None
    m = _DOI_RE.search(doi)
    if not m:
        return None
    value = m.group(0).rstrip(".,;")
    return "doi:" + value.lower()


def canonical_identity(record: SourceRecord) -> str:
    """Stable identity key for a source (DOI if present, else canonical URL)."""
    if record.canonical_uri:
        doi = normalize_doi(record.canonical_uri)
        if doi:
            return doi
        url = canonicalize_url(record.canonical_uri)
        if url:
            return "url:" + url
    return "hash:" + (record.content_hash or "")


def source_fingerprint(record: SourceRecord) -> str:
    """Exact-duplicate key: content hash first, then canonical identity."""
    if record.content_hash:
        return "content:" + record.content_hash
    return canonical_identity(record)


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    return _WORD_RE.findall(text)


def tokenize(text: str) -> list[str]:
    """Public tokenizer used by both de-dup and BM25 retrieval."""
    return _tokens(text)


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity over word tokens, in [0, 1]."""
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def dedupe_exact(records: list[SourceRecord]) -> list[SourceRecord]:
    """Keep one record per exact fingerprint, preserving first-seen order."""
    seen: dict[str, SourceRecord] = {}
    for rec in records:
        key = source_fingerprint(rec)
        if key not in seen:
            seen[key] = rec
    return list(seen.values())


def dedupe_near(
    records: list[SourceRecord],
    *,
    threshold: float = 0.9,
    text_key: str = "title",
) -> list[SourceRecord]:
    """Drop near-duplicates by greedy clustering on title similarity.

    The first-seen record becomes the cluster representative. This is a cheap
    syndication detector: five copies of one press release share a title and
    collapse to a single family.
    """
    kept: list[SourceRecord] = []
    for rec in records:
        representative = True
        for existing in kept:
            a = getattr(rec, text_key, "") or ""
            b = getattr(existing, text_key, "") or ""
            if jaccard_similarity(a, b) >= threshold:
                representative = False
                break
        if representative:
            kept.append(rec)
    return kept


def content_hash_from_text(text: str) -> str:
    """Deterministic content hash (SHA-256 of normalized bytes)."""
    normalized = unicodedata.normalize("NFKC", text)
    return hash_bytes(normalized.encode("utf-8"))


def content_hash_from_file(path: str) -> str:
    from pathlib import Path

    return hash_bytes(Path(path).read_bytes())


def independence_families(records: list[SourceRecord]) -> dict[str, list[str]]:
    """Group sources into dependency families (plan §24).

    A family is the transitive closure of ``dependencies`` edges between
    records. Sources that declare they syndicate from another collapse into that
    source's family; independent records are their own singleton family.
    """
    by_id = {r.source_id: r for r in records}
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for r in records:
        find(r.source_id)
        for dep in r.dependencies:
            if dep in by_id:
                union(r.source_id, dep)

    families: dict[str, list[str]] = {}
    for r in records:
        families.setdefault(find(r.source_id), []).append(r.source_id)
    return families


def count_independent_sources(records: list[SourceRecord]) -> int:
    """Number of distinct dependency families (not raw source count)."""
    return len(independence_families(records))


def term_frequency_histogram(tokens: list[str]) -> Counter[str]:
    return Counter(tokens)
