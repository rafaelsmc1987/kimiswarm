"""Source trust, prompt-injection boundary, contradiction and falsification.

This module is the deterministic part of the epistemic core:

- source identity / retraction / COI / currency checks (plan §20);
- the instruction/data boundary: retrieved content is *untrusted data* (§32);
- a contradiction clusterer and type detector (§25);
- the falsification-swarm plan for critical claims (§26).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from kdrx.schemas.claims import Claim, ContradictionCluster
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import (
    ContradictionStatus,
    ContradictionType,
    PrimarySecondary,
    QualityGrade,
    RetractionStatus,
    SourceType,
)
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.gate import GateKind

# Transporte HTTP injetável (ver adapters.py) — imports reais (adapters,
# security.egress_allowed) são lazy porque formariam ciclos:
# adapters -> corpus -> state -> security -> verification.
Transport = Callable[[str, dict[str, str] | None], str]


# --------------------------------------------------------------------------- #
# Retraction / correction alerts (T-10-02)
# --------------------------------------------------------------------------- #
_PROBLEM_STATUS = {
    RetractionStatus.RETRACTED.value,
    RetractionStatus.CORRECTED.value,
    RetractionStatus.EXPRESSED_CONCERN.value,
}


@dataclass
class RetractionAlert:
    """Fonte que mudou para status problemático + claims afetados."""

    source_id: str
    previous_status: str
    current_status: str
    #: claims com ao menos um support vindo da fonte afetada
    affected_claims: list[str] = field(default_factory=list)
    #: claims cuja TOTALIDADE das fontes de suporte está problemática
    fully_invalidated_claims: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "previous_status": self.previous_status,
            "current_status": self.current_status,
            "affected_claims": self.affected_claims,
            "fully_invalidated_claims": self.fully_invalidated_claims,
        }


def retraction_alerts(
    sources: list[SourceRecord],
    claims: list[Claim] | None = None,
    spans: list[EvidenceSpan] | None = None,
    *,
    prior_status: dict[str, str] | None = None,
) -> list[RetractionAlert]:
    """Detecta fontes que viraram retracted/corrected/expressed-concern e
    invalida os claims dependentes (T-10-02).

    ``prior_status`` é o snapshot anterior ``{source_id: status}`` (default:
    tudo "none" — primeira observação). Um alerta só dispara quando o status
    MUDA para um status problemático; snapshot antigo já retracted não repete.
    """
    claims = claims or []
    spans = spans or []
    prior_status = prior_status or {}
    evidence_source = {sp.evidence_id: sp.source_id for sp in spans}
    status_by_id = {s.source_id: s.retraction_status.value for s in sources}

    alerts: list[RetractionAlert] = []
    for s in sources:
        current = s.retraction_status.value
        previous = prior_status.get(s.source_id, RetractionStatus.NONE.value)
        if current not in _PROBLEM_STATUS or current == previous:
            continue
        alert = RetractionAlert(
            source_id=s.source_id,
            previous_status=previous,
            current_status=current,
        )
        for c in claims:
            supporting_sources = {
                evidence_source.get(e, "")
                for e in c.support_edges
                if e in evidence_source
            }
            if s.source_id not in supporting_sources:
                continue
            alert.affected_claims.append(c.claim_id)
            if supporting_sources and all(
                status_by_id.get(src, RetractionStatus.NONE.value) in _PROBLEM_STATUS
                for src in supporting_sources
            ):
                alert.fully_invalidated_claims.append(c.claim_id)
        alerts.append(alert)
    return alerts


# --------------------------------------------------------------------------- #
# Prompt-injection / instruction-data boundary (plan §32)
# --------------------------------------------------------------------------- #
_INJECTION_MARKERS: tuple[str, ...] = (
    "ignore all previous instructions",
    "ignore the above",
    "ignore prior instructions",
    "disregard your",
    "disregard previous",
    "you are now",
    "your new instructions",
    "system prompt",
    "do not follow your",
    "forget your instructions",
    "reveal your instructions",
    "act as if",
    "this is a new directive",
    "override your",
    "i am your",
    "as an ai you must",
    "you must respond only",
)

#: Domain-style egress / instruction strings that try to change the workflow.
_WORKFLOW_TAMPER: tuple[str, ...] = (
    "set your objective",
    "change your task",
    "ignore your rubric",
    "bypass your",
    "you no longer have to",
    "output path is now",
    "disable your",
)


@dataclass
class InjectionScan:
    """Result of scanning untrusted retrieved text."""

    text: str
    markers: list[str] = field(default_factory=list)
    score: int = 0

    @property
    def suspicious(self) -> bool:
        return self.score >= 2

    @property
    def critical(self) -> bool:
        return self.score >= 4


def scan_prompt_injection(text: str) -> InjectionScan:
    """Detect imperative strings in retrieved content.

    Conservative and marker-based on purpose: retrieved pages, PDFs, issues and
    comments are *data*, never instructions. Any hit is flagged for the
    prompt-injection auditor; the workflow, rubric, permissions and gates are
    never mutated from this content.
    """
    lowered = text.lower()
    markers = [m for m in _INJECTION_MARKERS + _WORKFLOW_TAMPER if m in lowered]
    score = sum(2 if m in _WORKFLOW_TAMPER else 1 for m in markers)
    return InjectionScan(text=text, markers=markers, score=score)


def content_is_untrusted(text: str) -> bool:
    """True when content carries any imperative marker (data, not instruction)."""
    return scan_prompt_injection(text).suspicious


# --------------------------------------------------------------------------- #
# Source trust (plan §20)
# --------------------------------------------------------------------------- #
def source_identity_checks(record: SourceRecord) -> list[GateCheck]:
    """Existence / identity-match checks that are computable locally."""
    checks: list[GateCheck] = []
    has_uri = bool(record.canonical_uri.strip())
    checks.append(
        GateCheck(check_id="URI", description="canonical URI present", passed=has_uri)
    )
    checks.append(
        GateCheck(
            check_id="TITLE",
            description="title present",
            passed=bool(record.title.strip()),
        )
    )
    checks.append(
        GateCheck(
            check_id="TYPE",
            description="source type is not UNKNOWN",
            passed=record.source_type is not SourceType.UNKNOWN,
        )
    )
    checks.append(
        GateCheck(
            check_id="HASH",
            description="content hash present (enables dedup & versioning)",
            passed=bool(record.content_hash),
        )
    )
    return checks


def retraction_check(record: SourceRecord) -> GateCheck:
    """Flag retracted/corrected sources so they never ground a material claim.

    Apenas retração CONHECIDA bloqueia (``RETRACTED``); ``UNKNOWN`` significa
    "não verificado" e não pode ser bloqueante para corpus offline — o status
    fica visível nos details, e a ausência de verificação viva é limitação
    admitida do shelf-life state (ver risk policy por route).
    """
    ok = record.retraction_status != RetractionStatus.RETRACTED
    return GateCheck(
        check_id="RETRACTION",
        description=f"retraction status acceptable ({record.retraction_status})",
        passed=ok,
        details=record.retraction_status,
    )


def currency_check(record: SourceRecord, max_age_days: int = 730) -> GateCheck:
    """Staleness flag; a source can be real yet out-of-date (plan §20)."""
    from datetime import datetime, timezone

    if record.date is None:
        return GateCheck(
            check_id="CURRENCY",
            description="source date unknown; cannot assert freshness",
            passed=False,
            severity="advisory",
        )
    now = datetime.now(timezone.utc)
    age_days = (
        (now - record.date).days
        if record.date.tzinfo
        else (now.replace(tzinfo=None) - record.date).days
    )
    passed = age_days <= max_age_days
    return GateCheck(
        check_id="CURRENCY",
        description=f"source age {age_days}d within {max_age_days}d",
        passed=passed,
        details={"age_days": age_days, "max_age_days": max_age_days},
        severity="advisory",
    )


def coi_check(record: SourceRecord) -> GateCheck:
    # T-06-05: COI é dimensão SEPARADA e consistente — metadata declarada pelo
    # agente não pode divergir do campo tipado sem falhar a dimensão.
    meta_coi = (record.metadata or {}).get("conflicts_of_interest")
    mismatch = meta_coi is not None and list(meta_coi) != record.conflicts_of_interest
    passed = not record.conflicts_of_interest and not mismatch
    return GateCheck(
        check_id="COI",
        description="no declared conflicts of interest and metadata consistent",
        passed=passed,
        details={"typed": record.conflicts_of_interest, "metadata": meta_coi},
        severity="advisory",
    )


def source_quality_policy(record: SourceRecord) -> QualityGrade:
    """A small domain-relative trust heuristic (plan §20).

    The full registry is domain-specific; this default combines the signals a
    local record carries. It is a *floor*, never a replacement for verification.
    """
    grade = QualityGrade.UNVERIFIED
    if record.retraction_status == RetractionStatus.RETRACTED:
        return QualityGrade.REJECTED
    if record.primary_or_secondary.value == "primary":
        grade = QualityGrade.GOOD
    elif record.quality_grade is not QualityGrade.UNVERIFIED:
        grade = record.quality_grade
    if record.conflicts_of_interest:
        grade = QualityGrade.WEAK
    return grade


def source_trust_gate(
    record: SourceRecord,
    *,
    policy: DomainPolicy | None = None,
    resolution: DOIResolution | None = None,
) -> GateDecision:
    """Identity (blocking) + retraction (blocking) + dimensions (advisory).

    B-06/T-04-07: existência/identidade e retração BLOQUEIAM a entrega; COI e
    currency stale sinalizam qualidade sem bloquear por si sós. ``warn_is_pass``
    foi removido — falha blocking agora é FAIL de verdade.

    T-06-04: a política por domínio regge currency/tipo permitido/resolução
    obrigatória. T-06-01/07: quando uma ``DOIResolution`` é fornecida, os
    checks vivos entram como BLOCKING — DOI fabricado ou misrouted derruba o
    pipeline, não vira WARN.
    """
    policy = policy or policy_for_record(record)
    checks = source_identity_checks(record) + [
        retraction_check(record),
        coi_check(record),
        currency_check(record, policy.max_age_days),
        version_check(record),
    ]
    checks.extend(source_dimension_checks(record))
    if policy.allowed_source_types is not None:
        checks.append(
            GateCheck(
                check_id="SOURCE_TYPE_ALLOWED",
                description=f"source type allowed by domain policy {policy.domain}",
                passed=record.source_type in policy.allowed_source_types,
                details={
                    "policy": policy.domain,
                    "allowed": sorted(t.value for t in policy.allowed_source_types),
                    "actual": record.source_type.value,
                },
                severity="advisory",
            )
        )
    if resolution is not None:
        checks.extend(live_resolution_checks(record, resolution))
    elif policy.require_live_resolution and record.source_type != SourceType.DATASET:
        checks.append(
            GateCheck(
                check_id="LIVE_RESOLUTION",
                description="domain policy requires live resolution but none was provided",
                passed=False,
                details={"policy": policy.domain},
                severity="advisory",
            )
        )
    return GateDecision.compose(
        gate_id=f"gate:source:{record.source_id}",
        kind=GateKind.SOURCE,
        checks=checks,
    )


# --------------------------------------------------------------------------- #
# Live source verification (T-06-01..07, plan §20)
# --------------------------------------------------------------------------- #
def _norm_title(title: str) -> str:
    """Título normalizado para comparação de identidade (case/punct-insensitive)."""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _host_of(uri: str) -> str:
    return urllib.parse.urlparse(uri).netloc.lower()


@dataclass
class LiveMetadata:
    """Normalized bibliographic metadata fetched from a live registry."""

    registry: str
    title: str | None = None
    publisher: str | None = None
    date: datetime | None = None
    doi: str | None = None
    target_uri: str | None = None
    is_retracted: bool = False
    raw: dict = field(default_factory=dict)


def _csl_date(payload: dict) -> datetime | None:
    parts = payload.get("issued", {}).get("date-parts", [[None]])
    year = parts[0][0] if parts and parts[0] else None
    return datetime(year, 1, 1, tzinfo=timezone.utc) if year else None


def _title_marker_retracted(title: str | None) -> bool:
    if not title:
        return False
    lowered = title.lower()
    return (
        lowered.startswith("retracted:")
        or "[retraction]" in lowered
        or "retraction notice" in lowered
    )


def parse_csl_metadata(payload: dict, registry: str = "doi.org") -> LiveMetadata:
    """Parse CSL-JSON (doi.org content negotiation) into LiveMetadata."""
    title = payload.get("title")
    if isinstance(title, list):
        title = title[0] if title else None
    updates = payload.get("update-to", []) + payload.get("updates", [])
    is_retracted = _title_marker_retracted(title) or any(
        isinstance(u, dict) and u.get("type") == "retraction" for u in updates
    )
    doi = (payload.get("DOI") or "").lower() or None
    return LiveMetadata(
        registry=registry,
        title=title,
        publisher=payload.get("publisher"),
        date=_csl_date(payload),
        doi=doi,
        target_uri=payload.get("URL"),
        is_retracted=is_retracted,
        raw=payload,
    )


def parse_crossref_metadata(payload: dict) -> LiveMetadata:
    """Parse a Crossref `/works/{doi}` response into LiveMetadata."""
    return parse_csl_metadata(payload.get("message", {}), registry="crossref")


def parse_openalex_metadata(payload: dict) -> LiveMetadata:
    """Parse an OpenAlex work object into LiveMetadata."""
    date = None
    if payload.get("publication_date"):
        try:
            date = datetime.strptime(payload["publication_date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            date = None
    return LiveMetadata(
        registry="openalex",
        title=payload.get("title"),
        publisher=((payload.get("primary_location") or {}).get("source") or {}).get(
            "display_name"
        ),
        date=date,
        doi=(payload.get("doi") or "").removeprefix("https://doi.org/").lower() or None,
        target_uri=payload.get("id"),
        is_retracted=_title_marker_retracted(payload.get("title")),
        raw=payload,
    )


def parse_semanticscholar_metadata(payload: dict) -> LiveMetadata:
    """Parse a Semantic Scholar paper object into LiveMetadata."""
    year = payload.get("year")
    doi = (payload.get("externalIds") or {}).get("DOI")
    return LiveMetadata(
        registry="semanticscholar",
        title=payload.get("title"),
        publisher=payload.get("venue") or None,
        date=datetime(year, 1, 1, tzinfo=timezone.utc) if year else None,
        doi=doi.lower() if doi else None,
        target_uri=payload.get("url"),
        is_retracted=bool(payload.get("isRetracted", False))
        or _title_marker_retracted(payload.get("title")),
        raw=payload,
    )


@dataclass
class MetadataCacheEntry:
    metadata: LiveMetadata
    cached_at: datetime


class MetadataCache:
    """TTL cache for registry metadata — staleness is explicit, never silent."""

    def __init__(self, ttl_days: int = 30) -> None:
        self.ttl_days = ttl_days
        self._entries: dict[str, MetadataCacheEntry] = {}

    def get(self, key: str, now: datetime) -> tuple[LiveMetadata | None, bool]:
        """Returns (metadata, is_stale); (None, False) when absent."""
        entry = self._entries.get(key)
        if entry is None:
            return None, False
        stale = (now - entry.cached_at).days > self.ttl_days
        return entry.metadata, stale

    def put(self, key: str, metadata: LiveMetadata, now: datetime) -> None:
        self._entries[key] = MetadataCacheEntry(metadata=metadata, cached_at=now)


@dataclass
class DOIResolution:
    """Outcome of a live DOI resolution attempt."""

    doi: str
    resolves: bool
    metadata: LiveMetadata | None = None
    from_cache: bool = False
    cache_stale: bool = False
    error: str | None = None


class DOIResolver:
    """T-06-01/02: live DOI resolution over doi.org content negotiation.

    Proves a DOI *exists* over HTTPS and retrieves its bibliographic record.
    Fresh cache entries short-circuit HTTP; on outage a stale entry answers
    with explicit flags; without any cache the failure surfaces as
    ``resolves=False`` (never an exception).
    """

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        cache: MetadataCache | None = None,
        allowlist: set[str] | None = None,
        denylist: set[str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if transport is None:
            from kdrx.adapters import UrllibTransport

            transport = UrllibTransport()
        self.transport = transport
        self.cache = cache or MetadataCache()
        self.allowlist = allowlist
        self.denylist = denylist
        self._now = now or (lambda: datetime.now(timezone.utc))

    def resolve(self, doi: str) -> DOIResolution:
        from kdrx.adapters import AdapterError  # lazy: evita ciclo de imports
        from kdrx.security import egress_allowed  # lazy: security -> verification

        doi = doi.strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
        now = self._now()
        cached, stale = self.cache.get(doi, now)
        if cached is not None and not stale:
            return DOIResolution(
                doi=doi,
                resolves=True,
                metadata=cached,
                from_cache=True,
                cache_stale=False,
            )
        if not egress_allowed(
            "doi.org", allowlist=self.allowlist, denylist=self.denylist
        ):
            raise AdapterError("egress bloqueado pela policy para host 'doi.org'")
        try:
            text = self.transport(
                f"https://doi.org/{doi}",
                {"Accept": "application/vnd.citationstyles.csl+json"},
            )
            payload = json.loads(text)
        except (AdapterError, json.JSONDecodeError) as exc:
            if cached is not None:
                return DOIResolution(
                    doi=doi,
                    resolves=True,
                    metadata=cached,
                    from_cache=True,
                    cache_stale=stale,
                    error=str(exc),
                )
            return DOIResolution(doi=doi, resolves=False, error=str(exc))
        metadata = parse_csl_metadata(payload)
        metadata.doi = metadata.doi or doi
        self.cache.put(doi, metadata, now)
        return DOIResolution(
            doi=doi,
            resolves=True,
            metadata=metadata,
            from_cache=False,
            cache_stale=False,
        )


def record_doi(record: SourceRecord) -> str | None:
    """Extract a DOI from the record (metadata or canonical URI), if any."""
    doi = record.metadata.get("doi")
    if isinstance(doi, str) and doi.strip():
        return doi
    uri = record.canonical_uri
    if "doi.org/" in uri:
        return uri.split("doi.org/", 1)[1]
    if re.match(r"^10\.\d{4,9}/\S+$", uri.strip()):
        return uri.strip()
    return None


# --------------------------------------------------------------------------- #
# Live checks (T-06-03/07)
# --------------------------------------------------------------------------- #
def live_resolution_checks(
    record: SourceRecord, resolution: DOIResolution
) -> list[GateCheck]:
    """Blocking checks derived from a live resolution (DOI misrouting = critical)."""
    checks = [
        GateCheck(
            check_id="DOI_RESOLVES",
            description=f"DOI {resolution.doi} resolves over HTTPS",
            passed=resolution.resolves,
            details=(
                {"error": resolution.error, "from_cache": resolution.from_cache}
                if resolution.error
                else {
                    "from_cache": resolution.from_cache,
                    "cache_stale": resolution.cache_stale,
                }
            ),
            severity="blocking",
        )
    ]
    if not resolution.resolves or resolution.metadata is None:
        return checks
    meta = resolution.metadata
    titles_match = bool(meta.title) and _norm_title(meta.title or "") == _norm_title(
        record.title
    )
    # T-06-07: um DOI que resolve para OUTRO trabalho é falha CRÍTICA —
    # a identidade da fonte é falsa; bloqueia, não vira WARN.
    checks.append(
        GateCheck(
            check_id="DOI_TARGET_MATCHES",
            description="registry metadata title matches the record title",
            passed=titles_match,
            details={
                "record_title": record.title,
                "registry_title": meta.title,
                "critical": not titles_match,
            },
            severity="blocking",
        )
    )
    checks.append(live_retraction_check(record, meta))
    checks.append(date_consistency_check(record, meta))
    return checks


def live_retraction_check(record: SourceRecord, metadata: LiveMetadata) -> GateCheck:
    """T-06-03: live registry retraction status (retração conhecida bloqueia)."""
    return GateCheck(
        check_id="RETRACTION_LIVE",
        description=f"live registry ({metadata.registry}) reports no retraction",
        passed=not metadata.is_retracted,
        details={"registry": metadata.registry, "is_retracted": metadata.is_retracted},
        severity="blocking",
    )


def version_check(record: SourceRecord) -> GateCheck:
    """T-06-03: detect content changes since the source was last seen."""
    previous = record.metadata.get("previous_content_hash")
    changed = bool(previous) and previous != record.content_hash
    return GateCheck(
        check_id="VERSION",
        description="content version stable since last seen",
        passed=not changed,
        details={"previous": previous, "current": record.content_hash},
        severity="advisory",
    )


def date_consistency_check(record: SourceRecord, metadata: LiveMetadata) -> GateCheck:
    """T-06-03: record date must agree with the registry's publication year."""
    if record.date is None or metadata.date is None:
        return GateCheck(
            check_id="DATE_CONSISTENCY",
            description="insufficient date data to compare",
            passed=True,
            severity="advisory",
        )
    consistent = record.date.year == metadata.date.year
    return GateCheck(
        check_id="DATE_CONSISTENCY",
        description="record date matches registry publication year",
        passed=consistent,
        details={"record_year": record.date.year, "registry_year": metadata.date.year},
        severity="advisory",
    )


# --------------------------------------------------------------------------- #
# Domain policy registry (T-06-04)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DomainPolicy:
    """Per-domain trust policy: staleness window, mandatory live resolution and
    allowed source types. Longest suffix match against the source host wins."""

    domain: str
    max_age_days: int = 730
    require_live_resolution: bool = False
    allowed_source_types: frozenset[SourceType] | None = None


DEFAULT_DOMAIN_POLICY = DomainPolicy(domain="*")

POLICY_REGISTRY: dict[str, DomainPolicy] = {
    # preprints têm shelf-life longo; registry DOI exige verificação viva
    "arxiv.org": DomainPolicy(domain="arxiv.org", max_age_days=3650),
    "doi.org": DomainPolicy(domain="doi.org", require_live_resolution=True),
    "github.com": DomainPolicy(
        domain="github.com",
        max_age_days=1825,
        allowed_source_types=frozenset({SourceType.CODE_REPOSITORY}),
    ),
    "wikipedia.org": DomainPolicy(
        domain="wikipedia.org", allowed_source_types=frozenset({SourceType.WIKI})
    ),
}


def policy_for_record(
    record: SourceRecord, registry: dict[str, DomainPolicy] | None = None
) -> DomainPolicy:
    """Resolve the domain policy for a source (longest host suffix match)."""
    registry = registry or POLICY_REGISTRY
    host = _host_of(record.canonical_uri)
    best: DomainPolicy | None = None
    for domain, policy in registry.items():
        if host == domain or host.endswith("." + domain):
            if best is None or len(domain) > len(best.domain):
                best = policy
    return best or DEFAULT_DOMAIN_POLICY


# --------------------------------------------------------------------------- #
# Trust dimensions checked separately (T-06-05)
# --------------------------------------------------------------------------- #
def source_dimension_checks(record: SourceRecord) -> list[GateCheck]:
    """Primaryness / directness / independence as SEPARATE advisory dimensions.

    Cada dimensão cruza o que o agente DECLAROU em ``metadata`` com o que o
    campo tipado carrega: divergência = falha advisory (metadata nunca pode
    discordar silenciosamente do record). Dimensão não-avaliável (sem sinal)
    passa com descrição explícita — UNKNOWN não é prova de problema.
    """
    checks: list[GateCheck] = []
    meta = record.metadata or {}

    # primaryness: campo tipado vs declaração em metadata
    claimed_p = meta.get("primary_or_secondary")
    mismatch_p = (
        claimed_p is not None and claimed_p != record.primary_or_secondary.value
    )
    checks.append(
        GateCheck(
            check_id="PRIMARYNESS",
            description=(
                "primary/secondary dimension consistent"
                if record.primary_or_secondary is not PrimarySecondary.UNKNOWN
                else "primary/secondary unknown — dimension not evaluable"
            ),
            passed=not mismatch_p,
            details={
                "typed": record.primary_or_secondary.value,
                "metadata": claimed_p,
            },
            severity="advisory",
        )
    )

    # directness: derivada de dependencies (cópia/syndication => indirect)
    derived_d = "indirect" if record.dependencies else "direct"
    claimed_d = meta.get("directness")
    mismatch_d = claimed_d is not None and claimed_d != derived_d
    checks.append(
        GateCheck(
            check_id="DIRECTNESS",
            description="directness dimension consistent with dependencies",
            passed=not mismatch_d,
            details={"derived": derived_d, "metadata": claimed_d},
            severity="advisory",
        )
    )

    # independence: fonte sem dependencies é família independente
    derived_i = "dependent" if record.dependencies else "independent"
    claimed_i = meta.get("independence")
    mismatch_i = claimed_i is not None and claimed_i != derived_i
    checks.append(
        GateCheck(
            check_id="INDEPENDENCE",
            description="independence dimension consistent with dependency family",
            passed=not mismatch_i,
            details={"derived": derived_i, "metadata": claimed_i},
            severity="advisory",
        )
    )
    return checks


# --------------------------------------------------------------------------- #
# Contradiction detection & clustering (plan §25)
# --------------------------------------------------------------------------- #
def detect_contradiction_type(a: Claim, b: Claim) -> ContradictionType:
    """Heuristically classify the *kind* of disagreement between two claims.

    Semantic contradiction detection is model-assisted; this deterministic
    classifier covers the well-defined structural cases and defaults to
    ``FACTUAL`` otherwise.
    """
    if a.claim_type.value in ("forecast", "normative") or b.claim_type.value in (
        "forecast",
        "normative",
    ):
        return ContradictionType.FACTUAL
    a_scope = a.scope or {}
    b_scope = b.scope or {}
    # temporal mismatch: disjoint explicit time windows
    if "time" in a_scope and "time" in b_scope and a_scope["time"] != b_scope["time"]:
        return ContradictionType.TEMPORAL
    # jurisdiction mismatch
    if (
        "jurisdiction" in a_scope
        and "jurisdiction" in b_scope
        and a_scope["jurisdiction"] != b_scope["jurisdiction"]
    ):
        return ContradictionType.JURISDICTION
    # population/sample mismatch
    if (
        "population" in a_scope
        and "population" in b_scope
        and a_scope["population"] != b_scope["population"]
    ):
        return ContradictionType.POPULATION_SAMPLE
    # numerical disagreement on same subject
    a_num = _extract_numbers(a.statement)
    b_num = _extract_numbers(b.statement)
    if a_num and b_num and a_num != b_num:
        return ContradictionType.NUMERICAL
    return ContradictionType.FACTUAL


_NUM_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")


def _extract_numbers(statement: str) -> list[str]:
    return _NUM_PATTERN.findall(statement)


def infer_contradiction_pairs(claims: list[Claim]) -> list[tuple[str, str]]:
    """Infer CONTRADICTS pairs from claim content alone (no gold labels).

    Two claims pair as a contradiction when they share the same scope and
    make numerically different statements about the same normalized subject
    (numbers replaced by a placeholder). Semantic-only disagreement stays
    model-assisted and is out of scope for this deterministic check.
    """

    def _numeric_subject(statement: str) -> tuple[str, tuple[str, ...]]:
        nums = tuple(_extract_numbers(statement))
        subject = (
            re.sub(r"\s+", " ", _NUM_PATTERN.sub("<NUM>", statement)).strip().lower()
        )
        return subject, nums

    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(claims):
        for b in claims[i + 1 :]:
            if (a.scope or {}) != (b.scope or {}):
                continue
            subject_a, nums_a = _numeric_subject(a.statement)
            subject_b, nums_b = _numeric_subject(b.statement)
            if subject_a != subject_b or not nums_a or not nums_b or nums_a == nums_b:
                continue
            pairs.append((a.claim_id, b.claim_id))
    return pairs


def cluster_contradictions(
    claims: list[Claim], contradicting_pairs: list[tuple[str, str]]
) -> list[ContradictionCluster]:
    """Group claims connected by CONTRADICTS edges into clusters.

    Uses union-find so a 3-way disagreement (A vs B, B vs C) becomes one cluster.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for x, y in contradicting_pairs:
        union(x, y)

    groups: dict[str, list[str]] = {}
    for c in claims:
        groups.setdefault(find(c.claim_id), []).append(c.claim_id)

    clusters: list[ContradictionCluster] = []
    for i, members in enumerate(groups.values()):
        if len(members) < 2:
            continue
        member_claims = [c for c in claims if c.claim_id in members]
        ctype = (
            detect_contradiction_type(member_claims[0], member_claims[1])
            if len(member_claims) >= 2
            else ContradictionType.FACTUAL
        )
        clusters.append(
            ContradictionCluster(
                contradiction_id=f"CT-{i}",
                claims=members,
                contradiction_type=ctype,
                status=ContradictionStatus.OPEN,
            )
        )
    return clusters


# --------------------------------------------------------------------------- #
# Falsification swarm (plan §26)
# --------------------------------------------------------------------------- #
@dataclass
class FalsificationPlan:
    claim_id: str
    roles: list[dict] = field(default_factory=list)
    minimum_new_searches: int = 3

    @classmethod
    def for_claim(cls, claim: Claim) -> "FalsificationPlan":
        """The five falsification roles for a critical claim."""
        roles = [
            {"role": "support", "goal": "find support", "query_hint": claim.statement},
            {
                "role": "refute",
                "goal": "find refutation",
                "query_hint": f"contradiction to: {claim.statement}",
            },
            {
                "role": "alternative",
                "goal": "find alternative explanations",
                "query_hint": f"alternative to: {claim.statement}",
            },
            {"role": "verify", "goal": "verify evidence spans", "query_hint": None},
            {"role": "calibrate", "goal": "update standing", "query_hint": None},
        ]
        return cls(claim_id=claim.claim_id, roles=roles)


def minimum_new_search_rule(
    used_queries: set[str], new_queries: list[str], minimum: int = 3
) -> bool:
    """Enforce that conflict resolution uses fresh, unused queries (plan §26)."""
    fresh = [q for q in new_queries if q not in used_queries]
    return len(fresh) >= minimum
