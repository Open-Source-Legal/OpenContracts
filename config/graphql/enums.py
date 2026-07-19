"""GraphQL enum types (generated to match the golden SDL)."""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501 — generated enum descriptions (long value docstrings).

from enum import Enum

import strawberry


@strawberry.enum(name="AgentTypeEnum", description="Enum for agent types in messages.")
class AgentTypeEnum(Enum):
    DOCUMENT_AGENT = "document_agent"
    CORPUS_AGENT = "corpus_agent"


@strawberry.enum(
    name="AgentsAgentActionResultStatusChoices", description="An enumeration."
)
class AgentsAgentActionResultStatusChoices(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@strawberry.enum(
    name="AgentsAgentConfigurationScopeChoices", description="An enumeration."
)
class AgentsAgentConfigurationScopeChoices(Enum):
    GLOBAL = "GLOBAL"
    CORPUS = "CORPUS"


@strawberry.enum(name="AnalyzerAnalysisStatusChoices", description="An enumeration.")
class AnalyzerAnalysisStatusChoices(Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@strawberry.enum(name="AnnotationFilterMode", description="An enumeration.")
class AnnotationFilterMode(Enum):
    CORPUS_LABELSET_ONLY = "CORPUS_LABELSET_ONLY"
    CORPUS_LABELSET_PLUS_ANALYSES = "CORPUS_LABELSET_PLUS_ANALYSES"
    ANALYSES_ONLY = "ANALYSES_ONLY"


@strawberry.enum(
    name="AnnotationsAnnotationLabelLabelTypeChoices", description="An enumeration."
)
class AnnotationsAnnotationLabelLabelTypeChoices(Enum):
    RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
    DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
    TOKEN_LABEL = "TOKEN_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


@strawberry.enum(
    name="AnnotationsAuthorityFrontierAuthorityTypeChoices",
    description="An enumeration.",
)
class AnnotationsAuthorityFrontierAuthorityTypeChoices(Enum):
    STATUTE = "statute"
    REGULATION = "regulation"
    ADMIN_RULE = "admin-rule"
    MUNICIPAL_ORDINANCE = "municipal-ordinance"
    CASE = "case"
    CONSTITUTION = "constitution"
    COURT_RULE = "court-rule"
    GUIDANCE = "guidance"
    TREATY = "treaty"


@strawberry.enum(
    name="AnnotationsAuthorityFrontierDiscoveryStateChoices",
    description="An enumeration.",
)
class AnnotationsAuthorityFrontierDiscoveryStateChoices(Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    INGESTED = "ingested"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    BLOCKED_LICENSE = "blocked_license"
    BLOCKED_DOMAIN = "blocked_domain"
    UNLOCATED = "unlocated"
    PENDING_APPROVAL = "pending_approval"
    DEFERRED_CAP = "deferred_cap"


@strawberry.enum(
    name="AnnotationsAuthorityKeyEquivalenceSourceChoices",
    description="An enumeration.",
)
class AnnotationsAuthorityKeyEquivalenceSourceChoices(Enum):
    USLM = "uslm"
    POPULAR_NAME = "popular_name"
    BASELINE = "baseline"
    MANUAL = "manual"


@strawberry.enum(
    name="AnnotationsCorpusReferenceAuthorityTypeChoices", description="An enumeration."
)
class AnnotationsCorpusReferenceAuthorityTypeChoices(Enum):
    STATUTE = "statute"
    REGULATION = "regulation"
    ADMIN_RULE = "admin-rule"
    MUNICIPAL_ORDINANCE = "municipal-ordinance"
    CASE = "case"
    CONSTITUTION = "constitution"
    COURT_RULE = "court-rule"
    GUIDANCE = "guidance"
    TREATY = "treaty"


@strawberry.enum(
    name="AnnotationsCorpusReferenceDetectionTierChoices", description="An enumeration."
)
class AnnotationsCorpusReferenceDetectionTierChoices(Enum):
    REGISTRY = "registry"
    GRAMMAR = "grammar"
    LLM = "llm"


@strawberry.enum(
    name="AnnotationsCorpusReferenceReferenceTypeChoices", description="An enumeration."
)
class AnnotationsCorpusReferenceReferenceTypeChoices(Enum):
    LAW = "LAW"
    DOCUMENT = "DOCUMENT"
    SECTION = "SECTION"
    DEFINED_TERM = "DEFINED_TERM"


@strawberry.enum(
    name="AnnotationsCorpusReferenceResolutionStatusChoices",
    description="An enumeration.",
)
class AnnotationsCorpusReferenceResolutionStatusChoices(Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    EXTERNAL = "EXTERNAL"


@strawberry.enum(name="BadgesBadgeBadgeTypeChoices", description="An enumeration.")
class BadgesBadgeBadgeTypeChoices(Enum):
    GLOBAL = "GLOBAL"
    CORPUS = "CORPUS"


@strawberry.enum(
    name="ConversationTypeEnum", description="Enum for conversation types."
)
class ConversationTypeEnum(Enum):
    CHAT = "chat"
    THREAD = "thread"


@strawberry.enum(
    name="ConversationsChatMessageMsgTypeChoices", description="An enumeration."
)
class ConversationsChatMessageMsgTypeChoices(Enum):
    SYSTEM = "SYSTEM"
    HUMAN = "HUMAN"
    LLM = "LLM"


@strawberry.enum(
    name="ConversationsChatMessageStateChoices", description="An enumeration."
)
class ConversationsChatMessageStateChoices(Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"
    AWAITING_APPROVAL = "awaiting_approval"


@strawberry.enum(
    name="ConversationsModerationActionActionTypeChoices", description="An enumeration."
)
class ConversationsModerationActionActionTypeChoices(Enum):
    LOCK_THREAD = "lock_thread"
    UNLOCK_THREAD = "unlock_thread"
    PIN_THREAD = "pin_thread"
    UNPIN_THREAD = "unpin_thread"
    DELETE_THREAD = "delete_thread"
    RESTORE_THREAD = "restore_thread"
    DELETE_MESSAGE = "delete_message"
    RESTORE_MESSAGE = "restore_message"


@strawberry.enum(
    name="CorpusesCorpusActionExecutionActionTypeChoices", description="An enumeration."
)
class CorpusesCorpusActionExecutionActionTypeChoices(Enum):
    FIELDSET = "fieldset"
    ANALYZER = "analyzer"
    AGENT = "agent"


@strawberry.enum(
    name="CorpusesCorpusActionExecutionStatusChoices", description="An enumeration."
)
class CorpusesCorpusActionExecutionStatusChoices(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@strawberry.enum(
    name="CorpusesCorpusActionExecutionTriggerChoices", description="An enumeration."
)
class CorpusesCorpusActionExecutionTriggerChoices(Enum):
    ADD_DOCUMENT = "add_document"
    EDIT_DOCUMENT = "edit_document"
    NEW_THREAD = "new_thread"
    NEW_MESSAGE = "new_message"
    MANUAL_BATCH = "manual_batch"


@strawberry.enum(
    name="CorpusesCorpusActionTemplateTriggerChoices", description="An enumeration."
)
class CorpusesCorpusActionTemplateTriggerChoices(Enum):
    ADD_DOCUMENT = "add_document"
    EDIT_DOCUMENT = "edit_document"
    NEW_THREAD = "new_thread"
    NEW_MESSAGE = "new_message"


@strawberry.enum(
    name="CorpusesCorpusActionTriggerChoices", description="An enumeration."
)
class CorpusesCorpusActionTriggerChoices(Enum):
    ADD_DOCUMENT = "add_document"
    EDIT_DOCUMENT = "edit_document"
    NEW_THREAD = "new_thread"
    NEW_MESSAGE = "new_message"


@strawberry.enum(name="CorpusesCorpusLicenseChoices", description="An enumeration.")
class CorpusesCorpusLicenseChoices(Enum):
    A_ = ""
    CC_BY_4_0 = "CC-BY-4.0"
    CC_BY_SA_4_0 = "CC-BY-SA-4.0"
    CC_BY_NC_4_0 = "CC-BY-NC-4.0"
    CC_BY_NC_SA_4_0 = "CC-BY-NC-SA-4.0"
    CC_BY_ND_4_0 = "CC-BY-ND-4.0"
    CC_BY_NC_ND_4_0 = "CC-BY-NC-ND-4.0"
    CC0_1_0 = "CC0-1.0"
    CUSTOM = "CUSTOM"


@strawberry.enum(
    name="DocumentProcessingStatusEnum",
    description="Enum for document processing status in the parsing pipeline.",
)
class DocumentProcessingStatusEnum(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@strawberry.enum(
    name="DocumentsDocumentRelationshipRelationshipTypeChoices",
    description="An enumeration.",
)
class DocumentsDocumentRelationshipRelationshipTypeChoices(Enum):
    NOTES = "NOTES"
    RELATIONSHIP = "RELATIONSHIP"


@strawberry.enum(
    name="DocumentsIngestionSourceSourceTypeChoices", description="An enumeration."
)
class DocumentsIngestionSourceSourceTypeChoices(Enum):
    MANUAL = "manual"
    CRAWLER = "crawler"
    API = "api"
    PIPELINE = "pipeline"
    SYNC = "sync"


@strawberry.enum(name="ExportType", description="An enumeration.")
class ExportType(Enum):
    LANGCHAIN = "LANGCHAIN"
    OPEN_CONTRACTS = "OPEN_CONTRACTS"
    OPEN_CONTRACTS_V2 = "OPEN_CONTRACTS_V2"
    FUNSD = "FUNSD"


@strawberry.enum(
    name="ExtractDiffStatus",
    description="Cell-level diff result between two iterations of the same extract.",
)
class ExtractDiffStatus(Enum):
    UNCHANGED = "UNCHANGED"
    CHANGED = "CHANGED"
    ONLY_IN_A = "ONLY_IN_A"
    ONLY_IN_B = "ONLY_IN_B"


@strawberry.enum(name="ExtractsColumnDataTypeChoices", description="An enumeration.")
class ExtractsColumnDataTypeChoices(Enum):
    STRING = "STRING"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    DATE = "DATE"
    DATETIME = "DATETIME"
    URL = "URL"
    EMAIL = "EMAIL"
    CHOICE = "CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    JSON = "JSON"


@strawberry.enum(name="FileTypeEnum", description="An enumeration.")
class FileTypeEnum(Enum):
    PDF = "pdf"
    TXT = "txt"
    MD = "md"
    DOCX = "docx"


@strawberry.enum(
    name="IngestionSourceTypeEnum",
    description="Category of integration that produces documents.\n\n    Named 'Category' to avoid confusion with the GraphQL IngestionSourceType\n    (DjangoObjectType) defined in config/graphql/document_types.py.\n    ",
)
class IngestionSourceTypeEnum(Enum):
    MANUAL = "manual"
    CRAWLER = "crawler"
    API = "api"
    PIPELINE = "pipeline"
    SYNC = "sync"


@strawberry.enum(name="LabelType", description="An enumeration.")
class LabelType(Enum):
    DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
    TOKEN_LABEL = "TOKEN_LABEL"
    RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


@strawberry.enum(name="LabelTypeEnum")
class LabelTypeEnum(Enum):
    RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
    DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
    TOKEN_LABEL = "TOKEN_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


@strawberry.enum(
    name="LeaderboardMetricEnum",
    description="Enum for different leaderboard metrics.\n\nIssue: #613 - Create leaderboard and community stats dashboard\nEpic: #572 - Social Features Epic",
)
class LeaderboardMetricEnum(Enum):
    BADGES = "badges"
    MESSAGES = "messages"
    THREADS = "threads"
    ANNOTATIONS = "annotations"
    REPUTATION = "reputation"


@strawberry.enum(
    name="LeaderboardScopeEnum",
    description="Enum for leaderboard scope (time period or corpus).\n\nIssue: #613 - Create leaderboard and community stats dashboard",
)
class LeaderboardScopeEnum(Enum):
    ALL_TIME = "all_time"
    MONTHLY = "monthly"
    WEEKLY = "weekly"


@strawberry.enum(
    name="NotificationsNotificationNotificationTypeChoices",
    description="An enumeration.",
)
class NotificationsNotificationNotificationTypeChoices(Enum):
    REPLY = "REPLY"
    VOTE = "VOTE"
    BADGE = "BADGE"
    MENTION = "MENTION"
    ACCEPTED = "ACCEPTED"
    THREAD_LOCKED = "THREAD_LOCKED"
    THREAD_UNLOCKED = "THREAD_UNLOCKED"
    THREAD_PINNED = "THREAD_PINNED"
    THREAD_UNPINNED = "THREAD_UNPINNED"
    MESSAGE_DELETED = "MESSAGE_DELETED"
    THREAD_DELETED = "THREAD_DELETED"
    MESSAGE_RESTORED = "MESSAGE_RESTORED"
    THREAD_RESTORED = "THREAD_RESTORED"
    THREAD_REPLY = "THREAD_REPLY"
    DOCUMENT_PROCESSED = "DOCUMENT_PROCESSED"
    DOCUMENT_PROCESSING_FAILED = "DOCUMENT_PROCESSING_FAILED"
    EXTRACT_COMPLETE = "EXTRACT_COMPLETE"
    ANALYSIS_RUNNING = "ANALYSIS_RUNNING"
    ANALYSIS_COMPLETE = "ANALYSIS_COMPLETE"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    EXPORT_COMPLETE = "EXPORT_COMPLETE"
    DOCUMENT_PUBLICIZED = "DOCUMENT_PUBLICIZED"
    RESEARCH_REPORT_COMPLETE = "RESEARCH_REPORT_COMPLETE"
    RESEARCH_REPORT_FAILED = "RESEARCH_REPORT_FAILED"
    RESEARCH_REPORT_CANCELLED = "RESEARCH_REPORT_CANCELLED"
    RESEARCH_REPORT_PROGRESS = "RESEARCH_REPORT_PROGRESS"


@strawberry.enum(
    name="PathActionEnum", description="Enum for document path lifecycle actions."
)
class PathActionEnum(Enum):
    IMPORTED = "IMPORTED"
    MOVED = "MOVED"
    RENAMED = "RENAMED"
    DELETED = "DELETED"
    RESTORED = "RESTORED"
    UPDATED = "UPDATED"


@strawberry.enum(
    name="ResearchResearchReportStatusChoices", description="An enumeration."
)
class ResearchResearchReportStatusChoices(Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@strawberry.enum(name="UsersUserExportFormatChoices", description="An enumeration.")
class UsersUserExportFormatChoices(Enum):
    LANGCHAIN = "LANGCHAIN"
    OPEN_CONTRACTS = "OPEN_CONTRACTS"
    OPEN_CONTRACTS_V2 = "OPEN_CONTRACTS_V2"
    FUNSD = "FUNSD"


@strawberry.enum(
    name="VersionChangeTypeEnum", description="Enum for types of version changes."
)
class VersionChangeTypeEnum(Enum):
    INITIAL = "INITIAL"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    MINOR_EDIT = "MINOR_EDIT"
    MAJOR_REVISION = "MAJOR_REVISION"
