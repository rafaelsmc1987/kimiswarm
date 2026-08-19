"""Hybrid retrieval primitives (plan §18).

This module provides the deterministic, dependency-free retrieval core: BM25
over a file corpus (powering routes R3/R4), a query graph that replaces the flat
"count searches" proxy with structured nodes, and the evidence-saturation
stopping criterion (§18.5). Network/scholarly adapters plug in through the same
``Corpus`` interface and are intentionally out-of-scope for the offline core.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from kdrx.corpus import tokenize
from kdrx.extractors import ExtractionError, extract_text
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import ExtractionStatus, QualityGrade, SourceType


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
# Rank fusion (T-05-03, plan §18.2): lexical + dense-proxy + source-specific
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FusionWeights:
    """Declarative channel weights — sempre somam 1.0 (auditável)."""

    bm25: float = 0.55
    dense: float = 0.35
    source: float = 0.10


RRF_K = 60  # constante canônica do Reciprocal Rank Fusion

#: Piso de relevância do canal dense (T-05-03, calibrado na FASE 7): o ngram
#: cosine compartilha ruído de caracteres com qualquer doc (~0.08); um typo
#: real no termo de query produz ~0.5. Abaixo do piso, dense = ruído.
DENSE_RELEVANCE_FLOOR = 0.2

# Prior de qualidade por grade (channel source-specific, plan §20)
SOURCE_QUALITY_SCORE: dict[QualityGrade, float] = {
    QualityGrade.EXCELLENT: 1.0,
    QualityGrade.GOOD: 0.85,
    QualityGrade.ADEQUATE: 0.7,
    QualityGrade.WEAK: 0.4,
    QualityGrade.UNVERIFIED: 0.25,
    QualityGrade.REJECTED: 0.0,
}


def _char_ngrams(text: str, n: int = 3) -> Counter[str]:
    """Character n-grams do texto normalizado (proxy determinístico denso).

    Honestidade de implementação: isso NÃO é um embedding neural. É um canal
    semântico substituto que captura similaridade de superfície tolerante a
    typos/sufixos (nenhum modelo, nenhuma rede). Um scorer neural real entra
    pela mesma interface (``dense_scorer`` de ``fused_search``).
    """
    toks = tokenize(text)
    grams: Counter[str] = Counter()
    for tok in toks:
        padded = f"^{tok}$"
        for i in range(len(padded) - n + 1):
            grams[padded[i : i + n]] += 1
    return grams


def ngram_cosine(a: str, b: str) -> float:
    """Cosseno entre os vetores de char-ngrams de dois textos, em [0, 1]."""
    ga, gb = _char_ngrams(a), _char_ngrams(b)
    if not ga or not gb:
        return 0.0
    dot = sum(ga[g] * gb[g] for g in ga.keys() & gb.keys())
    norm_a = math.sqrt(sum(v * v for v in ga.values()))
    norm_b = math.sqrt(sum(v * v for v in gb.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# --------------------------------------------------------------------------- #
# File corpus (routes R3 / R4)
# --------------------------------------------------------------------------- #
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".py",
    ".html",
    ".htm",
    ".pdf",
    ".log",
}


class FileCorpus:
    """A read-only file corpus that backs BM25 retrieval (R3 file-only, R4 file-augmented)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._docs: list[Document] = []
        self._bm25 = BM25()
        # token->char-offset map por doc (T-05-04), cache na 1a extração de span
        self._token_map: dict[str, list[tuple[str, int, int]]] = {}
        # T-05-05: falhas de extração surfacadas — nunca silenciosas
        self.extraction_failures: list[dict[str, str]] = []

    def scan(self, *, extensions: set[str] | None = None) -> list[Document]:
        exts = extensions or TEXT_EXTENSIONS
        docs: list[Document] = []
        self.extraction_failures = []
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in exts:
                continue
            rel = str(path.relative_to(self.root))
            # T-05-05: extração por formato (extractors dedicados). Falha
            # explícita (ExtractionError) é REGISTRADA e o doc é pulado —
            # documento não-extraível não vira "fonte fantasma" no índice.
            try:
                text, extractor_name = extract_text(path)
            except ExtractionError as exc:
                self.extraction_failures.append({"file": rel, "reason": str(exc)})
                continue
            # Identidade mínima verificável (B-06/T-04-07): a existência da
            # fonte é blocking — fonte sem URI/título/hash NÃO passa no gate.
            # O hash cobre o TEXTO EXTRAÍDO (conteúdo canônico indexado), não
            # necessariamente os bytes do arquivo (ex.: markdown normalizado).
            doc = Document(
                doc_id=rel,
                text=text,
                source=SourceRecord(
                    source_id=f"file:{rel}",
                    canonical_uri=f"file://{path.resolve()}",
                    title=rel,
                    source_type=(
                        SourceType.CODE_REPOSITORY
                        if path.suffix.lower() in {".py", ".json", ".yaml", ".yml"}
                        else SourceType.DATASET
                    ),
                    content_hash=f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}",
                    date=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
                    extraction_status=ExtractionStatus.EXTRACTED,
                    metadata={"extractor": extractor_name},
                ),
            )
            docs.append(doc)
        self._docs = docs
        self._bm25.fit(docs)
        return docs

    def search(self, query: str, top_k: int = 10) -> list[tuple[Document, float]]:
        return self._bm25.search(query, top_k)

    def fused_search(
        self,
        query: str,
        top_k: int = 10,
        weights: FusionWeights | None = None,
        dense_scorer: "Callable[[str, Document], float] | None" = None,
    ) -> list[tuple[Document, float, dict[str, float]]]:
        """T-05-03: Reciprocal Rank Fusion (RRF) de 3 canais declarados.

        Canais e pesos ficam explícitos (``FusionWeights``): ``bm25`` (lexical),
        ``dense`` (proxy char-ngram determinístico ou scorer neural injetado)
        e ``source`` (prior de qualidade da fonte, plan §20). Retorna
        ``(doc, score_fundido, breakdown)`` ordenado; o breakdown carrega o
        score cru de cada canal para auditoria.
        """
        w = weights or FusionWeights()
        docs = list(self._docs)
        if not docs:
            return []

        def _ranked(values: list[float]) -> dict[str, int]:
            """Ranks com empate compartilhado (standard competition ranking).

            Scores iguais recebem o MESMO rank — sem desempate alfabético —
            para que um canal empatado não decida o resultado (caso típico:
            dois docs com bm25=0 não devem prevalecer sobre um sinal dense
            positivo no canal que discrimina).
            """
            order = sorted(range(len(docs)), key=lambda i: (-values[i], docs[i].doc_id))
            ranks: dict[str, int] = {}
            last_val: float | None = None
            last_rank = 0
            for pos, i in enumerate(order):
                v = values[i]
                if last_val is None or v != last_val:
                    last_rank = pos + 1
                    last_val = v
                ranks[docs[i].doc_id] = last_rank
            return ranks

        dense_fn = dense_scorer or (lambda q, d: ngram_cosine(q, d.text))
        bm25_raw = [self._bm25.score(query, d) for d in docs]
        dense_raw = [float(dense_fn(query, d)) for d in docs]
        source_raw = [
            SOURCE_QUALITY_SCORE.get(d.source.quality_grade, 0.25) if d.source else 0.25
            for d in docs
        ]

        rank_bm25 = _ranked(bm25_raw)
        rank_dense = _ranked(dense_raw)
        rank_source = _ranked(source_raw)

        out: list[tuple[Document, float, dict[str, float]]] = []
        for d, b25, dse, src in zip(docs, bm25_raw, dense_raw, source_raw):
            fused = (
                w.bm25 / (RRF_K + rank_bm25[d.doc_id])
                + w.dense / (RRF_K + rank_dense[d.doc_id])
                + w.source / (RRF_K + rank_source[d.doc_id])
            )
            out.append(
                (
                    d,
                    fused,
                    {
                        "bm25": round(b25, 6),
                        "dense": round(dse, 6),
                        "source": src,
                        "rank_bm25": rank_bm25[d.doc_id],
                        "rank_dense": rank_dense[d.doc_id],
                        "rank_source": rank_source[d.doc_id],
                    },
                )
            )
        out.sort(key=lambda item: (-item[1], item[0].doc_id))
        return out[:top_k]

    def retrieve_evidence_spans(
        self,
        query: str,
        top_k: int = 3,
        window: int = 60,
        *,
        fused: bool = True,
        weights: FusionWeights | None = None,
    ) -> list[dict]:
        """Return VERBATIM, char-locatable spans (window of tokens).

        T-05-04: o span devolvido é um slice literal do texto fonte (casing,
        pontuação e whitespace preservados) com ``char_start``/``char_end`` e
        números de linha — a citação é verificável contra o arquivo original.
        O interior da janela é escolhido no espaço de tokens normalizados
        (mesmo índice do BM25); os offsets vêm de ``token_spans``.

        T-05-03/T-05-07: a ORDEM de varredura vem do rank fusion (``fused``),
        então um doc com typo (sem match lexical exato) ainda produz evidência
        quando o canal dense sinaliza similaridade. ``fused=False`` volta ao
        BM25 puro (comparação de benchmark).
        """
        from kdrx.corpus import token_spans

        spans: list[dict] = []
        q_terms = set(tokenize(query))
        if fused:
            ranked = [
                (d, fs, br)
                for d, fs, br in self.fused_search(query, top_k, weights)
                if br["bm25"] > 0 or br["dense"] >= DENSE_RELEVANCE_FLOOR
            ]
        else:
            ranked = [(d, s, None) for d, s in self.search(query, top_k) if s > 0]
        for doc, score, breakdown in ranked:
            tmap = self._token_map.setdefault(doc.doc_id, token_spans(doc.text))
            toks = [t[0] for t in tmap]
            # find the densest window of query terms
            best_start, best_hits = 0, 0
            for i in range(max(0, len(toks) - window + 1)):
                hits = sum(1 for t in toks[i : i + window] if t in q_terms)
                if hits > best_hits:
                    best_hits, best_start = hits, i
            window_idx = range(best_start, min(len(toks), best_start + window))
            if not window_idx:
                continue
            char_start = tmap[window_idx[0]][1]
            char_end = tmap[window_idx[-1]][2]
            verbatim = doc.text[char_start:char_end]
            line_start = doc.text.count("\n", 0, char_start) + 1
            line_end = line_start + verbatim.count("\n")

            base_score = breakdown["bm25"] if breakdown else score
            if fused and base_score <= 0 and (breakdown or {}).get("dense", 0) < DENSE_RELEVANCE_FLOOR:
                continue
            spans.append(
                {
                    "source_id": doc.source.source_id if doc.source else doc.doc_id,
                    "title": doc.source.title if doc.source else doc.doc_id,
                    "verbatim_span": verbatim,
                    "locator": {
                        "file": doc.doc_id,
                        "line_start": line_start,
                        "line_end": line_end,
                        "char_start": char_start,
                        "char_end": char_end,
                    },
                    "bm25_score": round(base_score, 4),
                    "fused_score": round(score, 6) if fused else None,
                    "channels": breakdown,
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


# --------------------------------------------------------------------------- #
# Saved queries + delta retrieval (monitoring, T-10-01)
# --------------------------------------------------------------------------- #
@dataclass
class SourceDelta:
    """Diferença entre dois snapshots de corpus de arquivos."""

    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def has_delta(self) -> bool:
        return bool(self.added or self.changed or self.removed)

    def as_dict(self) -> dict:
        return {
            "added": self.added,
            "changed": self.changed,
            "removed": self.removed,
            "has_delta": self.has_delta,
        }


def snapshot_corpus_hashes(
    corpus_dir: str | Path, *, extensions: set[str] | None = None
) -> dict[str, str]:
    """``{rel_path: sha256(texto extraído)}`` — mesmo conteúdo canônico do corpus.

    Hash sobre o TEXTO EXTRAÍDO (não o mtime): uma edição semântica dispara
    delta "changed"; um re-save idêntico não. Arquivos não-extraíveis são
    hasheados por bytes (ainda participam do delta).
    """
    root = Path(corpus_dir)
    exts = extensions or TEXT_EXTENSIONS
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in exts:
            continue
        rel = str(path.relative_to(root))
        try:
            text, _ = extract_text(path)
            payload = text.encode("utf-8")
        except ExtractionError:
            payload = path.read_bytes()
        out[rel] = hashlib.sha256(payload).hexdigest()
    return out


def delta_sources(previous: dict[str, str], current: dict[str, str]) -> SourceDelta:
    """Compara dois snapshots ``{path: hash}`` e classifica added/changed/removed."""
    delta = SourceDelta()
    for path in sorted(current):
        if path not in previous:
            delta.added.append(path)
        elif previous[path] != current[path]:
            delta.changed.append(path)
    for path in sorted(previous):
        if path not in current:
            delta.removed.append(path)
    return delta


@dataclass
class SavedQuery:
    """Query monitorada (standing query) — o delta-search roda sobre ela."""

    query: str
    corpus_dir: str
    saved_at: str

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "corpus_dir": self.corpus_dir,
            "saved_at": self.saved_at,
        }


class SavedQueryStore:
    """Persistência JSON simples de standing queries (T-10-01)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[SavedQuery]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [
            SavedQuery(
                query=q["query"], corpus_dir=q["corpus_dir"], saved_at=q["saved_at"]
            )
            for q in data.get("queries", [])
        ]

    def save(self, queries: list[SavedQuery]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"queries": [q.as_dict() for q in queries]}, indent=2) + "\n",
            encoding="utf-8",
        )

    def add(self, query: SavedQuery) -> None:
        queries = self.load()
        if not any(
            q.query == query.query and q.corpus_dir == query.corpus_dir for q in queries
        ):
            queries.append(query)
        self.save(queries)
