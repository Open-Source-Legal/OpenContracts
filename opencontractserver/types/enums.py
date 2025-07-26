import enum
from enum import Enum


class OpenContractsEnum(str, enum.Enum):
    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class ExportType(OpenContractsEnum):
    LANGCHAIN = "LANGCHAIN"
    OPEN_CONTRACTS = "OPEN_CONTRACTS"
    FUNSD = "FUNSD"


class LabelType(str, enum.Enum):
    DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
    TOKEN_LABEL = "TOKEN_LABEL"
    RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
    SPAN_LABEL = "SPAN_LABEL"


class JobStatus(str, enum.Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    @classmethod
    def choices(cls):
        return [(key, key) for key in cls]


class PermissionTypes(str, enum.Enum):
    CREATE = "CREATE"
    READ = "READ"
    EDIT = "EDIT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PERMISSION = "PERMISSION"
    PUBLISH = "PUBLISH"
    CRUD = "CRUD"
    ALL = "ALL"


class AnnotationFilterMode(Enum):
    CORPUS_LABELSET_ONLY = "CORPUS_LABELSET_ONLY"
    CORPUS_LABELSET_PLUS_ANALYSES = "CORPUS_LABELSET_PLUS_ANALYSES"
    ANALYSES_ONLY = "ANALYSES_ONLY"
