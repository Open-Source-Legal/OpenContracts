"""GraphQL type definitions for corpus-related types."""

import logging
from typing import Any

import graphene
from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Q, Subquery
from graphene import relay
from graphene_django import DjangoObjectType
from graphql_relay import from_global_id

from config.graphql.annotation_types import AnnotationType
from config.graphql.base import CountableConnection
from config.graphql.base_types import LabelTypeEnum
from config.graphql.document_types import DocumentTypeConnection
from config.graphql.permissioning.permission_annotator.mixins import (
    AnnotatePermissionsForReadMixin,
)
from opencontractserver.annotations.models import Annotation
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusCategory,
    CorpusEngagementMetrics,
    CorpusFolder,
    CorpusVote,
)
from opencontractserver.shared.services.base import BaseService
from opencontractserver.utils.auth import is_authenticated_user

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------- Corpus Category Types ----------------
class CorpusCategoryType(DjangoObjectType):
    """
    GraphQL type for corpus categories.

    NOTE: This type does NOT use AnnotatePermissionsForReadMixin because
    corpus categories are admin-provisioned structural data that is globally
    visible to all users and do not have per-user permissions.

    Categories are managed by superusers either via Django Admin or at
    runtime through the create/update/deleteCorpusCategory GraphQL mutations
    (see config/graphql/corpus_category_mutations.py) and the in-app
    "Corpus Categories" admin panel.

    See docs/permissioning/consolidated_permissioning_guide.md for details.
    """

    corpus_count = graphene.Int(description="Number of corpuses in this category")

    class Meta:
        model = CorpusCategory
        interfaces = (relay.Node,)
        connection_class = CountableConnection
        fields = (
            "id",
            "name",
            "description",
            "icon",
            "color",
            "sort_order",
            "creator",
            "is_public",
            "created",
            "modified",
        )

    def resolve_corpus_count(self, info) -> Any:
        """
        Return count of corpuses visible to user in this category.

        NOTE: This resolver could cause N+1 queries if many categories are fetched.
        The resolve_corpus_categories query uses annotation to pre-compute counts
        to avoid this issue.
        """
        # If the count was pre-annotated by the query resolver, use it
        if hasattr(self, "_corpus_count"):
            return self._corpus_count
        # Fallback to dynamic count (used when accessed individually)
        user = info.context.user
        visible_corpus_ids = BaseService.filter_visible(
            Corpus, user, request=info.context
        ).values("pk")
        return self.corpuses.filter(pk__in=visible_corpus_ids).count()


# ---------------- Engagement Metrics Types (Epic #565) ----------------
class CorpusEngagementMetricsType(graphene.ObjectType):
    """
    GraphQL type for corpus engagement metrics.

    This type does NOT use AnnotatePermissionsForReadMixin because
    engagement metrics are read-only and permissions are checked on
    the parent Corpus object.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
    """

    # Thread counts
    total_threads = graphene.Int(
        description="Total number of discussion threads in this corpus"
    )
    active_threads = graphene.Int(
        description="Number of active (not locked/deleted) threads"
    )

    # Message counts
    total_messages = graphene.Int(
        description="Total number of messages across all threads"
    )
    messages_last_7_days = graphene.Int(
        description="Number of messages posted in the last 7 days"
    )
    messages_last_30_days = graphene.Int(
        description="Number of messages posted in the last 30 days"
    )

    # Contributor counts
    unique_contributors = graphene.Int(
        description="Total number of unique users who have posted messages"
    )
    active_contributors_30_days = graphene.Int(
        description="Number of users who posted in the last 30 days"
    )

    # Engagement metrics
    total_upvotes = graphene.Int(
        description="Total upvotes across all messages in this corpus"
    )
    avg_messages_per_thread = graphene.Float(
        description="Average number of messages per thread"
    )

    # Metadata
    last_updated = graphene.DateTime(
        description="Timestamp when metrics were last calculated"
    )


class CorpusFolderType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    """
    GraphQL type for corpus folders.
    Folders inherit permissions from their parent corpus.
    """

    path = graphene.String(description="Full path from root to this folder")
    document_count = graphene.Int(
        description="Number of documents directly in this folder"
    )
    descendant_document_count = graphene.Int(
        description="Number of documents in this folder and all subfolders"
    )
    children = graphene.List(
        lambda: CorpusFolderType, description="Immediate child folders"
    )

    def resolve_path(self, info) -> Any:
        """Get full path from root to this folder.

        Prefers the ``_path`` attribute attached by
        :meth:`FolderCRUDService.get_visible_folders_with_aggregates` so the
        list-view resolver doesn't fire a recursive ancestor CTE per folder.
        Falls back to the per-folder ``get_path()`` for single-folder reads
        (e.g. the ``corpusFolder(id:)`` resolver).
        """
        if hasattr(self, "_path"):
            return self._path
        return self.get_path()

    def resolve_document_count(self, info) -> Any:
        """Get count of documents directly in this folder.

        Prefers the ``_doc_count`` attribute attached by
        :meth:`FolderCRUDService.get_visible_folders_with_aggregates` so the
        list-view resolver doesn't fire a per-folder ``COUNT`` on
        ``DocumentPath``.
        """
        if hasattr(self, "_doc_count"):
            return self._doc_count
        return self.get_document_count()

    def resolve_descendant_document_count(self, info) -> Any:
        """Get count of documents in this folder and all subfolders.

        Prefers the ``_descendant_doc_count`` attribute attached by
        :meth:`FolderCRUDService.get_visible_folders_with_aggregates` so the
        list-view resolver doesn't fire a recursive descendant CTE + COUNT
        per folder.
        """
        if hasattr(self, "_descendant_doc_count"):
            return self._descendant_doc_count
        return self.get_descendant_document_count()

    def resolve_children(self, info) -> Any:
        """Get immediate child folders (service-layer visibility)."""
        return BaseService.filter_visible_qs(
            self.children, info.context.user, request=info.context
        )

    def resolve_parent(self, info) -> Any:
        """Return the in-memory ``parent`` cached by ``select_related``.

        graphene-django's auto-generated FK resolver re-queries through
        ``CorpusFolderType.get_queryset`` (which chains
        ``visible_to_user().with_tree_fields()``), firing a recursive
        CTE plus two guardian-permission subqueries per row on the
        folder-list view — the exact ``N`` fan-out the
        :meth:`FolderCRUDService.get_visible_folders_with_aggregates`
        rewrite was supposed to kill. The parent is already
        ``select_related``-cached on the in-memory folder instance and
        the surrounding visibility filter authorised ``self``, so reading
        from the cache is equivalent and skips the per-row query. The
        ``_bypass_get_queryset`` flag on this resolver tells
        graphene-django's FK ``custom_resolver`` shim
        (``graphene_django/converter.py``) to skip its ``get_node`` /
        ``get_queryset`` round-trip and call this method directly — see
        the ``getattr(resolver, "_bypass_get_queryset", False)`` branch
        in ``DjangoObjectType._meta.connection_resolver``.
        """
        if self.parent_id is None:
            return None
        cached = self._state.fields_cache.get("parent")
        if cached is not None:
            return cached
        # Single-folder reads (no select_related) fall back to the
        # auto-generated resolver semantics via the standard descriptor.
        return self.parent

    # Tell graphene-django's FK resolver shim to skip its ``get_node`` /
    # ``get_queryset`` round-trip and use ``resolve_parent`` directly.
    resolve_parent._bypass_get_queryset = True  # type: ignore[attr-defined]

    def resolve_my_permissions(self, info) -> list[str]:
        """Permissions are inherited from the parent corpus.

        ``CorpusFolder`` rows never carry guardian permission rows (see
        ``opencontractserver/corpuses/models.py`` ``CorpusFolder`` class
        docstring), so the default
        :meth:`AnnotatePermissionsForReadMixin.resolve_my_permissions`
        would burn two empty ``.filter()`` queries per folder against
        ``corpusfolderuserobjectpermission_set`` and
        ``corpusfoldergroupobjectpermission_set`` — a ``2N`` fan-out on the
        folder-list view. Resolve once per ``(corpus, user)`` per request
        by delegating to the parent corpus's resolver and translating the
        permission strings.
        """
        context = info.context
        user = getattr(context, "user", None)
        if user is None or not is_authenticated_user(user):
            # Anonymous users get ``read_corpusfolder`` whenever the
            # *corpus* is public OR the folder is explicitly public.
            # ``CorpusFolder.user_can`` delegates to the corpus, so the
            # corpus's public-read grant authorises folder access; the
            # permissions list must mirror that decision (otherwise the
            # frontend disables folder-read UI for an anon viewer of a
            # public corpus). The mixin's bare ``self.is_public`` branch
            # would only consult the folder row.
            if self.corpus.is_public or self.is_public:
                return ["read_corpusfolder"]
            return []

        cache_attr = f"_corpus_folder_perms_{self.corpus_id}_{user.id}"
        cached = getattr(context, cache_attr, None)
        if cached is None:
            corpus_perms = AnnotatePermissionsForReadMixin.resolve_my_permissions(
                self.corpus, info
            )
            # corpus_perms entries end in ``_corpus`` (e.g. ``read_corpus``);
            # rewrite to the folder model name so the API contract matches
            # what the AnnotatePermissionsForReadMixin would have returned.
            cached = [
                (
                    f"{perm[: -len('corpus')]}corpusfolder"
                    if perm.endswith("_corpus")
                    else perm
                )
                for perm in corpus_perms
            ]
            setattr(context, cache_attr, cached)

        if self.is_public and "read_corpusfolder" not in cached:
            return [*cached, "read_corpusfolder"]
        return list(cached)

    def resolve_is_published(self, info) -> bool:
        """``CorpusFolder`` rows never carry guardian permission rows, so the
        ``DEFAULT_PERMISSIONS_GROUP`` is never granted on a folder; the
        answer is always ``False``. Override the mixin's
        :meth:`resolve_is_published` to skip the per-folder
        ``get_groups_with_perms`` + ``.filter().count()`` queries it would
        otherwise run on the folder-list view.
        """
        return False

    class Meta:
        model = CorpusFolder
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        """Filter folders to only those the user can see (via corpus permissions)."""
        # Chain ``visible_to_user`` on the incoming queryset/manager so the
        # filter is a single ``WHERE`` expression tree (no ``pk__in``
        # subquery over the full table).
        return BaseService.filter_visible_qs(
            queryset, info.context.user, request=info.context
        )


class CorpusType(AnnotatePermissionsForReadMixin, DjangoObjectType):
    all_annotation_summaries = graphene.List(
        AnnotationType,
        analysis_id=graphene.ID(),
        label_types=graphene.List(LabelTypeEnum),
    )

    # Explicit documents field to use custom resolver via DocumentPath
    # This is necessary because Corpus model no longer has M2M documents field
    # (corpus isolation moved to DocumentPath-based relationships)
    documents = relay.ConnectionField(
        DocumentTypeConnection, description="Documents in this corpus via DocumentPath"
    )

    def resolve_documents(self, info, **kwargs) -> Any:
        """
        Custom resolver for documents field that uses DocumentPath.
        Returns documents with active paths in this corpus, filtered by
        document-level visibility.

        Delegates to
        ``CorpusDocumentService.get_corpus_documents_visible_to_user``, which
        enforces the MIN-permission semantic::

            Effective Permission = MIN(document_permission, corpus_permission)

        A private document in a public (or shared) corpus stays hidden from
        users without document-level access — keeping this user-facing
        GraphQL field aligned with the permission model documented in
        ``CLAUDE.md`` rather than the corpus-as-gate semantic that
        pipeline-facing callers (MCP, discovery) use. See issue #1682.

        CAML/markdown files are included here since this resolver serves
        corpus views that need to display the article landing page.
        """
        from django.contrib.auth.models import AnonymousUser

        from opencontractserver.corpuses.services import CorpusDocumentService

        user = getattr(info.context, "user", None) or AnonymousUser()
        return CorpusDocumentService.get_corpus_documents_visible_to_user(
            user, self, include_caml=True, request=info.context
        )

    def resolve_annotations(self, info) -> Any:
        """
        Custom resolver for annotations field that properly computes permissions.
        Uses AnnotationService to ensure permission flags are set.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.annotations.services import AnnotationService

        user = getattr(info.context, "user", None)

        # Get all document IDs in this corpus via DocumentPath. Corpus READ is
        # already gated by the parent query that resolved ``self`` — see the
        # equivalent note in ``resolve_documents`` above. The internal helper
        # avoids the deprecated user-facing wrapper's runtime warning.
        document_ids = self._get_active_documents().values_list("id", flat=True)

        # Collect annotations for all documents with proper permission computation
        all_annotations = Annotation.objects.none()
        for doc_id in document_ids:
            annotations = AnnotationService.get_document_annotations(
                document_id=doc_id, user=user, corpus_id=self.id
            )
            all_annotations = all_annotations | annotations

        return all_annotations.distinct()

    def resolve_all_annotation_summaries(self, info, **kwargs) -> Any:

        analysis_id = kwargs.get("analysis_id", None)
        label_types = kwargs.get("label_types", None)

        annotation_set = self.annotations.all()

        if label_types and isinstance(label_types, list):
            logger.info(f"Filter to label_types: {label_types}")
            annotation_set = annotation_set.filter(
                annotation_label__label_type__in=[
                    label_type.value for label_type in label_types
                ]
            )

        if analysis_id:
            try:
                analysis_pk = from_global_id(analysis_id)[1]
                annotation_set = annotation_set.filter(analysis_id=analysis_pk)
            except Exception as e:
                logger.warning(
                    f"Failed resolving analysis pk for corpus {self.id} with input graphene id"
                    f" {analysis_id}: {e}"
                )

        return annotation_set

    applied_analyzer_ids = graphene.List(graphene.String)

    def resolve_applied_analyzer_ids(self, info) -> Any:
        return list(
            self.analyses.all().values_list("analyzer_id", flat=True).distinct()
        )

    def resolve_icon(self, info) -> Any:
        return "" if not self.icon else info.context.build_absolute_uri(self.icon.url)

    # File link resolver for markdown description — reads through the
    # canonical Readme.CAML Document body (the source of truth for the
    # corpus's description). See spec §4.5.
    def resolve_md_description(self, info) -> Any:
        """Resolve to the URL of the Readme.CAML Document's body file.

        After the canonical-CAML refactor, the corpus's description lives
        in the Readme.CAML Document (title='Readme.CAML',
        file_type='text/markdown'). The denormalized
        ``readme_caml_document`` FK + ``with_readme_caml_doc`` queryset
        helper let us return the URL without a per-row Document fetch on
        list queries.

        Returns ``None`` when no CAML doc exists for the corpus.
        """
        doc = self.readme_caml_document
        if doc is None:
            return None
        file_field = doc.txt_extract_file
        if not file_field or not file_field.name:
            return None
        if info is None or getattr(info, "context", None) is None:
            return file_field.url
        return info.context.build_absolute_uri(file_field.url)

    readme_caml_document = graphene.Field(
        "config.graphql.document_types.DocumentType",
        description=(
            "The corpus's canonical Readme.CAML Document — the source of "
            "truth for the rich description. Use this for revision history, "
            "permissions, and direct content access. The mdDescription "
            "string field exposes the same body as a file URL."
        ),
    )

    def resolve_readme_caml_document(self, info) -> Any:
        """Optional rich-object access to the canonical Readme.CAML doc.

        Existing clients use mdDescription (URL) or descriptionPreview
        (text). New clients that need revision history or any other
        Document field can fetch it here. Resolves from the cached FK
        — see spec §4.5.
        """
        return self.readme_caml_document

    # Description revision history: each entry is a sibling Document on
    # the corpus's Readme.CAML version_tree. The resolver shape preserves
    # the legacy ``CorpusDescriptionRevision`` API so the frontend
    # revision-history viewer renders without changes.
    description_revisions = graphene.List(
        lambda: CorpusDescriptionRevisionType,
        description=(
            "Revision history for the corpus description. After the "
            "canonical-CAML refactor each entry is a sibling Document on "
            "the corpus's Readme.CAML version_tree, newest first. The "
            "field shape preserves the legacy CorpusDescriptionRevision "
            "API so the frontend revision-history viewer renders without "
            "changes."
        ),
    )

    def resolve_description_revisions(self, info) -> Any:
        """List Readme.CAML version-tree siblings as revisions, newest first.

        Resolves via the cached ``readme_caml_document`` FK and the
        Document ``version_tree_id``; returns ``[]`` when the corpus has
        no canonical CAML document yet. Filtering on the canonical title
        + markdown mime is defensive — a Readme.CAML version tree only
        ever contains Readme.CAML siblings — and keeps the contract
        explicit.

        Annotates each sibling with ``_version_index`` (1-based, oldest
        first) so ``CorpusDescriptionRevisionType.resolve_version`` can
        read the position off the instance instead of re-querying the
        full tree per row (avoids an N+1 storm on the revisions modal).
        """
        if self.readme_caml_document_id is None:
            return []
        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
            MARKDOWN_MIME_TYPE,
        )
        from opencontractserver.documents.models import Document

        tree_id = self.readme_caml_document.version_tree_id
        oldest_first = list(
            Document.objects.filter(
                version_tree_id=tree_id,
                title=CAML_ARTICLE_TITLE,
                file_type=MARKDOWN_MIME_TYPE,
            )
            .select_related("creator")
            .order_by("created", "pk")
        )
        for index, doc in enumerate(oldest_first, start=1):
            doc._version_index = index
        return list(reversed(oldest_first))

    # Folder structure
    folders = graphene.List(
        CorpusFolderType, description="All folders in this corpus (flat list)"
    )

    def resolve_folders(self, info) -> Any:
        """Get all folders in this corpus with service-layer visibility filtering."""
        return BaseService.filter_visible_qs(
            self.folders, info.context.user, request=info.context
        )

    # Engagement metrics (Epic #565)
    engagement_metrics = graphene.Field(CorpusEngagementMetricsType)

    def resolve_engagement_metrics(self, info) -> Any:
        """
        Resolve engagement metrics for this corpus.

        Returns None if metrics haven't been calculated yet.

        Epic: #565 - Corpus Engagement Metrics & Analytics
        Issue: #568 - Create GraphQL queries for engagement metrics and leaderboards
        """
        try:
            return self.engagement_metrics
        except CorpusEngagementMetrics.DoesNotExist:
            return None

    # Agent memory privacy warning
    memory_active_warning = graphene.String(
        description=(
            "When memory is enabled, returns a privacy notice explaining "
            "that conversation patterns may be stored. Null when disabled."
        ),
    )

    def resolve_memory_active_warning(self, info) -> Any:
        if not self.memory_enabled:
            return None
        return (
            "Agent memory is enabled for this corpus. Generalised patterns "
            "from conversations (not specific content) may be distilled into "
            "the corpus memory document. Review the memory document in your "
            "corpus to see what has been recorded."
        )

    # Categories
    categories = graphene.List(lambda: CorpusCategoryType)

    def resolve_categories(self, info) -> Any:
        """Get all categories assigned to this corpus."""
        return self.categories.all()

    # Efficient document count field - uses annotation from resolver
    document_count = graphene.Int(
        description="Count of active documents in this corpus (optimized)"
    )

    def resolve_document_count(self, info) -> Any:
        """
        Return document count from annotation or fallback to model method.

        For list queries, resolve_corpuses annotates _document_count.
        For single corpus queries, falls back to model.document_count().
        """
        if hasattr(self, "_document_count") and self._document_count is not None:
            return self._document_count
        return self.document_count()

    # Voting — denormalized counts live directly on the model so they
    # serialize for free through the DjangoObjectType field auto-discovery.
    # ``my_vote`` requires a custom resolver because the answer depends on
    # the calling user (or the anonymous session key for guest voters).
    my_vote = graphene.String(
        description=(
            "Current viewer's vote on this corpus: 'UPVOTE', 'DOWNVOTE', or null. "
            "Resolved against the authenticated user when present, otherwise "
            "against the Django session id for guest voters."
        )
    )

    def resolve_my_vote(self, info) -> str | None:
        """Return the viewer's vote on this corpus, if any.

        Prefer the ``_viewer_vote`` annotation that ``get_queryset`` attaches
        to every row of a list query — that's a single ``Subquery`` per page
        instead of N per-row lookups. Fall back to a per-row service call
        only when the annotation isn't present (e.g. a nested fetch path
        that bypasses our list resolver). The Subquery returns ``None`` for
        rows the viewer hasn't voted on; ``hasattr`` distinguishes "no
        annotation attached" from "annotated with no vote".
        """
        if hasattr(self, "_viewer_vote"):
            annotated = self._viewer_vote
            return annotated.upper() if annotated else None

        from opencontractserver.corpuses.services import CorpusVoteService

        request = info.context
        user = getattr(request, "user", None)
        session_key = None
        session = getattr(request, "session", None)
        if session is not None:
            session_key = session.session_key

        vote_type = CorpusVoteService.get_user_vote_type(
            user, self, session_key=session_key
        )
        return vote_type.upper() if vote_type else None

    # Efficient annotation count field - uses annotation from resolver
    annotation_count = graphene.Int(
        description="Count of annotations in this corpus (optimized)"
    )

    def resolve_annotation_count(self, info) -> Any:
        """
        Return annotation count from annotation or fallback to database query.

        For list queries, resolve_corpuses annotates _annotation_count.
        For single corpus queries, falls back to counting via DocumentPath.
        """
        if hasattr(self, "_annotation_count") and self._annotation_count is not None:
            return self._annotation_count
        from opencontractserver.documents.models import DocumentPath

        doc_ids = DocumentPath.objects.filter(
            corpus=self, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)
        return Annotation.objects.filter(document_id__in=doc_ids).count()

    def resolve_label_set(self, info) -> Any:
        """
        Return label_set with count annotations copied from corpus.

        When resolve_corpuses annotates label counts on the Corpus, we need
        to copy those annotations to the label_set instance so that its
        count resolvers can use them instead of hitting the database.
        """
        if self.label_set is None:
            return None

        # Copy annotated counts to the label_set instance
        if hasattr(self, "_label_doc_count"):
            self.label_set._doc_label_count = self._label_doc_count
        if hasattr(self, "_label_span_count"):
            self.label_set._span_label_count = self._label_span_count
        if hasattr(self, "_label_token_count"):
            self.label_set._token_label_count = self._label_token_count

        return self.label_set

    class Meta:
        model = Corpus
        interfaces = [relay.Node]
        connection_class = CountableConnection

    @classmethod
    def get_queryset(cls, queryset, info) -> Any:
        # Chain ``visible_to_user`` on the incoming queryset/manager so the
        # filter is a single ``WHERE`` expression tree (no ``pk__in``
        # subquery over the full table).
        request = info.context
        user = getattr(request, "user", None)
        visible_qs = BaseService.filter_visible_qs(queryset, user, request=request)
        # Prefetch the Readme.CAML FK so mdDescription / readmeCamlDocument
        # resolve in O(1) per row. See spec §4.5.
        from opencontractserver.corpuses.services.corpus_documents import (
            CorpusDocumentService,
        )

        visible_qs = CorpusDocumentService.with_readme_caml_doc(visible_qs)

        # Annotate the viewer's vote in one Subquery per page so
        # ``resolve_my_vote`` doesn't fire N queries (one per corpus card)
        # on the public list view. Authenticated viewers key on creator;
        # anonymous viewers key on the Django session key — both branches
        # mirror ``CorpusVoteService.get_user_vote_type``.
        is_auth = is_authenticated_user(user)
        if is_auth:
            viewer_filter = Q(creator=user, session_key__isnull=True)
        else:
            session = getattr(request, "session", None)
            session_key = getattr(session, "session_key", None) if session else None
            if not session_key:
                # No session => no anonymous votes possible; skip the
                # annotation to avoid attaching a column of NULLs.
                return visible_qs
            viewer_filter = Q(session_key=session_key, creator__isnull=True)

        viewer_vote_subquery = CorpusVote.objects.filter(
            viewer_filter, corpus=OuterRef("pk")
        ).values("vote_type")[:1]
        return visible_qs.annotate(_viewer_vote=Subquery(viewer_vote_subquery))

    @classmethod
    def get_node(cls, info, id) -> Any:
        """Cache + visibility-check FK/relay-node ``Corpus`` lookups.

        ``Corpus`` is a ``with_tree_fields=True`` ``TreeNode``, so every
        ``Corpus.objects.get(pk=...)`` emits a recursive ``WITH __rank_table``
        CTE. Graphene's default ``DjangoObjectType.get_node`` fires that CTE
        once per FK-via-Node access AND does an unprotected lookup that
        bypasses visibility. This override caches the result on
        ``info.context._corpus_node_cache`` and routes the fetch through
        ``BaseService.get_or_none`` so visibility + the Tier-2 permission
        cache apply (also required by the ``opencontracts.E001`` system check).
        """
        try:
            pk = int(id)
        except (TypeError, ValueError):
            return None

        cache = getattr(info.context, "_corpus_node_cache", None)
        if cache is None:
            cache = {}
            try:
                info.context._corpus_node_cache = cache
            except AttributeError:
                # ``info.context`` may be frozen in some test contexts; skip
                # caching but still apply visibility.
                cache = None

        if cache is not None and pk in cache:
            return cache[pk]

        corpus = BaseService.get_or_none(
            Corpus, pk, info.context.user, request=info.context
        )

        if cache is not None:
            cache[pk] = corpus
        return corpus


class CorpusStatsType(graphene.ObjectType):
    total_docs = graphene.Int()
    total_annotations = graphene.Int()
    total_comments = graphene.Int()
    total_analyses = graphene.Int()
    total_extracts = graphene.Int()
    total_threads = graphene.Int()
    total_chats = graphene.Int()
    total_relationships = graphene.Int()


class CorpusFilterCountsType(graphene.ObjectType):
    """Counts of corpuses visible to the user, broken down by tab filter.

    Each count respects guardian permissions (matches BaseService.filter_visible(Corpus, user))
    so tab badges in the corpus list view stay accurate without paginating every
    page on the client.
    """

    all = graphene.Int(required=True)
    mine = graphene.Int(required=True)
    shared = graphene.Int(required=True)
    public = graphene.Int(required=True)


# ---------------- CorpusDescriptionRevisionType ----------------
class CorpusDescriptionRevisionType(graphene.ObjectType):
    """Backwards-compatible facade over a Readme.CAML version-tree sibling.

    The legacy ``CorpusDescriptionRevision`` model was dropped in
    migration 0055. The GraphQL shape is preserved by mapping each
    Document sibling's metadata onto the historical fields, so the
    frontend revision-history viewer renders without changes. The
    instance bound to each resolver is a
    ``opencontractserver.documents.models.Document`` row (a Readme.CAML
    version-tree sibling), NOT a ``CorpusDescriptionRevision``.

    The legacy ``diff`` field is dropped: clients that need a unified
    diff compute it on the fly from successive ``snapshot`` values via
    ``difflib`` rather than reading a pre-stored payload. Queries that
    still reference ``diff`` will fail GraphQL validation — remove it
    from the frontend query to eliminate the field entirely.

    Spec: ``docs/superpowers/specs/2026-05-27-canonical-caml-description-refactor-design.md`` §4.5
    """

    id = graphene.ID(required=True)
    version = graphene.Int()
    author = graphene.Field("config.graphql.graphene_types.UserType")
    snapshot = graphene.String()
    created = graphene.DateTime()

    def resolve_id(self, info) -> Any:
        """Document primary key — used as the revision identity."""
        return self.pk

    def resolve_version(self, info) -> Any:
        """1-indexed position within the version_tree, oldest first.

        Mirrors the legacy ``CorpusDescriptionRevision.version`` counter
        so the frontend's "Version N" header keeps lining up. Reads the
        index pre-computed by the list resolver
        (``CorpusType.resolve_description_revisions``); falls back to a
        per-row query when the instance is resolved outside that list
        path (e.g. node(id:) — uncommon for this facade type).
        """
        precomputed = getattr(self, "_version_index", None)
        if precomputed is not None:
            return precomputed

        from opencontractserver.constants.document_processing import (
            CAML_ARTICLE_TITLE,
            MARKDOWN_MIME_TYPE,
        )
        from opencontractserver.documents.models import Document

        ordered_ids = list(
            Document.objects.filter(
                version_tree_id=self.version_tree_id,
                title=CAML_ARTICLE_TITLE,
                file_type=MARKDOWN_MIME_TYPE,
            )
            .order_by("created", "pk")
            .values_list("pk", flat=True)
        )
        try:
            return ordered_ids.index(self.pk) + 1
        except ValueError:
            return None

    def resolve_author(self, info) -> Any:
        """Document creator — historical revisions used ``author``."""
        return self.creator

    def resolve_snapshot(self, info) -> Any:
        """Read the Document's txt_extract_file body on demand.

        Each Readme.CAML version-tree sibling stores the full markdown
        in ``txt_extract_file``; the legacy ``snapshot`` column on
        ``CorpusDescriptionRevision`` carried the same content, so this
        is a 1:1 swap for the frontend rev viewer. Reads go through the
        shared ``read_caml_body`` helper (promoted from a private helper
        in ``corpuses/signals.py`` to ``description_cache.py`` for DRY) so the I/O
        contract — text-mode then binary-fallback — matches the
        cache-refresh signal handler exactly.

        Performance (accepted trade-off): each call opens one
        ``txt_extract_file`` blob, so requesting ``snapshot`` for every
        revision in one query is N storage round-trips. Pre-reading the
        bodies in the list resolver would not reduce that count (object
        storage has no batch read), so the effective fix is to fetch
        ``snapshot`` only on a single-revision drill-down rather than in
        the list query. The list path is the modal-only revision viewer,
        so the N reads
        are bounded by the revision count a human is browsing.
        """
        from opencontractserver.corpuses.services.description_cache import (
            read_caml_body,
        )

        return read_caml_body(self)

    def resolve_created(self, info) -> Any:
        """Document creation timestamp — historical revisions used the
        same field name."""
        return self.created
