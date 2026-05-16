"""Coverage-gap tests for the Phase A permission centralisation surface.

This module is the companion to ``test_authorization_invariants.py``: the
invariant file pins the ``user_can ↔ visible_to_user`` equivalence under a
small user matrix, while this file walks the leaf branches of every per-model
``user_can`` override, every ``QuerySet.visible_to_user`` fallback path, and
the new ``permission_cache`` machinery. Two motivations:

1.  Patch-coverage for PR #1663 (the codecov report flagged
    ``shared/Managers.py``, ``shared/QuerySets.py``, ``permission_cache.py``
    and ``utils/permissioning.py``).
2.  Address the gaps Claude flagged on the same PR:
    - ``created_by_extract`` privacy recursion branch in ``AnnotationManager``
      was untested (only ``created_by_analysis`` was).
    - ``RelationshipManager`` access-widening case (stranger with doc+corpus
      READ now sees the relationship) was untested.
    - Shim ``user_has_permission_for_obj`` should raise ``TypeError`` —
      not bare ``AttributeError`` — when the model's manager hasn't yet
      been migrated.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase, TransactionTestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Note,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.shared.permission_cache import (
    MISS,
    cached_user_can,
    permission_cache_scope,
    store_user_can,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


# ---------------------------------------------------------------------------
# permission_cache.py
# ---------------------------------------------------------------------------


class PermissionCacheMachineryTestCase(SimpleTestCase):
    """Direct unit tests for the request-scoped permission cache primitives.

    ``permission_cache.py`` is dormant in Phase A (no production caller enters
    the scope yet), so the invariant test file never touches it. We exercise
    the API surface here so codecov can see the scope/get/set bodies and a
    future Phase B activation has a regression guard for the key shape.
    """

    # 6-tuple matching ``cached_user_can``'s positional signature
    # (user_id, app_label, model_name, pk, permission, include_group_permissions).
    # ``store_user_can`` takes the same 6 plus a 7th ``result`` arg; spelling
    # ``result`` as a kwarg with ``*KEY_ARGS`` confuses mypy (it can't infer
    # the tuple length), so we wrap a helper instead.
    KEY_ARGS: tuple[Any, ...] = (
        42,  # user_id
        "documents",  # app_label
        "document",  # model_name
        7,  # pk
        "read",  # permission value
        True,  # include_group_permissions
    )

    @staticmethod
    def _store(key: tuple[Any, ...], result: bool) -> None:
        store_user_can(key[0], key[1], key[2], key[3], key[4], key[5], result)

    def test_cached_user_can_returns_miss_without_scope(self) -> None:
        """Outside ``permission_cache_scope`` every lookup is a cache MISS."""
        self.assertIs(cached_user_can(*self.KEY_ARGS), MISS)

    def test_store_is_noop_without_scope(self) -> None:
        """``store_user_can`` outside a scope must not raise and must not
        leak state into a later scope."""
        self._store(self.KEY_ARGS, True)
        with permission_cache_scope():
            self.assertIs(cached_user_can(*self.KEY_ARGS), MISS)

    def test_scope_round_trip_hits(self) -> None:
        """Inside the scope, ``store_user_can`` + ``cached_user_can`` round-trips."""
        with permission_cache_scope():
            self.assertIs(cached_user_can(*self.KEY_ARGS), MISS)
            self._store(self.KEY_ARGS, True)
            self.assertIs(cached_user_can(*self.KEY_ARGS), True)
            # Cached ``False`` is a legitimate hit — must not be confused
            # with the MISS sentinel.
            other_key: tuple[Any, ...] = (43, "documents", "document", 7, "read", True)
            self._store(other_key, False)
            self.assertIs(cached_user_can(*other_key), False)

    def test_scope_does_not_leak_after_exit(self) -> None:
        """After exiting the scope the ContextVar resets to ``None``."""
        with permission_cache_scope():
            self._store(self.KEY_ARGS, True)
        self.assertIs(cached_user_can(*self.KEY_ARGS), MISS)

    def test_pk_none_is_skipped_on_read_and_write(self) -> None:
        """Unsaved instances (pk=None) cannot be uniquely keyed — both
        read and write are no-ops even inside an active scope."""
        none_key: tuple[Any, ...] = (42, "documents", "document", None, "read", True)
        with permission_cache_scope():
            self._store(none_key, True)
            self.assertIs(cached_user_can(*none_key), MISS)

    def test_nested_scope_uses_fresh_dict(self) -> None:
        """Nested ``permission_cache_scope`` allocates a fresh empty dict
        (documented contract — nesting offers no caching benefit yet)."""
        with permission_cache_scope():
            self._store(self.KEY_ARGS, True)
            self.assertIs(cached_user_can(*self.KEY_ARGS), True)
            with permission_cache_scope():
                # Inner scope is a fresh empty dict.
                self.assertIs(cached_user_can(*self.KEY_ARGS), MISS)
                self._store(self.KEY_ARGS, False)
                self.assertIs(cached_user_can(*self.KEY_ARGS), False)
            # Outer scope's value is restored on inner exit.
            self.assertIs(cached_user_can(*self.KEY_ARGS), True)

    def test_include_group_permissions_is_part_of_key(self) -> None:
        """Flipping ``include_group_permissions`` MUST be a distinct cache key."""
        with permission_cache_scope():
            store_user_can(42, "documents", "document", 7, "read", True, True)
            self.assertIs(
                cached_user_can(42, "documents", "document", 7, "read", False),
                MISS,
            )


# ---------------------------------------------------------------------------
# Shim (utils/permissioning.user_has_permission_for_obj)
# ---------------------------------------------------------------------------


class _DummyDefaultManager:
    """Stand-in for a Django manager lacking ``user_can`` (Phase A migration gap)."""


class _DummyInstance:
    """Stand-in for a Django model instance whose manager lacks ``user_can``."""

    _default_manager = _DummyDefaultManager()


class ShimTypeErrorGuardTestCase(TransactionTestCase):
    """Pin Claude review item #2: the deprecation shim must raise
    ``TypeError`` (not bare ``AttributeError``) when the instance's
    ``_default_manager`` hasn't implemented ``user_can`` yet — the
    Phase A → Phase B migration is incremental, so the error message
    must be actionable."""

    def setUp(self) -> None:
        self.creator = User.objects.create_user(
            username="shim_typerror_creator", email="shim@cov.test", password="x"
        )

    def test_shim_raises_typeerror_for_unmigrated_manager(self) -> None:
        import warnings

        from opencontractserver.utils.permissioning import (
            user_has_permission_for_obj,
        )

        with warnings.catch_warnings():
            # We expect the DeprecationWarning and the TypeError — the
            # warning fires before the manager check.
            warnings.simplefilter("ignore", DeprecationWarning)
            with self.assertRaises(TypeError) as cm:
                # mypy: ``user_has_permission_for_obj`` is typed against
                # ``django.db.models.Model``; the dummy is a stand-in
                # specifically to exercise the missing-``user_can`` guard.
                user_has_permission_for_obj(
                    self.creator,
                    _DummyInstance(),  # type: ignore[arg-type]
                    PermissionTypes.READ,
                )
        message = str(cm.exception)
        self.assertIn("user_can", message)
        self.assertIn("_DummyInstance", message)
        self.assertIn("Phase A", message)

    def test_shim_returns_false_for_unknown_user_id(self) -> None:
        """Pin the ``User.DoesNotExist`` legacy branch — the shim must
        return ``False`` (not raise) when an int id doesn't resolve. The
        legacy behaviour raised; the shim deliberately swallows so no
        caller has to wrap it in try/except."""
        import warnings

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.utils.permissioning import (
            user_has_permission_for_obj,
        )

        corpus = Corpus.objects.create(
            title="Shim NoSuchUser", creator=self.creator, is_public=False
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            result = user_has_permission_for_obj(
                999_999_999, corpus, PermissionTypes.READ
            )
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# AnnotationManager.user_can — non-default leaf branches
# ---------------------------------------------------------------------------


class AnnotationUserCanLeafBranchesTestCase(TransactionTestCase):
    """Walk the AnnotationManager.user_can branches that the matrix
    invariant test doesn't exercise: ``created_by_extract`` privacy recursion
    (Claude review item #4 — the partner of the ``created_by_analysis``
    branch already pinned by ``test_privacy_recursion_*``), ``document_id
    is None`` denial for non-READ, every permission code beyond READ, the
    int/str user-id resolver paths, and the PUBLISH/PERMISSION → False
    fallback (these constants are defined for other models but undefined
    on annotations)."""

    def setUp(self) -> None:
        from opencontractserver.analyzer.models import Analyzer
        from opencontractserver.extracts.models import Extract, Fieldset

        self.creator = User.objects.create_user(
            username="ann_leaf_creator", email="alc@cov.test", password="x"
        )
        self.reader = User.objects.create_user(
            username="ann_leaf_reader", email="alr@cov.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="ann_leaf_stranger", email="als@cov.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="Ann Leaf Corpus", creator=self.creator, is_public=False
        )
        self.doc = Document.objects.create(
            title="Ann Leaf Doc", creator=self.creator, is_public=False
        )
        set_permissions_for_obj_to_user(
            self.reader, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.reader, self.doc, [PermissionTypes.READ])

        self.token_label = AnnotationLabel.objects.create(
            text="alt", label_type="TOKEN_LABEL", creator=self.creator
        )

        self.fieldset = Fieldset.objects.create(
            name="Leaf Fieldset", creator=self.creator
        )
        self.extract = Extract.objects.create(
            name="Leaf Extract",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.creator,
        )
        self.via_extract = Annotation.objects.create(
            raw_text="via_extract",
            json={"x": 1},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.doc,
            corpus=self.corpus,
            created_by_extract=self.extract,
        )

        # An analysis-rooted annotation, for the partner branch.
        self.analyzer = Analyzer.objects.create(
            id="leaf_analyzer",
            description="x",
            creator=self.creator,
            task_name="opencontractserver.tasks.noop",
        )
        from opencontractserver.analyzer.models import Analysis

        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer,
            analyzed_corpus=self.corpus,
            creator=self.creator,
        )
        self.via_analysis = Annotation.objects.create(
            raw_text="via_analysis",
            json={"x": 2},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.doc,
            corpus=self.corpus,
            created_by_analysis=self.analysis,
        )

        # Plain non-structural annotation for the permission-code matrix.
        self.plain = Annotation.objects.create(
            raw_text="plain",
            json={"x": 3},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
            document=self.doc,
            corpus=self.corpus,
        )

    def test_created_by_extract_privacy_recursion_honors_creator(self) -> None:
        """Creator of the extract + annotation can READ the private
        annotation — the partner test to
        ``test_privacy_recursion_honors_creator_on_source_analysis``."""
        self.assertTrue(self.via_extract.user_can(self.creator, PermissionTypes.READ))

    def test_created_by_extract_privacy_recursion_blocks_other_users(self) -> None:
        """A user with doc+corpus READ but no extract access cannot READ
        a private-via-extract annotation."""
        self.assertFalse(self.via_extract.user_can(self.reader, PermissionTypes.READ))

    def test_privacy_recursion_with_deleted_analysis_returns_false(self) -> None:
        """When the source Analysis row is deleted, the recursion path
        treats the annotation as private and denies all non-creator
        access — the safe failure mode, but worth pinning so a future
        refactor that "fixes" the orphan to grant access cannot slip in
        silently.

        The DB enforces the analysis FK, so a true orphan id cannot be
        persisted. We simulate the descriptor-returns-None outcome the
        manager actually sees by setting the cached relation to ``None``
        on a real instance whose ``created_by_analysis_id`` is non-null;
        this is the in-memory state Django produces when the FK row has
        been deleted under a stale reference, and is exactly what
        ``AnnotationManager.user_can`` checks before denying.
        """
        ann = self.via_analysis
        # Force the FK descriptor to think the source has been removed
        # while ``created_by_analysis_id`` remains non-null. Django uses
        # the field's cache slot at ``<field>.cache_name`` to short-
        # circuit DB hits — populating it with ``None`` makes the
        # descriptor return ``None`` without a query.
        from django.db.models.fields.related_descriptors import (
            ForwardManyToOneDescriptor,
        )

        descriptor = type(ann).__dict__["created_by_analysis"]
        assert isinstance(descriptor, ForwardManyToOneDescriptor)
        ann._state.fields_cache[descriptor.field.name] = None
        self.assertIsNotNone(ann.created_by_analysis_id)
        self.assertIsNone(ann.created_by_analysis)

        # Even the annotation's own creator is denied — the orphan source
        # is treated as private and there's no Analysis row left to
        # honour the creator-grant short-circuit on.
        self.assertFalse(ann.user_can(self.creator, PermissionTypes.READ))
        # A reader with doc+corpus grants is similarly denied.
        self.assertFalse(ann.user_can(self.reader, PermissionTypes.READ))

    def test_str_and_int_user_id_inputs_on_annotation(self) -> None:
        """int and str user ids resolve identically to the User instance."""
        self.assertTrue(self.plain.user_can(self.creator.id, PermissionTypes.READ))
        self.assertTrue(self.plain.user_can(str(self.creator.id), PermissionTypes.READ))
        # Unknown id → False (not raise).
        self.assertFalse(self.plain.user_can(999_999_999, PermissionTypes.READ))

    def test_anonymous_non_read_is_denied(self) -> None:
        """Anonymous users cannot do anything but READ — non-READ branches
        return False before the visible_to_user fallback runs."""
        anon = AnonymousUser()
        for perm in (
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.CREATE,
            PermissionTypes.COMMENT,
        ):
            self.assertFalse(
                self.plain.user_can(anon, perm),
                f"anonymous granted {perm} on annotation — leak!",
            )

    def test_permission_matrix_for_creator(self) -> None:
        """The creator passes every permission code that ``Annotation``
        recognises (READ/CREATE/UPDATE/DELETE/EDIT/COMMENT/CRUD/ALL)
        thanks to the creator short-circuit in
        ``_compute_effective_permissions``."""
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.CREATE,
            PermissionTypes.UPDATE,
            PermissionTypes.EDIT,
            PermissionTypes.DELETE,
            PermissionTypes.COMMENT,
            PermissionTypes.CRUD,
            PermissionTypes.ALL,
        ):
            self.assertTrue(
                self.plain.user_can(self.creator, perm),
                f"creator denied {perm} on their own annotation",
            )

    def test_publish_and_permission_codes_are_false_for_annotation(self) -> None:
        """Annotations don't recognise PUBLISH/PERMISSION — both fall
        through to ``return False`` at the end of
        ``AnnotationManager.user_can``. Pinning this prevents an
        accidental silent True from a future branch reorder."""
        for perm in (PermissionTypes.PUBLISH, PermissionTypes.PERMISSION):
            self.assertFalse(
                self.plain.user_can(self.creator, perm),
                f"annotation unexpectedly granted {perm} — does the model "
                f"now support this permission?",
            )

    def test_document_id_none_non_read_denied(self) -> None:
        """Annotations whose ``document_id`` is NULL (only reachable via
        the structural-set route) cannot accept non-READ permissions —
        the manager denies before falling through to the READ-only
        ``visible_to_user`` exists() check."""
        # Spoof a non-saved annotation with no document_id.
        ann = Annotation(
            raw_text="no_doc",
            json={"x": 9},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
        )
        ann.pk = -1  # unsaved sentinel
        # Skip privacy recursion (no analysis/extract).
        self.assertFalse(
            Annotation.objects.user_can(self.creator, ann, PermissionTypes.UPDATE)
        )

    def test_document_id_none_read_falls_through_to_visible_to_user(self) -> None:
        """Annotations whose ``document_id`` is NULL hit the READ
        ``visible_to_user`` fallback rather than the non-READ deny.

        Companion to ``test_document_id_none_non_read_denied`` — pins
        the asymmetry between UPDATE/DELETE/etc. (denied outright) and
        READ (delegated to ``visible_to_user``). A future refactor that
        accidentally collapses both branches into the same denial would
        silently break structural-set READ visibility for orphaned
        annotations — this test makes that regression visible.

        An annotation with no ``document_id`` and no matching structural
        set returns ``False`` from ``visible_to_user`` (no link to a
        readable corpus/document), not from the non-READ deny. The
        ``.exists()`` lookup uses the real DB row so this stays honest.
        """
        # The DB enforces ``annotation_has_single_parent`` — a pure orphan
        # (no document, no corpus, no structural_set) cannot be saved. So
        # we spoof an in-memory row (mirroring the sibling
        # ``test_document_id_none_non_read_denied``); the READ branch is
        # exercised because ``visible_to_user(...).filter(pk=spoof).exists()``
        # naturally returns False against a non-existent pk, which is the
        # same answer the live path would give an outsider on an orphan
        # structural-set row.
        ann = Annotation(
            raw_text="orphan_read",
            json={"x": 10},
            page=1,
            annotation_label=self.token_label,
            creator=self.creator,
        )
        ann.pk = -2  # unsaved sentinel distinct from the non-READ test

        # Stranger hits the visible_to_user fallback and is denied.
        # This proves the READ branch fell through to the
        # ``.exists()`` check rather than the non-READ deny.
        self.assertFalse(
            Annotation.objects.user_can(self.stranger, ann, PermissionTypes.READ)
        )
        # Superuser bypass short-circuits before the fallback (sanity
        # check that branch order intact: superuser precedes the
        # document_id deny + visible_to_user fallback).
        admin = User.objects.create_superuser(
            username="orphan_read_admin",
            email="ora@cov.test",
            password="x",
        )
        self.assertTrue(Annotation.objects.user_can(admin, ann, PermissionTypes.READ))

    def test_stranger_denied_on_private_annotation(self) -> None:
        """A user with no grants on the doc/corpus is denied every code."""
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
            PermissionTypes.CRUD,
            PermissionTypes.ALL,
        ):
            self.assertFalse(
                self.plain.user_can(self.stranger, perm),
                f"stranger granted {perm} on private annotation",
            )


# ---------------------------------------------------------------------------
# RelationshipManager.user_can — access-widening + leaf branches
# ---------------------------------------------------------------------------


class RelationshipUserCanAccessWideningTestCase(TransactionTestCase):
    """Address Claude review item #3: pin the access-widening case for
    ``RelationshipManager.user_can`` — a stranger who has been granted
    READ on BOTH the parent document and the parent corpus now sees the
    relationship (the old ``BaseVisibilityManager`` fallback denied this
    because no ``relationshipuserobjectpermission`` table exists).

    Also exercises the permission-code matrix and the int/str user-id
    resolver paths that the invariant matrix doesn't reach."""

    def setUp(self) -> None:
        self.creator = User.objects.create_user(
            username="rel_widen_creator", email="rwc@cov.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="rel_widen_stranger", email="rws@cov.test", password="x"
        )

        self.corpus = Corpus.objects.create(
            title="Rel Widen Corpus", creator=self.creator, is_public=False
        )
        self.doc = Document.objects.create(
            title="Rel Widen Doc", creator=self.creator, is_public=False
        )
        # The widening grant — stranger gets READ on BOTH doc and corpus.
        set_permissions_for_obj_to_user(
            self.stranger, self.corpus, [PermissionTypes.READ]
        )
        set_permissions_for_obj_to_user(self.stranger, self.doc, [PermissionTypes.READ])

        rel_label = AnnotationLabel.objects.create(
            text="rwl", label_type="RELATIONSHIP_LABEL", creator=self.creator
        )
        self.relationship = Relationship.objects.create(
            relationship_label=rel_label,
            creator=self.creator,
            document=self.doc,
            corpus=self.corpus,
            structural=False,
        )

    def test_stranger_with_doc_and_corpus_grants_can_read_relationship(self) -> None:
        """The Phase A widening: a non-creator user with READ on both
        the parent doc and the parent corpus now sees the relationship."""
        self.assertTrue(
            self.relationship.user_can(self.stranger, PermissionTypes.READ),
            "stranger with doc+corpus READ should now see relationship — "
            "Phase A widening regression",
        )
        # And the queryset filter agrees (the invariant — Claude review #3).
        self.assertTrue(
            Relationship.objects.visible_to_user(self.stranger)
            .filter(pk=self.relationship.pk)
            .exists()
        )

    def test_str_and_int_user_id_inputs_on_relationship(self) -> None:
        self.assertTrue(
            self.relationship.user_can(self.creator.id, PermissionTypes.READ)
        )
        self.assertTrue(
            self.relationship.user_can(str(self.creator.id), PermissionTypes.READ)
        )
        self.assertFalse(self.relationship.user_can(999_999_999, PermissionTypes.READ))

    def test_relationship_permission_matrix_for_creator(self) -> None:
        """Creator passes every permission code the relationship surface
        recognises (READ/UPDATE/DELETE/CREATE/COMMENT/CRUD/ALL)."""
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.CREATE,
            PermissionTypes.UPDATE,
            PermissionTypes.EDIT,
            PermissionTypes.DELETE,
            PermissionTypes.COMMENT,
            PermissionTypes.CRUD,
            PermissionTypes.ALL,
        ):
            self.assertTrue(
                self.relationship.user_can(self.creator, perm),
                f"creator denied {perm} on their own relationship",
            )

    def test_publish_and_permission_codes_are_false_for_relationship(self) -> None:
        for perm in (PermissionTypes.PUBLISH, PermissionTypes.PERMISSION):
            self.assertFalse(
                self.relationship.user_can(self.creator, perm),
                f"relationship unexpectedly granted {perm}",
            )

    def test_anonymous_non_read_is_denied(self) -> None:
        anon = AnonymousUser()
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(self.relationship.user_can(anon, perm))

    def test_relationship_with_no_document_denied_for_authenticated(self) -> None:
        """Non-structural relationship with ``document_id=None``: the
        manager denies before the MIN(doc, corpus) optimiser ever runs.
        The save-time validator forbids creating a doc-less + non-
        structural relationship, but the manager check can still see
        one via in-memory spoofing (e.g. a half-built domain object in
        an importer). Pin the defensive guard."""
        rel_label = AnnotationLabel.objects.create(
            text="rwl_nodoc", label_type="RELATIONSHIP_LABEL", creator=self.creator
        )
        rel = Relationship(
            relationship_label=rel_label,
            creator=self.creator,
            document=None,
            corpus=self.corpus,
            structural=False,
        )
        rel.pk = -1  # unsaved sentinel — only used by user_can's MIN call
        self.assertFalse(
            Relationship.objects.user_can(self.stranger, rel, PermissionTypes.READ)
        )


class RelationshipNonOwnerCreatorTestCase(TransactionTestCase):
    """Pin the creator short-circuit added to ``RelationshipManager.user_can``.

    Addresses the latent invariant violation flagged on PR #1663: a
    user who is granted CREATE on someone else's document/corpus,
    authors a relationship (becoming ``relationship.creator``), and
    then loses their READ grant must still see/manage the relationship
    via the creator path — otherwise ``visible_to_user`` (which has
    ``Q(creator=user)``) and ``user_can(READ)`` (which routed only
    through ``_compute_effective_permissions``) diverge.

    Structural relationships remain read-only even for their creator.
    """

    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            username="rel_owner", email="ro@cov.test", password="x"
        )
        self.contributor = User.objects.create_user(
            username="rel_contrib", email="rc@cov.test", password="x"
        )
        self.corpus = Corpus.objects.create(
            title="Rel Creator Corpus", creator=self.owner, is_public=False
        )
        self.doc = Document.objects.create(
            title="Rel Creator Doc", creator=self.owner, is_public=False
        )
        # Contributor gets transient READ+CREATE on doc+corpus so they
        # can author a relationship; we then revoke the grants to
        # simulate the share-then-revoke sequence.
        for inst in (self.corpus, self.doc):
            set_permissions_for_obj_to_user(
                self.contributor,
                inst,
                [PermissionTypes.READ, PermissionTypes.CREATE],
            )

        rel_label = AnnotationLabel.objects.create(
            text="rlnoc", label_type="RELATIONSHIP_LABEL", creator=self.owner
        )
        self.relationship = Relationship.objects.create(
            relationship_label=rel_label,
            creator=self.contributor,
            document=self.doc,
            corpus=self.corpus,
            structural=False,
        )
        # Revoke the grants — contributor now only has the creator path.
        for inst in (self.corpus, self.doc):
            set_permissions_for_obj_to_user(self.contributor, inst, [])

    def test_creator_keeps_access_after_grants_revoked(self) -> None:
        """The creator-short-circuit branch — without it, the contributor
        would lose READ when the doc/corpus grants were revoked, while
        ``visible_to_user``'s ``Q(creator=user)`` would still surface the
        row. That divergence is the invariant violation Claude flagged."""
        for perm in (
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
        ):
            self.assertTrue(
                self.relationship.user_can(self.contributor, perm),
                f"creator denied {perm} after their doc/corpus grants were "
                "revoked — short-circuit regressed",
            )
        # And the queryset filter agrees (the invariant — same row should
        # appear in both surfaces).
        self.assertTrue(
            Relationship.objects.visible_to_user(self.contributor)
            .filter(pk=self.relationship.pk)
            .exists()
        )

    def test_structural_creator_still_read_only(self) -> None:
        """Structural-write-deny runs *before* the creator short-circuit:
        even the creator can only READ a structural relationship."""
        rel_label = AnnotationLabel.objects.create(
            text="rlnoc_s", label_type="RELATIONSHIP_LABEL", creator=self.owner
        )
        # Re-grant so we can save a fresh structural row, then revoke.
        for inst in (self.corpus, self.doc):
            set_permissions_for_obj_to_user(
                self.contributor,
                inst,
                [PermissionTypes.READ, PermissionTypes.CREATE],
            )
        structural_rel = Relationship.objects.create(
            relationship_label=rel_label,
            creator=self.contributor,
            document=self.doc,
            corpus=self.corpus,
            structural=True,
        )
        for inst in (self.corpus, self.doc):
            set_permissions_for_obj_to_user(self.contributor, inst, [])

        # READ still works (via creator branch).
        self.assertTrue(structural_rel.user_can(self.contributor, PermissionTypes.READ))
        # Writes are denied even though contributor is the creator.
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                structural_rel.user_can(self.contributor, perm),
                f"structural relationship granted {perm} to creator — "
                "structural-write-deny regressed",
            )


class ResolveUserForUserCanInvalidStringTestCase(TransactionTestCase):
    """Cover ``resolve_user_for_user_can``'s ``ValueError`` catch.

    The legacy duplicated bodies caught ``DoesNotExist`` only; a
    non-numeric string (``""``, a GraphQL global id, or any stray
    label) would propagate ``ValueError`` from Django's PK coercion
    up through every per-model ``user_can`` override. The unified
    resolver now treats both as a deny — pinned here so a future
    "let's simplify the resolver" change can't silently re-introduce
    the uncaught exception."""

    def setUp(self) -> None:
        self.creator = User.objects.create_user(
            username="resolve_invalid", email="ri@cov.test", password="x"
        )
        self.doc = Document.objects.create(
            title="Resolve Invalid Doc",
            creator=self.creator,
            is_public=True,
        )
        self.corpus = Corpus.objects.create(
            title="Resolve Invalid Corpus",
            creator=self.creator,
            is_public=True,
        )
        tok_label = AnnotationLabel.objects.create(
            text="ri_tok", label_type="TOKEN_LABEL", creator=self.creator
        )
        self.ann = Annotation.objects.create(
            document=self.doc,
            corpus=self.corpus,
            annotation_label=tok_label,
            raw_text="x",
            json={"x": 1},
            page=1,
            creator=self.creator,
        )

    def test_non_numeric_string_is_denied_not_raised(self) -> None:
        from opencontractserver.shared.user_can_mixin import (
            resolve_user_for_user_can,
        )

        # The resolver itself: returns None instead of raising.
        for bad in ("", "not-a-number", "VXNlcjox"):
            self.assertIsNone(resolve_user_for_user_can(bad))

        # The downstream per-model surfaces deny without raising.
        for bad in ("", "not-a-number", "VXNlcjox"):
            self.assertFalse(
                Annotation.objects.user_can(bad, self.ann, PermissionTypes.READ),
                f"bad user_val {bad!r} should deny, not raise",
            )


# ---------------------------------------------------------------------------
# NoteManager.user_can — anonymous leaf branches and id resolution
# ---------------------------------------------------------------------------


class NoteUserCanAnonymousAndIdResolutionTestCase(TransactionTestCase):
    """Cover the anonymous branch's nested ``is_public`` gates and the
    int/str user-id resolver path. The invariant test only walks the
    matrix; these tests reach the leaf returns inside the ``not
    is_authenticated`` branch."""

    def setUp(self) -> None:
        self.creator = User.objects.create_user(
            username="note_anon_creator", email="nac@cov.test", password="x"
        )

        # Public note ↔ public doc ↔ public corpus — anonymous reads pass.
        self.public_corpus = Corpus.objects.create(
            title="Public NC", creator=self.creator, is_public=True
        )
        self.public_doc = Document.objects.create(
            title="Public ND", creator=self.creator, is_public=True
        )
        self.public_note = Note.objects.create(
            title="Public Note",
            content="x",
            creator=self.creator,
            document=self.public_doc,
            corpus=self.public_corpus,
            is_public=True,
        )

        # Public note + public doc + NO corpus — should still pass anonymous READ
        # (the corpus-null branch of the anonymous logic).
        self.public_note_no_corpus = Note.objects.create(
            title="Public Note No Corpus",
            content="y",
            creator=self.creator,
            document=self.public_doc,
            corpus=None,
            is_public=True,
        )

        # Public doc, PRIVATE corpus, public note — anonymous denied via
        # the ``corpus is not None and not public`` branch.
        self.private_corpus = Corpus.objects.create(
            title="Private NC", creator=self.creator, is_public=False
        )
        self.note_private_corpus = Note.objects.create(
            title="Note Private Corpus",
            content="z",
            creator=self.creator,
            document=self.public_doc,
            corpus=self.private_corpus,
            is_public=True,
        )

        # Public note, PRIVATE doc — anonymous denied via the ``doc not
        # public`` branch.
        self.private_doc = Document.objects.create(
            title="Private ND", creator=self.creator, is_public=False
        )
        self.note_private_doc = Note.objects.create(
            title="Note Private Doc",
            content="w",
            creator=self.creator,
            document=self.private_doc,
            corpus=self.public_corpus,
            is_public=True,
        )

        # Private note, public doc/corpus — anonymous denied via the
        # ``not getattr(instance, 'is_public', False)`` branch.
        self.private_note = Note.objects.create(
            title="Private Note",
            content="v",
            creator=self.creator,
            document=self.public_doc,
            corpus=self.public_corpus,
            is_public=False,
        )

    def test_anonymous_can_read_fully_public_note(self) -> None:
        anon = AnonymousUser()
        self.assertTrue(self.public_note.user_can(anon, PermissionTypes.READ))

    def test_anonymous_can_read_public_note_with_null_corpus(self) -> None:
        anon = AnonymousUser()
        self.assertTrue(self.public_note_no_corpus.user_can(anon, PermissionTypes.READ))

    def test_anonymous_denied_when_corpus_is_private(self) -> None:
        anon = AnonymousUser()
        self.assertFalse(self.note_private_corpus.user_can(anon, PermissionTypes.READ))

    def test_anonymous_denied_when_doc_is_private(self) -> None:
        anon = AnonymousUser()
        self.assertFalse(self.note_private_doc.user_can(anon, PermissionTypes.READ))

    def test_anonymous_denied_when_note_is_private(self) -> None:
        anon = AnonymousUser()
        self.assertFalse(self.private_note.user_can(anon, PermissionTypes.READ))

    def test_anonymous_non_read_denied(self) -> None:
        """Even fully public chain — anonymous still denied non-READ."""
        anon = AnonymousUser()
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(self.public_note.user_can(anon, perm))

    def test_str_and_int_user_id_inputs_on_note(self) -> None:
        self.assertTrue(
            self.private_note.user_can(self.creator.id, PermissionTypes.READ)
        )
        self.assertTrue(
            self.private_note.user_can(str(self.creator.id), PermissionTypes.READ)
        )
        self.assertFalse(self.private_note.user_can(999_999_999, PermissionTypes.READ))

    def test_authenticated_user_can_read_note_with_null_corpus_via_doc_perm(
        self,
    ) -> None:
        """Authenticated branch: a note with ``corpus=None`` passes the
        MIN check when the user can READ the doc — there's no corpus
        scope to enforce. Pins the ``if corpus is None: return True``
        early-return in ``NoteManager.user_can``."""
        reader = User.objects.create_user(
            username="note_nocorpus_reader", email="nncr@cov.test", password="x"
        )
        set_permissions_for_obj_to_user(reader, self.public_doc, [PermissionTypes.READ])
        note = Note.objects.create(
            title="No Corpus Authn",
            content="x",
            creator=self.creator,
            document=self.public_doc,
            corpus=None,
            is_public=False,
        )
        self.assertTrue(note.user_can(reader, PermissionTypes.READ))

    def test_note_with_dangling_document_descriptor_denied(self) -> None:
        """``doc is None`` branch — authenticated path returns False
        when the ``document`` descriptor resolves to ``None``. The
        schema-level ``NOT NULL`` on ``document_id`` makes a true
        document-less note unsaveable, so we simulate the dangling
        descriptor by spoofing it on an in-memory instance and routing
        through the manager (which is the public surface
        ``NoteManager.user_can`` exposes)."""

        # Build a stand-in instance with the same attributes
        # ``NoteManager.user_can`` reads off the row, but with the
        # ``document`` descriptor pinned to ``None``. We use
        # ``Note(...)`` (no .save()) so we don't touch the DB.
        unsaved_note = Note(
            title="No Doc",
            content="x",
            creator=self.creator,
            is_public=False,
        )
        unsaved_note.document = None  # type: ignore[assignment]

        other = User.objects.create_user(
            username="note_orphan_other", email="noo@cov.test", password="x"
        )
        self.assertFalse(
            Note.objects.user_can(other, unsaved_note, PermissionTypes.READ)
        )


# ---------------------------------------------------------------------------
# UserFeedbackManager.user_can — non-public-annotation paths + DocumentManager
# ---------------------------------------------------------------------------


class UserFeedbackUserCanFallbackTestCase(TransactionTestCase):
    """Cover ``UserFeedbackManager.user_can`` when the feedback has no
    public commented annotation — the manager falls through to
    ``super().user_can`` which is the default branch. Also exercises
    ``DocumentManager.user_can`` (a thin ``super()`` delegate) so the
    one-line body is covered."""

    def setUp(self) -> None:
        self.creator = User.objects.create_user(
            username="ufb_creator", email="ufc@cov.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="ufb_stranger", email="ufs@cov.test", password="x"
        )

        # Feedback with NO commented annotation — the
        # commented-annotation branch short-circuits past the public-grant
        # and we land in ``super().user_can``.
        self.fb_no_annotation = UserFeedback.objects.create(
            creator=self.creator,
            is_public=False,
            comment="no annotation",
        )

        # Feedback that comments on a PRIVATE annotation — same fall-through.
        doc = Document.objects.create(
            title="UFB Doc", creator=self.creator, is_public=True
        )
        label = AnnotationLabel.objects.create(
            text="ufbl", label_type="TOKEN_LABEL", creator=self.creator
        )
        private_ann = Annotation.objects.create(
            raw_text="private_for_ufb",
            json={"x": 1},
            page=1,
            annotation_label=label,
            creator=self.creator,
            document=doc,
            is_public=False,
        )
        self.fb_private_annotation = UserFeedback.objects.create(
            creator=self.creator,
            commented_annotation=private_ann,
            is_public=False,
            comment="private",
        )

    def test_stranger_denied_on_feedback_with_no_commented_annotation(self) -> None:
        self.assertFalse(
            self.fb_no_annotation.user_can(self.stranger, PermissionTypes.READ)
        )

    def test_stranger_denied_when_commented_annotation_is_private(self) -> None:
        self.assertFalse(
            self.fb_private_annotation.user_can(self.stranger, PermissionTypes.READ)
        )

    def test_creator_passes_via_default_branch(self) -> None:
        self.assertTrue(
            self.fb_no_annotation.user_can(self.creator, PermissionTypes.READ)
        )

    def test_non_read_permission_falls_through_to_default(self) -> None:
        """Non-READ permissions never get the commented-annotation grant
        — verified by checking a stranger is denied UPDATE/DELETE on
        every feedback row regardless of annotation publicity."""
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                self.fb_no_annotation.user_can(self.stranger, perm),
                f"stranger granted {perm} on feedback — leak!",
            )

    def test_document_manager_user_can_delegate(self) -> None:
        """``DocumentManager.user_can`` is a thin ``super()`` call —
        exercise it directly so the one-line body is covered."""
        doc = Document.objects.create(
            title="DM Delegate", creator=self.creator, is_public=False
        )
        self.assertTrue(
            Document.objects.user_can(self.creator, doc, PermissionTypes.READ)
        )
        self.assertFalse(
            Document.objects.user_can(self.stranger, doc, PermissionTypes.READ)
        )


# ---------------------------------------------------------------------------
# PermissionQuerySet.visible_to_user — superuser/anonymous/guardian/LookupError
# ---------------------------------------------------------------------------


class PermissionQuerySetVisibleToUserTestCase(TransactionTestCase):
    """Exercise the fallback body of ``PermissionQuerySet.visible_to_user``
    directly.

    In production every model that inherits ``PermissionQuerySet``
    (``DocumentQuerySet``, ``AnnotationQuerySet``, ``NoteQuerySet``)
    overrides ``visible_to_user``, so the base body is only reached by
    a hypothetical future model that uses ``PermissionManager`` without
    its own queryset override. We exercise that body directly against
    ``Document`` (which has both ``creator``, ``is_public`` and a
    ``documentuserobjectpermission`` guardian table) so codecov sees the
    superuser/anonymous/authenticated/guardian/LookupError branches."""

    def setUp(self) -> None:
        from opencontractserver.shared.QuerySets import PermissionQuerySet

        self.PermissionQuerySet = PermissionQuerySet

        self.creator = User.objects.create_user(
            username="pqs_creator", email="pqc@cov.test", password="x"
        )
        self.grantee = User.objects.create_user(
            username="pqs_grantee", email="pqg@cov.test", password="x"
        )
        self.stranger = User.objects.create_user(
            username="pqs_stranger", email="pqs@cov.test", password="x"
        )
        self.superuser = User.objects.create_superuser(
            username="pqs_admin", email="pqa@cov.test", password="x"
        )

        self.private_doc = Document.objects.create(
            title="PQS Private", creator=self.creator, is_public=False
        )
        self.public_doc = Document.objects.create(
            title="PQS Public", creator=self.creator, is_public=True
        )
        set_permissions_for_obj_to_user(
            self.grantee, self.private_doc, [PermissionTypes.READ]
        )

    def _filter(self, user: Any) -> set[int]:
        """Run the base ``PermissionQuerySet.visible_to_user`` body
        directly (bypassing ``DocumentQuerySet.visible_to_user``)."""
        qs: Any = self.PermissionQuerySet(model=Document, using="default")
        return set(qs.visible_to_user(user).values_list("pk", flat=True))

    def test_superuser_sees_all(self) -> None:
        ids = self._filter(self.superuser)
        self.assertIn(self.private_doc.pk, ids)
        self.assertIn(self.public_doc.pk, ids)

    def test_anonymous_sees_only_public(self) -> None:
        ids = self._filter(AnonymousUser())
        self.assertIn(self.public_doc.pk, ids)
        self.assertNotIn(self.private_doc.pk, ids)

    def test_none_user_is_treated_as_anonymous(self) -> None:
        ids = self._filter(None)
        self.assertIn(self.public_doc.pk, ids)
        self.assertNotIn(self.private_doc.pk, ids)

    def test_authenticated_creator_sees_own_private(self) -> None:
        ids = self._filter(self.creator)
        self.assertIn(self.private_doc.pk, ids)
        self.assertIn(self.public_doc.pk, ids)

    def test_authenticated_stranger_sees_only_public(self) -> None:
        ids = self._filter(self.stranger)
        self.assertIn(self.public_doc.pk, ids)
        self.assertNotIn(self.private_doc.pk, ids)

    def test_authenticated_grantee_sees_private_via_guardian(self) -> None:
        """Explicit ``read_document`` guardian grant → private doc visible."""
        ids = self._filter(self.grantee)
        self.assertIn(self.private_doc.pk, ids)
        self.assertIn(self.public_doc.pk, ids)

    def test_lookup_error_fallback_degrades_to_creator_public(self) -> None:
        """When the guardian table doesn't exist (``LookupError``), the
        body degrades to ``creator | is_public`` — visible_to_user must
        not raise. We simulate the missing table by pointing the
        queryset at a model whose name will not resolve to a
        ``<name>userobjectpermission`` model."""
        from unittest.mock import patch

        # Easiest way to exercise the LookupError branch: patch the
        # lazy ``apps.get_model`` call to raise it.
        qs: Any = self.PermissionQuerySet(model=Document, using="default")
        with patch(
            "django.apps.apps.get_model", side_effect=LookupError("no such model")
        ):
            ids = set(qs.visible_to_user(self.creator).values_list("pk", flat=True))
        # Without guardian we still get creator+public.
        self.assertIn(self.private_doc.pk, ids)
        self.assertIn(self.public_doc.pk, ids)


# ---------------------------------------------------------------------------
# UserFeedbackQuerySet — authenticated guardian path
# ---------------------------------------------------------------------------


class UserFeedbackQuerySetGuardianTestCase(TransactionTestCase):
    """The authenticated branch of ``UserFeedbackQuerySet.visible_to_user``
    issues a guardian lookup for ``userfeedbackuserobjectpermission``.
    The invariant matrix exercises the symmetric path; here we pin the
    explicit-guardian-grant branch."""

    def setUp(self) -> None:
        self.creator = User.objects.create_user(
            username="ufq_creator", email="ufqc@cov.test", password="x"
        )
        self.grantee = User.objects.create_user(
            username="ufq_grantee", email="ufqg@cov.test", password="x"
        )
        self.fb = UserFeedback.objects.create(
            creator=self.creator,
            is_public=False,
            comment="guardian",
        )
        set_permissions_for_obj_to_user(self.grantee, self.fb, [PermissionTypes.READ])

    def test_grantee_sees_feedback_via_guardian(self) -> None:
        ids = set(
            UserFeedback.objects.visible_to_user(self.grantee).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.fb.pk, ids)

    def test_stranger_does_not_see_feedback(self) -> None:
        stranger = User.objects.create_user(
            username="ufq_stranger", email="ufqs@cov.test", password="x"
        )
        ids = set(
            UserFeedback.objects.visible_to_user(stranger).values_list("pk", flat=True)
        )
        self.assertNotIn(self.fb.pk, ids)
