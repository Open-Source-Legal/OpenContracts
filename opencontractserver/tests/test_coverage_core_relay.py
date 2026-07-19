"""Coverage-focused tests for ``config.graphql.core.relay``.

The strawberry migration ported ``config/graphql/core/relay.py`` wholesale
from graphene-django's connection/node/FK machinery (see the module
docstring there). ``test_fk_visibility_traversal.py`` already pins the two
main ``resolve_visible_fk`` hook branches (``get_queryset`` / ``get_node``);
this module fills in the remaining gaps left uncovered after that migration:

* ``type_name_for_instance`` — the model→type-name MRO walk used for
  interface type resolution.
* ``get_node_from_global_id`` — the unregistered-type guard, the
  best-effort ``_node_type_hint`` stash on a context that refuses new
  attributes, and the malformed-pk guards on both the custom-``get_node``
  and default (``get_queryset().get(pk=)``) branches.
* The ``ConnectionValue`` field resolvers (``totalCount`` cached-queryset
  branch, ``currentPage`` / ``pageCount`` — the ``PdfPageAwareConnection``
  port) and ``make_connection_types(..., pdf_page_aware=True)``, which
  wires those two resolvers onto a generated connection type.
* ``resolve_django_connection`` — the offset+after cursor combination, the
  ``last`` limit enforcement, the no-``default_manager`` empty fallback,
  and the invalid-filterset-data path.
* ``resolve_django_list`` — the per-type visibility hook applied to a list
  field's queryset.
* The two remaining ``resolve_visible_fk`` branches: an unregistered target
  type (falls back to the plain attribute) and a registered-but-hookless
  target type (falls back to the target model's unfiltered manager).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.test import TestCase
from graphql_relay import offset_to_cursor, to_global_id

from config.graphql.core.filtering import setup_filterset
from config.graphql.core.relay import (
    ConnectionValue,
    PageInfo,
    _resolve_current_page,
    _resolve_page_count,
    _resolve_total_count,
    get_node_from_global_id,
    make_connection_types,
    resolve_django_connection,
    resolve_django_list,
    resolve_visible_fk,
    type_name_for_instance,
)
from config.graphql.filters import AnnotationFilter
from config.graphql.schema import schema  # noqa: F401 — populates the type registry
from config.graphql.user_types import UserType
from opencontractserver.agents.models import AgentActionResult
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Extract
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import User
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

# A name deliberately absent from the type registry, used whenever a test
# wants ``apply_type_get_queryset`` to take its identity no-op path instead
# of engaging a real type's permission filter (i.e. to isolate the relay/
# pagination arithmetic from permission-filtering concerns).
_UNREGISTERED_TYPE_NAME = "CoverageUnregisteredNodeType"


class _Ctx:
    """Minimal Django-request-like GraphQL context (carries ``user``)."""

    def __init__(self, user: User) -> None:
        self.user = user


class _Info:
    """Minimal ``strawberry.Info``-like stand-in for direct resolver calls.

    ``field_name`` mirrors ``strawberry.Info.field_name``, read by
    ``resolve_django_connection``'s ``first``/``last``/``offset`` limit
    assertion messages.
    """

    def __init__(self, user: User) -> None:
        self.context = _Ctx(user)
        self.field_name = "coverageTestField"


class _Row:
    """Lightweight stand-in for a Django row exposing only FK id columns."""

    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class TypeNameForInstanceTests(TestCase):
    """``type_name_for_instance`` walks the instance's MRO against the
    model→type-name registry populated by ``register_type``."""

    def test_registered_model_instance_returns_its_type_name(self) -> None:
        owner = User.objects.create_user(username="tnfi_owner", password="pw")
        # Unsaved instance — the lookup only inspects ``type(instance)``.
        corpus = Corpus(title="Unsaved Corpus", creator=owner)
        self.assertEqual(type_name_for_instance(corpus), "CorpusType")

    def test_unregistered_instance_returns_none(self) -> None:
        self.assertIsNone(type_name_for_instance(object()))


class GetNodeFromGlobalIdCoverageTests(TestCase):
    """Guards in ``get_node_from_global_id`` beyond the happy path."""

    owner: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="gnfgi_owner", password="pw")

    def test_unregistered_type_name_raises(self) -> None:
        global_id = to_global_id("TotallyUnregisteredGraphQLType", 1)
        with self.assertRaises(Exception) as cm:
            get_node_from_global_id(_Info(self.owner), global_id)
        self.assertIn("not found in schema", str(cm.exception))

    def test_node_type_hint_assignment_is_best_effort_on_a_frozen_context(
        self,
    ) -> None:
        """A context that rejects new attributes must not blow up the fetch.

        Most contexts are plain objects and happily accept the
        ``_node_type_hint`` stash; a ``__slots__``-based context (or any
        object that raises ``AttributeError`` on an unknown attribute)
        exercises the ``except AttributeError: pass`` fallback instead —
        the fetch must still succeed.
        """

        class _FrozenCtx:
            __slots__ = ("user",)

            def __init__(self, user: User) -> None:
                self.user = user

        class _FrozenInfo:
            __slots__ = ("context", "field_name")

            def __init__(self, context: _FrozenCtx) -> None:
                self.context = context
                self.field_name = "coverageTestField"

        info = _FrozenInfo(_FrozenCtx(self.owner))
        global_id = to_global_id("UserType", self.owner.pk)

        result = get_node_from_global_id(info, global_id)
        self.assertEqual(result, self.owner)
        with self.assertRaises(
            AttributeError,
            msg="frozen context accepted the hint — the slots guard changed",
        ):
            getattr(info.context, "_node_type_hint")

    def test_get_node_hook_malformed_pk_is_treated_as_not_found(self) -> None:
        """``ExtractType.get_node`` casts ``int(pk)`` with no try/except of
        its own — the relay-level guard must catch the ``ValueError`` and
        raise the model's ``DoesNotExist`` instead of a raw 500."""
        global_id = to_global_id("ExtractType", "not-a-number")
        with self.assertRaises(Extract.DoesNotExist):
            get_node_from_global_id(_Info(self.owner), global_id)

    def test_default_path_malformed_pk_is_treated_as_not_found(self) -> None:
        """A type with no ``get_node`` hook (e.g. ``AgentActionResultType``)
        falls through to ``get_queryset().get(pk=)``; Django raises
        ``ValueError`` for a non-numeric pk against an integer column —
        the relay-level guard must convert that to ``DoesNotExist`` too."""
        global_id = to_global_id("AgentActionResultType", "not-a-number")
        with self.assertRaises(AgentActionResult.DoesNotExist):
            get_node_from_global_id(_Info(self.owner), global_id)


class ConnectionValueResolverTests(TestCase):
    """Direct tests of the ``ConnectionValue`` field resolvers — the
    ``totalCount`` cached-queryset branch and the ``PdfPageAwareConnection``
    port (``currentPage`` / ``pageCount``)."""

    owner: User
    doc: Document
    label: AnnotationLabel
    pages: list[int]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="cvrt_owner", password="pw")
        cls.doc = Document.objects.create(title="CVRT Doc", creator=cls.owner)
        cls.label = AnnotationLabel.objects.create(
            text="CVRT Label", label_type=DOC_TYPE_LABEL, creator=cls.owner
        )
        cls.pages = [0, 2, 5]
        for page in cls.pages:
            Annotation.objects.create(
                document=cls.doc,
                annotation_label=cls.label,
                creator=cls.owner,
                page=page,
                json={},
            )

    @staticmethod
    def _blank_page_info() -> PageInfo:
        return PageInfo(
            has_next_page=False,
            has_previous_page=False,
            start_cursor=None,
            end_cursor=None,
        )

    def test_total_count_uses_the_result_cache_once_a_queryset_is_evaluated(
        self,
    ) -> None:
        """Once a queryset has been materialised (``_result_cache`` set),
        ``totalCount`` must read its length instead of issuing a fresh
        ``COUNT(*)`` — this is what lets a single request reuse an
        already-iterated connection queryset for both ``edges`` and
        ``totalCount`` without doubling the query count."""
        queryset = Annotation.objects.filter(document=self.doc)
        list(queryset)  # force evaluation
        self.assertIsNotNone(queryset._result_cache)

        connection = ConnectionValue(edges=[], page_info=self._blank_page_info())
        connection.iterable = queryset
        # The direct-call unit-test pattern (see module docstring) bypasses
        # the real ``strawberry.Info`` the resolver's signature declares —
        # the function body never actually reads ``info``.
        self.assertEqual(
            _resolve_total_count(connection, None), len(self.pages)  # type: ignore[arg-type]
        )

    def test_current_page_is_always_one(self) -> None:
        """Port of ``PdfPageAwareConnection.resolve_current_page`` — the
        graphene original always returned page 1 (single-page connections
        only); the port preserves that constant."""
        connection = ConnectionValue(edges=[], page_info=self._blank_page_info())
        self.assertEqual(
            _resolve_current_page(connection, None), 1  # type: ignore[arg-type]
        )

    def test_page_count_is_the_max_page_across_the_iterable(self) -> None:
        connection = ConnectionValue(edges=[], page_info=self._blank_page_info())
        connection.iterable = Annotation.objects.filter(document=self.doc)
        self.assertEqual(
            _resolve_page_count(connection, None), max(self.pages)  # type: ignore[arg-type]
        )


class MakeConnectionTypesPdfPageAwareTests(TestCase):
    """``make_connection_types(..., pdf_page_aware=True)`` wires the
    ``currentPage`` / ``pageCount`` resolvers onto the generated connection
    type — no production call site opts into this today, but it is the
    live port of graphene's ``PdfPageAwareConnection`` and must keep
    working for the next caller that does."""

    def test_pdf_page_aware_connection_exposes_current_page_and_page_count(
        self,
    ) -> None:
        connection_cls = make_connection_types(
            UserType,
            type_name="CoveragePdfPageAwareConnection",
            countable=True,
            pdf_page_aware=True,
        )
        definition = getattr(connection_cls, "__strawberry_definition__")
        field_names = {field.python_name for field in definition.fields}
        self.assertIn("current_page", field_names)
        self.assertIn("page_count", field_names)


class ResolveDjangoConnectionCoverageTests(TestCase):
    """``resolve_django_connection`` — the graphene-django
    ``DjangoConnectionField``/``DjangoFilterConnectionField`` port."""

    owner: User
    corpora: list[Corpus]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="rdcc_owner", password="pw")
        cls.corpora = [
            Corpus.objects.create(
                title=f"RelayCov{i}", creator=cls.owner, is_public=True
            )
            for i in range(6)
        ]

    def _ordered_queryset(self):
        return Corpus.objects.filter(pk__in=[c.pk for c in self.corpora]).order_by("id")

    def test_offset_and_after_cursor_combine_for_pagination(self) -> None:
        """graphene-django's 1-based ``offset`` argument composes with an
        ``after`` cursor rather than replacing it — resuming from
        ``after`` and then skipping ``offset`` further rows."""
        ordered_ids = list(self._ordered_queryset().values_list("id", flat=True))
        result = resolve_django_connection(
            resolved=self._ordered_queryset(),
            info=_Info(self.owner),
            args={"offset": 2, "after": offset_to_cursor(0)},
            node_type_name=_UNREGISTERED_TYPE_NAME,
        )
        returned_ids = [edge.node.id for edge in result.edges]
        self.assertEqual(returned_ids, ordered_ids[3:])

    def test_last_argument_within_max_limit_is_honoured(self) -> None:
        ordered_ids = list(self._ordered_queryset().values_list("id", flat=True))
        result = resolve_django_connection(
            resolved=self._ordered_queryset(),
            info=_Info(self.owner),
            args={"last": 3},
            node_type_name=_UNREGISTERED_TYPE_NAME,
            max_limit=10,
        )
        returned_ids = [edge.node.id for edge in result.edges]
        self.assertEqual(returned_ids, ordered_ids[-3:])

    def test_last_argument_beyond_max_limit_raises(self) -> None:
        """``RELAY_CONNECTION_MAX_LIMIT`` enforcement on ``last`` mirrors
        the existing enforcement on ``first`` — a client can't bypass the
        cap by paginating from the tail instead of the head."""
        with self.assertRaises(AssertionError):
            resolve_django_connection(
                resolved=self._ordered_queryset(),
                info=_Info(self.owner),
                args={"last": 999},
                node_type_name=_UNREGISTERED_TYPE_NAME,
                max_limit=10,
            )

    def test_resolved_none_without_default_manager_yields_an_empty_connection(
        self,
    ) -> None:
        result = resolve_django_connection(
            resolved=None,
            info=_Info(self.owner),
            args={},
            node_type_name=_UNREGISTERED_TYPE_NAME,
            default_manager=None,
        )
        self.assertEqual(result.edges, [])
        self.assertFalse(result.page_info.has_next_page)

    def test_invalid_filterset_data_raises_validation_error(self) -> None:
        """``DjangoFilterConnectionField.resolve_queryset`` surfaced invalid
        filter input as a ``ValidationError`` rather than silently ignoring
        it or 500ing — a malformed relay global ID passed to
        ``annotationLabelId`` is exactly the shape a client can send."""
        with self.assertRaises(ValidationError):
            resolve_django_connection(
                resolved=Annotation.objects.all(),
                info=_Info(self.owner),
                args={"annotation_label_id": "not-a-valid-global-id"},
                node_type_name="AnnotationType",
                filterset_class=setup_filterset(AnnotationFilter),
                filter_args={"annotation_label_id": "annotation_label_id"},
            )


class ResolveDjangoListCoverageTests(TestCase):
    """``resolve_django_list`` — the ``DjangoListField.list_resolver`` port
    that applies the target type's visibility hook to a plain list field."""

    owner: User
    outsider: User
    public_corpus: Corpus
    private_corpus: Corpus

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="rdlc_owner", password="pw")
        cls.outsider = User.objects.create_user(username="rdlc_outsider", password="pw")
        cls.public_corpus = Corpus.objects.create(
            title="RDLC Public", creator=cls.owner, is_public=True
        )
        cls.private_corpus = Corpus.objects.create(
            title="RDLC Private", creator=cls.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            cls.owner, cls.private_corpus, [PermissionTypes.CRUD]
        )

    def _queryset(self):
        return Corpus.objects.filter(
            pk__in=[self.public_corpus.pk, self.private_corpus.pk]
        )

    def test_applies_the_target_types_visibility_hook(self) -> None:
        visible_to_outsider = resolve_django_list(
            None, _Info(self.outsider), self._queryset(), "CorpusType"
        )
        outsider_ids = set(visible_to_outsider.values_list("id", flat=True))
        self.assertIn(self.public_corpus.id, outsider_ids)
        self.assertNotIn(
            self.private_corpus.id,
            outsider_ids,
            "private corpus leaked through resolve_django_list",
        )

        visible_to_owner = resolve_django_list(
            None, _Info(self.owner), self._queryset(), "CorpusType"
        )
        owner_ids = set(visible_to_owner.values_list("id", flat=True))
        self.assertIn(self.public_corpus.id, owner_ids)
        self.assertIn(self.private_corpus.id, owner_ids)

    def test_non_queryset_values_pass_through_unchanged(self) -> None:
        value = ["a", "b", "c"]
        self.assertEqual(
            resolve_django_list(None, _Info(self.owner), value, "CorpusType"), value
        )


class ResolveVisibleFkFallbackTests(TestCase):
    """The two ``resolve_visible_fk`` branches not covered by
    ``test_fk_visibility_traversal.py``'s ``get_queryset``/``get_node``
    cases: an unregistered target type, and a registered target with no
    visibility hook at all."""

    owner: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="rvfft_owner", password="pw")

    def test_unregistered_target_type_falls_back_to_the_plain_attribute(
        self,
    ) -> None:
        row = _Row(foo_id=123, foo="plain-attribute-value")
        result = resolve_visible_fk(
            row, _Info(self.owner), "foo_id", "TotallyUnregisteredFkNodeType"
        )
        self.assertEqual(result, "plain-attribute-value")

    def test_registered_target_without_visibility_hooks_uses_default_manager(
        self,
    ) -> None:
        """``UserType`` is registered (so the FK isn't simply left alone)
        but declares no ``get_queryset``/``get_node``/``get_node_for_fk`` —
        parity with graphene's unfiltered default FK resolver."""
        row = _Row(creator_id=self.owner.pk)
        result = resolve_visible_fk(row, _Info(self.owner), "creator_id", "UserType")
        self.assertEqual(result, self.owner)
