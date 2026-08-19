"""Canonical enums for KDR-X.

These are the closed vocabularies that deterministic gates and hooks validate
against. They intentionally map one-to-one to the taxonomy in
``Plano/PLANO_SOTA_SUPER_DEEP_RESEARCH.md`` so that prompts, schemas and
validators cannot drift apart.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """str-valued enum so members serialize to plain JSON strings."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
class Route(StrEnum):
    """Research routes R0..R12 (plan §13)."""

    QUICK_BRIEF = "R0"
    FOCUSED_DEEP_RESEARCH = "R1"
    WIDE_LANDSCAPE = "R2"
    FILE_ONLY = "R3"
    FILE_AUGMENTED = "R4"
    ACADEMIC = "R5"
    SYSTEMATIC_REVIEW = "R6"
    STRUCTURED_ENUMERATION = "R7"
    CODE_RESEARCH = "R8"
    DATA_FIRST = "R9"
    MULTIMODAL = "R10"
    CROSS_LINGUAL = "R11"
    CONTINUOUS_MONITORING = "R12"


class RiskLevel(StrEnum):
    """HITL risk tiers (plan §30)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    REGULATED = "regulated"


# --------------------------------------------------------------------------- #
# Task lifecycle
# --------------------------------------------------------------------------- #
class TaskStage(StrEnum):
    """Stage a task belongs to, mapped to wave ordering."""

    INTAKE = "intake"
    PLANNING = "planning"
    RETRIEVAL = "retrieval"
    VERIFICATION = "verification"
    ANALYSIS = "analysis"
    SYNTHESIS = "synthesis"
    WRITING = "writing"
    REVIEW = "review"
    DELIVERY = "delivery"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class Criticality(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AgentRole(StrEnum):
    """The agent taxonomy (plan §17), grouped by family."""

    # Planning
    INTAKE_ANALYST = "intake_analyst"
    REQUIREMENTS_ANALYST = "requirements_analyst"
    RQ_FORMULATOR = "rq_formulator"
    METHODOLOGY_ARCHITECT = "methodology_architect"
    DIMENSION_MAPPER = "dimension_mapper"
    RETRIEVAL_STRATEGIST = "retrieval_strategist"
    RISK_PLANNER = "risk_planner"
    DAG_REVIEWER = "dag_reviewer"
    DAG_VERIFIER = "dag_verifier"
    # Discovery
    WEB_EXPLORER = "web_explorer"
    PRIMARY_SOURCE_FINDER = "primary_source_finder"
    ACADEMIC_SEARCHER = "academic_searcher"
    OFFICIAL_DOCS_SEARCHER = "official_docs_searcher"
    CODE_EXPLORER = "code_explorer"
    DATASET_FINDER = "dataset_finder"
    NEWS_SEARCHER = "news_searcher"
    LOCAL_LANGUAGE_SEARCHER = "local_language_searcher"
    MULTIMODAL_FINDER = "multimodal_finder"
    ARCHIVE_RESEARCHER = "archive_researcher"
    # Evidence
    SOURCE_RESOLVER = "source_resolver"
    METADATA_VERIFIER = "metadata_verifier"
    RETRACTION_CHECKER = "retraction_checker"
    VENUE_VERIFIER = "venue_verifier"
    EVIDENCE_SPAN_EXTRACTOR = "evidence_span_extractor"
    TABLE_FIGURE_EXTRACTOR = "table_figure_extractor"
    ENTITY_RESOLVER = "entity_resolver"
    DEDUPLICATOR = "deduplicator"
    CITATION_CONTEXT_VERIFIER = "citation_context_verifier"
    DATA_VERIFIER = "data_verifier"
    # Reasoning
    CLAIM_DECOMPOSER = "claim_decomposer"
    CONTRADICTION_ANALYST = "contradiction_analyst"
    COUNTEREVIDENCE_RESEARCHER = "counterevidence_researcher"
    ALTERNATIVE_HYPOTHESIS_ANALYST = "alternative_hypothesis_analyst"
    CAUSAL_REASONING_ANALYST = "causal_reasoning_analyst"
    STATISTICAL_ANALYST = "statistical_analyst"
    COMPARATIVE_ANALYST = "comparative_analyst"
    GAP_ANALYST = "gap_analyst"
    UNCERTAINTY_CALIBRATOR = "uncertainty_calibrator"
    SYNTHESIS_AGENT = "synthesis_agent"
    INSIGHT_EXTRACTOR = "insight_extractor"
    # Production
    OUTLINE_ARCHITECT = "outline_architect"
    SECTION_WRITER = "section_writer"
    TABLE_FIGURE_DESIGNER = "table_figure_designer"
    SECTION_REVIEWER = "section_reviewer"
    TRANSITION_EDITOR = "transition_editor"
    EXECUTIVE_SYNTHESIS_WRITER = "executive_synthesis_writer"
    CITATION_MANAGER = "citation_manager"
    REPORT_ASSEMBLER = "report_assembler"
    ARTIFACT_CONVERTER = "artifact_converter"
    # Audit
    DEVILS_ADVOCATE = "devils_advocate"
    METHODOLOGY_REVIEWER = "methodology_reviewer"
    SOURCE_VERIFIER = "source_verifier"
    CLAIM_VERIFIER = "claim_verifier"
    CALCULATION_VERIFIER = "calculation_verifier"
    PROMPT_INJECTION_AUDITOR = "prompt_injection_auditor"
    FINAL_INTEGRITY_AUDITOR = "final_integrity_auditor"


# --------------------------------------------------------------------------- #
# Corpus / source trust
# --------------------------------------------------------------------------- #
class SourceType(StrEnum):
    ACADEMIC_PAPER = "academic_paper"
    OFFICIAL_DOCUMENT = "official_document"
    GOVERNMENT = "government"
    LEGAL = "legal"
    NEWS = "news"
    BLOG = "blog"
    CODE_REPOSITORY = "code_repository"
    DATASET = "dataset"
    WIKI = "wiki"
    FORUM = "forum"
    PRESS_RELEASE = "press_release"
    PATENT = "patent"
    BOOK = "book"
    VIDEO = "video"
    IMAGE = "image"
    UNKNOWN = "unknown"


class PrimarySecondary(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    UNKNOWN = "unknown"


class QualityGrade(StrEnum):
    """A source can be real yet weak along an independent dimension (plan §20)."""

    EXCELLENT = "excellent"
    GOOD = "good"
    ADEQUATE = "adequate"
    WEAK = "weak"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class RetractionStatus(StrEnum):
    NONE = "none"
    RETRACTED = "retracted"
    CORRECTED = "corrected"
    EXPRESSED_CONCERN = "expressed_concern"
    UNKNOWN = "unknown"


class ExtractionStatus(StrEnum):
    NOT_EXTRACTED = "not_extracted"
    EXTRACTED = "extracted"
    FAILED = "failed"
    PAYWALLED = "paywalled"


class EvidenceType(StrEnum):
    VERBATIM = "verbatim"
    TABLE = "table"
    FIGURE = "figure"
    NUMBER = "number"
    DEFINITION = "definition"
    METHOD = "method"
    RESULT = "result"


class EvidenceLocatorType(StrEnum):
    PAGE = "page"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    LINE = "line"
    COMMIT = "commit"
    FILE = "file"


# --------------------------------------------------------------------------- #
# Claims / evidence graph
# --------------------------------------------------------------------------- #
class ClaimType(StrEnum):
    DESCRIPTIVE = "descriptive"
    COMPARATIVE = "comparative"
    CAUSAL = "causal"
    FORECAST = "forecast"
    NORMATIVE = "normative"


class ClaimImportance(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class Standing(StrEnum):
    """Claim standing verdict (plan §24)."""

    SUPPORTED = "supported"
    MIXED = "mixed"
    WEAK = "weak"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class EdgeRelation(StrEnum):
    """Claim <-> evidence relations (plan §23)."""

    SUPPORTS = "SUPPORTS"
    PARTIALLY_SUPPORTS = "PARTIALLY_SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    QUALIFIES = "QUALIFIES"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    IRRELEVANT = "IRRELEVANT"
    CANNOT_DETERMINE = "CANNOT_DETERMINE"


class EdgeDirectness(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    INFERRED = "inferred"


class ContradictionType(StrEnum):
    FACTUAL = "factual"
    NUMERICAL = "numerical"
    TEMPORAL = "temporal"
    DEFINITIONAL = "definitional"
    POPULATION_SAMPLE = "population_sample"
    METHODOLOGY = "methodology"
    JURISDICTION = "jurisdiction"
    VERSION = "version"
    SCOPE_RESOLVABLE = "scope_resolvable"
    IRREDUCIBLE = "irreducible"


class ContradictionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    IRREDUCIBLE = "irreducible"
    INVESTIGATING = "investigating"


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #
class GateKind(StrEnum):
    PLAN = "plan"
    SOURCE = "source"
    CLAIM = "claim"
    CITATION = "citation"
    INTEGRITY = "integrity"
    DELIVERY = "delivery"
    SECURITY = "security"


class GateVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    BLOCKED = "blocked"


# --------------------------------------------------------------------------- #
# Artifact
# --------------------------------------------------------------------------- #
class ArtifactKind(StrEnum):
    REPORT = "report"
    DOCX = "docx"
    PDF = "pdf"
    SITE = "site"
    TABLE = "table"
    FIGURE = "figure"
    DATASET = "dataset"
    SCRIPT = "script"
    MANIFEST = "manifest"


class SealLevel(StrEnum):
    """Provenance seal levels (Orchestra ARA-inspired)."""

    NONE = "none"
    LEVEL_1_HASHED = "level_1_hashed"
    LEVEL_2_SIGNED = "level_2_signed"
    LEVEL_3_REPRODUCIBLE = "level_3_reproducible"
