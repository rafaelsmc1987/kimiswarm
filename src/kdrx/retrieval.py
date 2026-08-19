"""Hybrid retrieval primitives (plan §18).

This module provides the deterministic, dependency-free retrieval core: BM25
over a file corpus (powering routes R3/R4), a query graph that replaces the flat
"count searches" proxy with structured nodes, and the evidence-saturation
stopping criterion (§18.5). Network/scholarly adapters plug in through the same
``Corpus`` interface and are intentionally out-of-scope for the offline core.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from kdrx.corpus import tokenize
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import SourceType


# --------------------------------------------------------------------------- #
# BM25
# --------------------------------------------------------------------------- #
@dataclass
class Document:
    doc_id: str
    text: str
    tokens: list[str] = field(default_factory=list)
    source: SourceRecord | None = None

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = tokenize(self.text)


class BM25:
    """Okapi BM25 ranker over an in-memory document corpus."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[Document] = []
        self._doc_freq: Counter[str] = Counter()
        self._doc_len: list[int] = []
        self._avgdl: float = 0.0

    def fit(self, docs: Iterable[Document]) -> "BM25":
        self._docs = list(docs)
        self._doc_freq = Counter()
        self._doc_len = []
        for d in self._docs:
            for term in set(d.tokens):
                self._doc_freq[term] += 1
            self._doc_len.append(len(d.tokens))
        total = sum(self._doc_len)
        self._avgdl = total / len(self._docs) if self._docs else 0.0
        return self

    def _idf(self, term: str) -> float:
        df = self._doc_freq.get(term, 0)
        n = len(self._docs)
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def score(self, query: str, doc: Document) -> float:
        if self._avgdl == 0:
            return 0.0
        q_terms = tokenize(query)
        score = 0.0
        tf = Counter(doc.tokens)
        for term in set(q_terms):
            if term not in tf:
                continue
            idf = self._idf(term)
            f = tf[term]
            denom = f + self.k1 * (1 - self.b + self.b * len(doc.tokens) / self._avgdl)
            score += idf * (f * (self.k1 + 1)) / denom
        return score

    def search(self, query: str, top_k: int = 10) -> list[tuple[Document, float]]:
        scored = [(d, self.score(query, d)) for d in self._docs]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    def top_docs(self, query: str, top_k: int = 10) -> list[Document]:
        return [d for d, _ in self.search(query, top_k)]


# --------------------------------------------------------------------------- #
# File corpus (routes R3 / R4)
# --------------------------------------------------------------------------- #
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".rst",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".log",
}


class FileCorpus:
    """A read-only file corpus that backs BM25 retrieval (R3 file-only, R4 file-augmented)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._docs: list[Document] = []
        self._bm25 = BM25()

    def scan(self, *, extensions: set[str] | None = None) -> list[Document]:
        exts = extensions or TEXT_EXTENSIONS
        docs: list[Document] = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in exts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:  # pragma: no cover - unreadable file
                continue
            rel = str(path.relative_to(self.root))
            is_code = path.suffix.lower() in {".py", ".json", ".yaml", ".yml"}
            # Identidade mínima verificável (B-06/T-04-07): a existência da
            # fonte é blocking — fonte sem URI/título/hash NÃO passa no gate.
            # O corpus local se identifica como dataset de arquivo com hash e
            # data de mtime (evidência de frescor) — nada é fakeado: são
            # atributos reais do arquivo apontado pelo canonical_uri.
            doc = Document(
                doc_id=rel,
                text=text,
                source=SourceRecord(
                    source_id=f"file:{rel}",
                    canonical_uri=f"file://{path.resolve()}",
                    title=rel,
                    source_type=SourceType.CODE_REPOSITORY if is_code else SourceType.DATASET,
                    content_hash=f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}",
                    date=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
                ),
            )
            docs.append(doc)
        self._docs = docs
        self._bm25.fit(docs)
        return docs

    def search(self, query: str, top_k: int = 10) -> list[tuple[Document, float]]:
        return self._bm25.search(query, top_k)

    def retrieve_evidence_spans(
        self, query: str, top_k: int = 3, window: int = 60
    ) -> list[dict]:
        """Return locatable spans (window of tokens around the best match).

        This is the deterministic analogue of evidence-span extraction for
        file corpora: it returns verbatim text plus a rough line locator so the
        R3 route can cite ``page/line`` spans without a model.
        """
        spans: list[dict] = []
        q_terms = set(tokenize(query))
        for doc, score in self.search(query, top_k):
            if score <= 0:
                continue
            toks = doc.tokens
            # find the densest window of query terms
            best_start, best_hits = 0, 0
            for i in range(max(0, len(toks) - window + 1)):
                hits = sum(1 for t in toks[i : i + window] if t in q_terms)
                if hits > best_hits:
                    best_hits, best_start = hits, i
            span_tokens = toks[best_start : best_start + window]
            spans.append(
                {
                    "source_id": doc.source.source_id if doc.source else doc.doc_id,
                    "title": doc.source.title if doc.source else doc.doc_id,
                    "verbatim_span": " ".join(span_tokens),
                    "locator": {"file": doc.doc_id, "line_start": None},
                    "bm25_score": round(score, 4),
                    "query_term_hits": best_hits,
                }
            )
        return spans


# --------------------------------------------------------------------------- #
# Query graph
# --------------------------------------------------------------------------- #
@dataclass
class QueryNode:
    query: str
    rationale: str = ""
    expected_evidence: str = ""
    source_class: str = "general_web"
    language: str = "en"
    time_window: str = ""
    parent: str | None = None
    results: list[str] = field(default_factory=list)
    marginal_gain: float = 0.0
    node_id: str = ""

    def __post_init__(self) -> None:
        if not self.node_id:
            self.node_id = "Q-" + self.query[:24]


class QueryGraph:
    """A structured query graph instead of a flat query list (plan §18.1).

    Each node records query, rationale, expected evidence, source class,
    language and time window; ``marginal_gain`` is updated as new sources are
    attributed, so the stopping criterion can reason about diminishing returns.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, QueryNode] = {}

    def add(self, node: QueryNode) -> QueryNode:
        if node.node_id in self.nodes:
            raise ValueError(f"duplicate query node {node.node_id}")
        self.nodes[node.node_id] = node
        return node

    def child_of(self, parent_id: str, **kwargs: object) -> QueryNode:
        node = QueryNode(parent=parent_id, **kwargs)
        return self.add(node)

    def record_results(self, node_id: str, result_ids: list[str]) -> None:
        self.nodes[node_id].results = result_ids

    def __iter__(self):
        return iter(self.nodes.values())

    def __len__(self) -> int:
        return len(self.nodes)


# --------------------------------------------------------------------------- #
# Stopping criterion (plan §18.5)
# --------------------------------------------------------------------------- #
@dataclass
class SaturationState:
    critical_claim_coverage: float = 0.0
    marginal_source_gain: float = 0.0
    marginal_evidence_gain: float = 0.0
    unresolved_blockers: int = 0
    diversity_sources: int = 0
    queries_issued: int = 0


class StoppingCriterion:
    """Decide whether retrieval has saturated (replaces fixed search budgets)."""

    def __init__(
        self,
        *,
        claim_coverage_threshold: float = 0.9,
        source_gain_threshold: float = 0.05,
        evidence_gain_threshold: float = 0.05,
        diversity_floor: int = 3,
        max_queries: int = 250,
    ) -> None:
        self.claim_coverage_threshold = claim_coverage_threshold
        self.source_gain_threshold = source_gain_threshold
        self.evidence_gain_threshold = evidence_gain_threshold
        self.diversity_floor = diversity_floor
        self.max_queries = max_queries

    def evaluate(self, state: SaturationState) -> dict:
        """Return a decision dict with ``stop``, ``reason`` and unmet criteria."""
        budget_hit = state.queries_issued >= self.max_queries
        saturated = (
            state.critical_claim_coverage >= self.claim_coverage_threshold
            and state.marginal_source_gain < self.source_gain_threshold
            and state.marginal_evidence_gain < self.evidence_gain_threshold
            and state.unresolved_blockers == 0
            and state.diversity_sources >= self.diversity_floor
        )
        unmet = []
        if state.critical_claim_coverage < self.claim_coverage_threshold:
            unmet.append("claim_coverage")
        if state.marginal_source_gain >= self.source_gain_threshold:
            unmet.append("source_gain")
        if state.marginal_evidence_gain >= self.evidence_gain_threshold:
            unmet.append("evidence_gain")
        if state.unresolved_blockers > 0:
            unmet.append("unresolved_blockers")
        if state.diversity_sources < self.diversity_floor:
            unmet.append("diversity")
        if saturated:
            reason = "saturated"
        elif budget_hit:
            reason = "budget_ceiling"
        else:
            reason = "continue"
        return {"stop": saturated or budget_hit, "reason": reason, "unmet": unmet}
