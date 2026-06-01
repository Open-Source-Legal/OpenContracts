import enum


class OpenContractsEnum(str, enum.Enum):
    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]


class ExportType(OpenContractsEnum):
    LANGCHAIN = "LANGCHAIN"
    OPEN_CONTRACTS = "OPEN_CONTRACTS"
    OPEN_CONTRACTS_V2 = "OPEN_CONTRACTS_V2"
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
    CANCELLED = "CANCELLED"

    @classmethod
    def choices(cls):
        return [(key, key) for key in cls]


class PermissionTypes(str, enum.Enum):
    CREATE = "CREATE"
    READ = "READ"
    EDIT = "EDIT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    COMMENT = "COMMENT"
    PERMISSION = "PERMISSION"
    PUBLISH = "PUBLISH"
    CRUD = "CRUD"
    ALL = "ALL"


# str-mixin (like every sibling enum here) so a member and its string value
# compare equal: the GraphQL/Celery boundaries deliver the value as a plain
# string while in-process callers pass the member, and both must hit the same
# branches in build_label_lookups / build_document_export (issue #1868).
class AnnotationFilterMode(str, enum.Enum):
    CORPUS_LABELSET_ONLY = "CORPUS_LABELSET_ONLY"
    CORPUS_LABELSET_PLUS_ANALYSES = "CORPUS_LABELSET_PLUS_ANALYSES"
    ANALYSES_ONLY = "ANALYSES_ONLY"


class ContentModality(str, enum.Enum):
    """
    Content modalities that can be present in an annotation or supported by an embedder.

    Used to track:
    - What types of content an annotation contains (content_modalities field)
    - What modalities an embedder can process (supported_modalities attribute)

    This enables embedders to filter annotations they can process and allows
    cross-modal similarity search when embedders support multiple modalities
    in the same vector space (e.g., CLIP for text + images).
    """

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"  # Future
    TABLE = "TABLE"  # Future
    VIDEO = "VIDEO"  # Future

    @classmethod
    def choices(cls):
        return [(key.value, key.name) for key in cls]

    @classmethod
    def from_string(cls, value: str) -> "ContentModality":
        """
        Convert a string to ContentModality enum.

        Args:
            value: String like "TEXT", "IMAGE", etc.

        Returns:
            Corresponding ContentModality enum value.

        Raises:
            ValueError: If string doesn't match any modality.
        """
        try:
            return cls(value.upper())
        except ValueError:
            raise ValueError(
                f"Unknown modality: {value}. Valid values: {[m.value for m in cls]}"
            )

    @classmethod
    def from_strings(cls, values: list[str]) -> set["ContentModality"]:
        """
        Convert a list of strings to a set of ContentModality enums.

        Args:
            values: List of strings like ["TEXT", "IMAGE"]

        Returns:
            Set of ContentModality enum values.
        """
        return {cls.from_string(v) for v in values}

    @classmethod
    def to_strings(cls, modalities: set["ContentModality"]) -> list[str]:
        """
        Convert a set of ContentModality enums to a list of strings.

        Args:
            modalities: Set of ContentModality enum values.

        Returns:
            List of string values like ["TEXT", "IMAGE"].
        """
        return [m.value for m in modalities]
