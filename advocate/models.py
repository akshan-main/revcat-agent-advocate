from pydantic import BaseModel
from enum import Enum


# --- Enums ---

class ContentType(str, Enum):
    TUTORIAL = "tutorial"
    CASE_STUDY = "case_study"
    AGENT_PLAYBOOK = "agent_playbook"
    SEO_PAGE = "seo_page"


class ExperimentStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    CONCLUDED = "concluded"


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class FeedbackArea(str, Enum):
    SDK = "sdk"
    DASHBOARD = "dashboard"
    API = "api"
    DOCS = "docs"
    CHARTS = "charts"
    PAYWALLS = "paywalls"
    OFFERINGS = "offerings"
    MCP = "mcp"
    OTHER = "other"


class InteractionChannel(str, Enum):
    GITHUB = "github"
    STACKOVERFLOW = "stackoverflow"
    DISCORD = "discord"
    TWITTER = "twitter"
    REDDIT = "reddit"
    OTHER = "other"


class InteractionIntent(str, Enum):
    ANSWER_QUESTION = "answer_question"
    SHARE_RESOURCE = "share_resource"
    PROVIDE_FEEDBACK = "provide_feedback"
    ENGAGE = "engage"


class SEOTemplateType(str, Enum):
    COMPARISON = "comparison"
    HOW_TO = "how_to"
    GLOSSARY = "glossary"


# --- Content ---

class Section(BaseModel):
    heading: str
    key_points: list[str]
    source_refs: list[str] = []
    has_code_snippet: bool = False
    snippet_language: str = "python"
    snippet_code: str = ""


class ContentOutline(BaseModel):
    title: str
    content_type: ContentType
    sections: list[Section]
    sources: list[str] = []
    estimated_word_count: int = 0


class SourceCitation(BaseModel):
    url: str
    doc_sha256: str = ""
    sections_cited: int = 0
    snippet_hashes: list[str] = []


class VerificationResult(BaseModel):
    citations_all_reachable: bool = True
    dead_links: list[str] = []
    snippet_syntax_valid: bool = True
    doc_sha256_matches: bool = True
    details: list[str] = []


class ContentPiece(BaseModel):
    slug: str
    title: str
    content_type: ContentType
    status: str = "draft"
    body_md: str = ""
    outline: ContentOutline | None = None
    sources: list[SourceCitation] = []
    verification: VerificationResult | None = None
    created_at: str = ""
    published_at: str | None = None
    word_count: int = 0
    citations_count: int = 0


# --- Growth ---

class ExperimentDefinition(BaseModel):
    name: str
    hypothesis: str
    metric: str
    channel: str
    tactic: str
    required_inputs: list[str] = []
    duration_days: int = 7


class GrowthExperiment(BaseModel):
    name: str
    hypothesis: str
    metric: str
    channel: str
    tactic: str
    status: ExperimentStatus = ExperimentStatus.PLANNED
    inputs: dict = {}
    outputs: dict = {}
    results: dict = {}
    duration_days: int = 7
    created_at: str = ""
    concluded_at: str | None = None


# --- Community ---

class CommunityInteraction(BaseModel):
    channel: InteractionChannel
    thread_url: str = ""
    counterpart: str = ""
    intent: InteractionIntent
    question: str = ""
    draft_response: str = ""
    status: str = "draft"
    notes: str = ""
    created_at: str = ""
    sent_at: str | None = None


# --- Feedback ---

class ProductFeedback(BaseModel):
    title: str
    severity: Severity
    area: FeedbackArea
    repro_steps: str = ""
    expected: str = ""
    actual: str = ""
    evidence_links: list[str] = []
    proposed_fix: str = ""
    status: str = "new"
    github_issue_url: str | None = None
    created_at: str = ""
    submitted_at: str | None = None


# --- Search ---

class SearchResult(BaseModel):
    url: str
    path: str
    title: str
    score: float
    snippets: list[str] = []
    doc_sha256: str = ""


# --- Ledger ---

class LedgerToolCall(BaseModel):
    tool: str
    params_summary: str = ""
    result_summary: str = ""


class LedgerSource(BaseModel):
    url: str
    doc_sha256: str = ""
    sections_cited: int = 0
    snippet_hashes: list[str] = []


class LedgerOutputs(BaseModel):
    artifact_type: str = ""
    artifact_path: str = ""
    word_count: int = 0
    citations_count: int = 0
    code_snippets: int = 0
    additional: dict = {}


class RunEntry(BaseModel):
    run_id: str
    sequence: int
    prev_hash: str
    command: str
    started_at: str
    ended_at: str = ""
    inputs: dict = {}
    sources_used: list[LedgerSource] = []
    tool_calls: list[LedgerToolCall] = []
    outputs: LedgerOutputs = LedgerOutputs()
    verification: VerificationResult | None = None
    hash: str = ""
    signature: str | None = None
    success: bool = True


class ChainVerification(BaseModel):
    valid: bool
    total_entries: int
    breaks: list[int] = []
    hmac_verified: bool | None = None
