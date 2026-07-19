"""Relay machinery reproducing graphene / graphene-django wire semantics.

Provides:

* ``Node`` — the relay interface with graphene-format global IDs
  (``base64("TypeName:pk")``).
* a **type registry** mapping GraphQL type names to their Django model and
  per-type hooks (``get_queryset`` / ``get_node``), mirroring
  ``DjangoObjectType`` Meta behaviour.
* ``PageInfo`` / connection factories producing ``XTypeConnection`` /
  ``XTypeEdge`` types byte-compatible with graphene's SDL output
  (including ``CountableConnection.totalCount`` and
  ``PdfPageAwareConnection.currentPage`` / ``pageCount``).
* ``resolve_django_connection`` — a faithful port of
  ``graphene_django.fields.DjangoConnectionField.connection_resolver`` +
  ``DjangoFilterConnectionField`` filterset application, including the
  1-based ``offset``→``after`` conversion, ``RELAY_CONNECTION_MAX_LIMIT``
  enforcement and ``arrayconnection`` cursors.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import django.db.models
import strawberry
from django.db.models import Manager, QuerySet
from graphql_relay import (
    connection_from_array_slice,
    cursor_to_offset,
    from_global_id,
    get_offset_with_default,
    offset_to_cursor,
    to_global_id,
)

logger = logging.getLogger(__name__)

# graphene's GRAPHENE["RELAY_CONNECTION_MAX_LIMIT"] equivalent.
RELAY_CONNECTION_MAX_LIMIT = 100


# --------------------------------------------------------------------------- #
# Type registry                                                               #
# --------------------------------------------------------------------------- #


class TypeRegistryEntry:
    __slots__ = (
        "type_name",
        "strawberry_type",
        "model",
        "get_queryset",
        "get_node",
        "get_node_for_fk",
    )

    def __init__(
        self,
        type_name: str,
        strawberry_type: type,
        model: type[django.db.models.Model] | None,
        get_queryset: Callable[[QuerySet, Any], QuerySet] | None = None,
        get_node: Callable[[Any, str], Any] | None = None,
        get_node_for_fk: Callable[[Any, str], Any] | None = None,
    ) -> None:
        self.type_name = type_name
        self.strawberry_type = strawberry_type
        self.model = model
        self.get_queryset = get_queryset
        self.get_node = get_node
        self.get_node_for_fk = get_node_for_fk


_TYPE_REGISTRY: dict[str, TypeRegistryEntry] = {}
_MODEL_PRIMARY_TYPE: dict[type, str] = {}


def register_type(
    type_name: str,
    strawberry_type: type,
    model: type[django.db.models.Model] | None = None,
    *,
    get_queryset: Callable[[QuerySet, Any], QuerySet] | None = None,
    get_node: Callable[[Any, str], Any] | None = None,
    get_node_for_fk: Callable[[Any, str], Any] | None = None,
    primary: bool = True,
) -> None:
    """Register a strawberry type so relay helpers can find its model/hooks.

    ``primary=False`` keeps a secondary type (e.g. a ``_WRITE`` variant of a
    model that already has a canonical read type) out of the model→type map
    used for interface type resolution.

    ``get_node`` backs the *singular* ``xxx(id:)`` / relay ``node(id:)``
    lookup (``get_node_from_global_id``) — it must stay request-fresh for
    types whose permissions can change mid-request against a reused context
    (see ``test_permissioning.py``, which drives several ``corpus(id:)``
    calls through one shared context while provisioning/deprovisioning perms
    between them). ``get_node_for_fk`` backs FK/relay-FK traversal
    (``resolve_visible_fk``) instead — a distinct call site that is safe to
    memoize per-request even when ``get_node`` isn't, because each FK access
    reads a fixed, already-loaded parent row rather than replaying a query
    whose permission state the test deliberately mutates. Falls back to
    ``get_node`` when unset.
    """
    _TYPE_REGISTRY[type_name] = TypeRegistryEntry(
        type_name, strawberry_type, model, get_queryset, get_node, get_node_for_fk
    )
    if model is not None and primary and model not in _MODEL_PRIMARY_TYPE:
        _MODEL_PRIMARY_TYPE[model] = type_name

    # Port of ``DjangoObjectType.is_type_of`` (graphene-django): resolvers
    # return Django MODEL INSTANCES for model-backed types, but strawberry
    # auto-generates an ``isinstance``-against-the-strawberry-class
    # ``is_type_of`` for every type that implements an interface (``Node``),
    # which rejects ORM objects with "Expected value of type 'XType' but
    # got: <X instance>". Install the graphene-django semantics instead:
    # a model instance (or an actual strawberry-type instance) satisfies
    # the type. Only set when strawberry hasn't been given an explicit
    # hook already.
    if model is not None:
        definition = getattr(strawberry_type, "__strawberry_definition__", None)
        if definition is not None and definition.is_type_of is None:

            def _is_type_of(
                obj: Any, _info: Any, _types: tuple = (strawberry_type, model)
            ) -> bool:
                return isinstance(obj, _types)

            definition.is_type_of = _is_type_of

    _install_graphene_resolver_aliases(type_name, strawberry_type)


def _install_graphene_resolver_aliases(type_name: str, strawberry_type: type) -> None:
    """Expose graphene-style ``XType.resolve_<field>(root, info, ...)`` methods.

    graphene resolvers were bound methods callable as
    ``XType.resolve_field(obj, info)`` — a form the unit tests use directly to
    exercise resolver logic without going through the full schema. The
    strawberry port keeps each custom resolver as a module-level
    ``_resolve_<TypeName>_<field>(root, info, ...)`` function; this installs a
    thin ``resolve_<field>`` staticmethod alias onto the type for each, plus
    the three permission-annotation fields, so those tests keep working
    unchanged. Strawberry ignores arbitrary ``resolve_*`` attributes (only
    ``@strawberry.field`` methods and annotated fields matter), so the aliases
    are inert for schema execution.
    """
    import sys

    module = sys.modules.get(strawberry_type.__module__)
    if module is not None:
        prefix = f"_resolve_{type_name}_"
        for attr_name in dir(module):
            if attr_name.startswith(prefix):
                field = attr_name[len(prefix) :]
                fn = getattr(module, attr_name)
                if callable(fn) and not hasattr(strawberry_type, f"resolve_{field}"):
                    setattr(strawberry_type, f"resolve_{field}", staticmethod(fn))
        # graphene ``get_node`` / ``get_queryset`` classmethods (some unit
        # tests — e.g. test_doc_annotations_prefetch — call them directly).
        for hook in ("get_node", "get_queryset"):
            hook_fn = getattr(module, f"_{hook}_{type_name}", None)
            if callable(hook_fn) and not hasattr(strawberry_type, hook):
                setattr(strawberry_type, hook, staticmethod(hook_fn))

    # Permission-annotation fields live in the shared core module, not the
    # per-type module, so alias them explicitly.
    from config.graphql.core import permissions as _perm

    for field, fn in (
        ("my_permissions", _perm.resolve_my_permissions),
        ("is_published", _perm.resolve_is_published),
        ("object_shared_with", _perm.resolve_object_shared_with),
    ):
        if not hasattr(strawberry_type, f"resolve_{field}"):
            setattr(strawberry_type, f"resolve_{field}", staticmethod(fn))


def get_registry_entry(type_name: str) -> TypeRegistryEntry | None:
    return _TYPE_REGISTRY.get(type_name)


def type_name_for_instance(instance: Any) -> str | None:
    """Best-effort GraphQL type name for a Django model instance."""
    for klass in type(instance).__mro__:
        name = _MODEL_PRIMARY_TYPE.get(klass)
        if name is not None:
            return name
    return None


def apply_type_get_queryset(type_name: str, queryset: Any, info: Any) -> Any:
    """Apply the registered per-type ``get_queryset`` hook (graphene-django's
    ``DjangoObjectType.get_queryset``) if one exists."""
    entry = _TYPE_REGISTRY.get(type_name)
    if entry is not None and entry.get_queryset is not None:
        return entry.get_queryset(queryset, info)
    return queryset


# --------------------------------------------------------------------------- #
# Node interface + global-id resolution                                        #
# --------------------------------------------------------------------------- #


def _resolve_node_id(root: Any, info: Any) -> str:
    """Global-ID resolver — graphene format ``base64("TypeName:pk")``.

    The concrete runtime parent type name is used, matching graphene's
    behaviour for types that implement the ``Node`` interface.
    """
    type_name = info._raw_info.parent_type.name
    return to_global_id(type_name, root.pk)


@strawberry.interface(name="Node", description="An object with an ID")
class Node:
    @strawberry.field(name="id", description="The ID of the object")
    def id(self, info: strawberry.Info) -> strawberry.ID:
        return strawberry.ID(_resolve_node_id(self, info))


def get_node_from_global_id(
    info: Any, global_id: str, only_type_name: str | None = None
) -> Any:
    """Relay node fetch matching graphene-django's ``relay.Node.Field``.

    Mirrors ``graphene_django.types.DjangoObjectType.get_node`` semantics —
    the resolver graphene used for every ``relay.Node.Field(XType)`` in the
    old schema:

    * A type with a **custom ``get_node`` hook** (registered from a graphene
      ``get_node`` override — e.g. ``CorpusType`` which ported
      ``OpenContractsNode``'s permission-aware fetch, or ``ExtractType`` /
      ``AnalysisType`` / ``ConversationType``) uses that hook.
    * Otherwise the DEFAULT path applies the type's registered
      ``get_queryset`` (the permission filter for types that define one; the
      identity manager for types that don't) and fetches by pk — **exactly**
      graphene-django's ``cls.get_queryset(model._default_manager, info)
      .get(pk=id)``. This is deliberately NOT a blanket
      ``BaseService.get_or_none``: graphene left types WITHOUT a
      ``get_queryset`` resolving unfiltered by pk here, with per-field
      resolvers enforcing visibility, and over-filtering this path silently
      changed that contract (issue surfaced by
      ``test_mentions.test_permission_enforcement_corpus``). Types whose
      *singular* ``xxx(id:)`` lookup must stay permission-scoped instead
      register an explicit ``get_node`` hook (the first bullet) — e.g.
      ``MessageType`` now routes ``chatMessage(id:)`` through
      ``BaseService.get_or_none`` (``_get_node_MessageType``), closing a
      pre-existing unfiltered-``.get(pk)`` IDOR; ``test_singular_node_idor``
      asserts every model-backed singular target carries such a hook.

    Returns the instance, or raises the model's ``DoesNotExist`` with a
    unified (IDOR-safe) message. Malformed pks (a global id passed where a
    raw pk is expected, or an out-of-range value) also raise ``DoesNotExist``
    rather than a 500.
    """
    _type, _pk = from_global_id(global_id)
    entry = _TYPE_REGISTRY.get(_type)
    if entry is None or entry.model is None:
        raise Exception(f'Relay Node "{_type}" not found in schema')

    if only_type_name is not None and _type != only_type_name:
        raise AssertionError(f"Must receive a {only_type_name} id.")

    # Stash the type name announced by the global id so interface
    # type resolution can honour it (e.g. ``node(id:)`` fields).
    try:
        info.context._node_type_hint = _type
    except AttributeError:
        # Frozen/immutable context — hint is best-effort only.
        pass

    not_found = entry.model.DoesNotExist(  # type: ignore[attr-defined]
        f"{entry.model.__name__} matching query does not exist."
    )

    if entry.get_node is not None:
        try:
            node = entry.get_node(info, _pk)
        except (ValueError, TypeError, OverflowError):
            # Malformed / out-of-range pk from untrusted input reaching a
            # ``get_node`` hook that casts it (e.g. ``int(pk)``) — treat as
            # not-found, the same IDOR-safe branch the default path takes
            # below, rather than surfacing a raw ``ValueError``.
            raise not_found
        if node is None:
            raise not_found
        return node

    queryset = apply_type_get_queryset(
        _type, entry.model._default_manager.get_queryset(), info
    )
    try:
        return queryset.get(pk=_pk)
    except entry.model.DoesNotExist:  # type: ignore[attr-defined]
        raise not_found
    except (ValueError, TypeError, OverflowError):
        # Malformed / out-of-range pk from untrusted input — treat as
        # not-found (graphene-django never surfaced a 500 here).
        raise not_found


# --------------------------------------------------------------------------- #
# PageInfo + connection value objects                                          #
# --------------------------------------------------------------------------- #


@strawberry.type(
    name="PageInfo",
    description=(
        "The Relay compliant `PageInfo` type, containing data necessary to"
        " paginate this connection."
    ),
)
class PageInfo:
    has_next_page: bool = strawberry.field(
        description="When paginating forwards, are there more items?"
    )
    has_previous_page: bool = strawberry.field(
        description="When paginating backwards, are there more items?"
    )
    start_cursor: str | None = strawberry.field(
        description="When paginating backwards, the cursor to continue."
    )
    end_cursor: str | None = strawberry.field(
        description="When paginating forwards, the cursor to continue."
    )


class ConnectionValue:
    """Runtime value returned by connection resolvers.

    Plain attribute container — the strawberry connection types generated by
    ``make_connection_types`` read ``edges`` / ``page_info`` off it via
    default (getattr) resolution, and the ``totalCount`` / page-aware
    resolvers read ``iterable`` / ``length``.
    """

    __slots__ = ("edges", "page_info", "iterable", "length")

    def __init__(self, edges: list[Any], page_info: PageInfo) -> None:
        self.edges = edges
        self.page_info = page_info
        self.iterable = None
        self.length = None


class EdgeValue:
    __slots__ = ("node", "cursor")

    def __init__(self, node: Any, cursor: str) -> None:
        self.node = node
        self.cursor = cursor


def _resolve_total_count(root: ConnectionValue, info: strawberry.Info) -> int:
    """Port of ``config.graphql.base.CountableConnection.resolve_total_count``."""
    iterable = root.iterable
    if isinstance(iterable, QuerySet):
        if iterable._result_cache is not None:
            return len(iterable._result_cache)
        return iterable.count()
    return len(iterable) if iterable is not None else 0


def _resolve_current_page(root: ConnectionValue, info: strawberry.Info) -> int:
    """Port of ``PdfPageAwareConnection.resolve_current_page``."""
    return 1


def _resolve_page_count(root: ConnectionValue, info: strawberry.Info) -> int:
    """Port of ``PdfPageAwareConnection.resolve_page_count``."""
    return max(
        list(root.iterable.values_list("page", flat=True).distinct())  # type: ignore[attr-defined]
    )


def make_connection_types(
    node_type: type,
    *,
    type_name: str,
    countable: bool = True,
    pdf_page_aware: bool = False,
) -> type:
    """Create ``{X}Connection`` + ``{X}Edge`` strawberry types.

    Field names, nullability, and descriptions match graphene's relay
    connection output exactly (see the golden SDL). Returns the connection
    class; the edge class is attached as ``.Edge``.
    """
    connection_name = type_name
    assert connection_name.endswith("Connection"), connection_name
    edge_name = connection_name[: -len("Connection")] + "Edge"

    edge_cls = type(
        edge_name,
        (),
        {
            "__annotations__": {
                "node": Optional[node_type],
                "cursor": str,
            },
            "node": strawberry.field(description="The item at the end of the edge"),
            "cursor": strawberry.field(description="A cursor for use in pagination"),
        },
    )
    edge_cls = strawberry.type(
        edge_cls,
        name=edge_name,
        description=(
            f"A Relay edge containing a `{connection_name[: -len('Connection')]}`"
            " and its cursor."
        ),
    )

    namespace: dict[str, Any] = {
        "__annotations__": {
            "page_info": PageInfo,
            "edges": list[Optional[edge_cls]],  # type: ignore[valid-type]
        },
        "page_info": strawberry.field(
            description="Pagination data for this connection."
        ),
        "edges": strawberry.field(description="Contains the nodes in this connection."),
    }
    if countable:
        namespace["total_count"] = strawberry.field(
            resolver=_resolve_total_count, graphql_type=Optional[int]
        )
    if pdf_page_aware:
        namespace["current_page"] = strawberry.field(
            resolver=_resolve_current_page, graphql_type=Optional[int]
        )
        namespace["page_count"] = strawberry.field(
            resolver=_resolve_page_count, graphql_type=Optional[int]
        )

    connection_cls = type(connection_name, (), namespace)
    connection_cls = strawberry.type(connection_cls, name=connection_name)
    connection_cls.Edge = edge_cls  # type: ignore[attr-defined]
    return connection_cls


# --------------------------------------------------------------------------- #
# Connection resolution (graphene-django port)                                 #
# --------------------------------------------------------------------------- #


def maybe_queryset(value: Any) -> Any:
    if isinstance(value, Manager):
        return value.get_queryset()
    return value


def resolve_connection_from_iterable(
    iterable: Any,
    args: dict[str, Any],
    max_limit: int | None = RELAY_CONNECTION_MAX_LIMIT,
) -> ConnectionValue:
    """Port of ``DjangoConnectionField.resolve_connection``."""
    args = dict(args)

    # Remove the offset parameter and convert it to an after cursor
    # (1-based offset, exactly like graphene-django).
    offset = args.pop("offset", None)
    after = args.get("after")
    if offset:
        if after:
            offset += cursor_to_offset(after) + 1  # type: ignore[operator]
        args["after"] = offset_to_cursor(offset - 1)

    iterable = maybe_queryset(iterable)

    if isinstance(iterable, QuerySet):
        array_length = iterable.count()
    else:
        array_length = len(iterable)

    slice_start = min(
        get_offset_with_default(args.get("after"), -1) + 1,
        array_length,
    )
    array_slice_length = array_length - slice_start

    if (
        max_limit is not None
        and args.get("first", None) is None
        and args.get("last", None) is None
    ):
        args["first"] = max_limit

    connection = connection_from_array_slice(
        iterable[slice_start:],
        args,
        slice_start=slice_start,
        array_length=array_length,
        array_slice_length=array_slice_length,
        # ``connection_from_array_slice`` invokes this as
        # ``connection_type(edges=..., pageInfo=...)`` (graphql-relay's camelCase
        # kwarg); the lambda adapts the ``pageInfo`` kwarg onto
        # ``ConnectionValue``'s ``page_info`` positional — passing
        # ``ConnectionValue`` directly would raise on the unexpected kwarg.
        connection_type=lambda edges, pageInfo: ConnectionValue(  # type: ignore[arg-type]
            edges, pageInfo
        ),
        edge_type=EdgeValue,
        page_info_type=lambda startCursor, endCursor, hasPreviousPage, hasNextPage: (  # type: ignore[arg-type]
            PageInfo(
                has_next_page=hasNextPage,
                has_previous_page=hasPreviousPage,
                start_cursor=startCursor,
                end_cursor=endCursor,
            )
        ),
    )
    connection.iterable = iterable  # type: ignore[attr-defined]
    connection.length = array_length  # type: ignore[attr-defined]
    return connection  # type: ignore[return-value]


def resolve_django_connection(
    *,
    resolved: Any,
    info: Any,
    args: dict[str, Any],
    node_type_name: str,
    default_manager: Manager | None = None,
    filterset_class: type | None = None,
    filter_args: dict[str, str] | None = None,
    max_limit: int | None = RELAY_CONNECTION_MAX_LIMIT,
) -> ConnectionValue:
    """Port of ``DjangoConnectionField.connection_resolver`` +
    ``DjangoFilterConnectionField.resolve_queryset``.

    ``args`` maps **filter/relay argument names** (django-filter filter names
    for filterset args, i.e. snake/dunder case) to provided values; absent
    arguments must be omitted by the caller (strawberry ``UNSET`` stripped).
    ``filter_args`` maps filter names to themselves for filterset-backed
    fields (which subset of ``args`` belongs to the filterset).
    """
    first = args.get("first")
    last = args.get("last")
    offset = args.get("offset")
    before = args.get("before")

    if max_limit:
        if first:
            assert first <= max_limit, (
                "Requesting {} records on the `{}` connection exceeds the "
                "`first` limit of {} records."
            ).format(first, info.field_name, max_limit)
            args["first"] = min(first, max_limit)

        if last:
            assert last <= max_limit, (
                "Requesting {} records on the `{}` connection exceeds the "
                "`last` limit of {} records."
            ).format(last, info.field_name, max_limit)
            args["last"] = min(last, max_limit)

    if offset is not None:
        assert before is None, (
            "You can't provide a `before` value at the same time as an "
            "`offset` value to properly paginate the `{}` connection."
        ).format(info.field_name)

    iterable = resolved
    if iterable is None:
        if default_manager is None:
            iterable = []
        else:
            iterable = default_manager
    iterable = maybe_queryset(iterable)

    if isinstance(iterable, QuerySet):
        iterable = maybe_queryset(
            apply_type_get_queryset(node_type_name, iterable, info)
        )

    if filterset_class is not None and isinstance(iterable, QuerySet):
        filter_kwargs = {
            name: value
            for name, value in args.items()
            if filter_args is not None and name in filter_args
        }
        filterset = filterset_class(
            data=filter_kwargs, queryset=iterable, request=info.context
        )
        if filterset.is_valid():
            iterable = filterset.qs
        else:
            from django.core.exceptions import ValidationError

            raise ValidationError(filterset.form.errors.as_json())

    relay_args = {
        key: value
        for key, value in args.items()
        if key in ("first", "last", "before", "after", "offset")
    }
    return resolve_connection_from_iterable(iterable, relay_args, max_limit=max_limit)


def resolve_django_list(root: Any, info: Any, value: Any, node_type_name: str) -> Any:
    """Port of ``DjangoListField.list_resolver`` — applies the node type's
    ``get_queryset`` hook to manager/queryset results."""
    queryset = maybe_queryset(value)
    if isinstance(queryset, QuerySet):
        queryset = maybe_queryset(
            apply_type_get_queryset(node_type_name, queryset, info)
        )
    return queryset


def resolve_visible_fk(
    root: Any, info: Any, fk_id_attr: str, node_type_name: str
) -> Any:
    """Resolve a to-one FK field through the target type's visibility hook.

    Ports graphene-django's ``convert_field_to_djangomodel`` behaviour: an
    auto-generated FK / 1:1 field whose target ``DjangoObjectType`` overrode
    ``get_queryset`` was resolved via ``target.get_node(info, fk_pk)`` →
    ``get_queryset(...).get(pk)``, i.e. **permission-filtered per row**,
    resolving to ``None`` when the FK target was not visible to the caller.

    Strawberry's stock getattr resolver skips that filter — the connection /
    list / relay-node paths funnel through ``apply_type_get_queryset`` but a
    plain ``foo: T = strawberry.field(...)`` singular FK field does not — so
    such a field would leak the target row's fields across a permission
    boundary (e.g. an ``AnnotationType.corpus`` pointing at a private corpus,
    or a ``CorpusReferenceType.targetDocument`` in another corpus). This helper
    reinstates the target type's visibility filter.

    ``fk_id_attr`` is the raw id column (e.g. ``"corpus_id"``) so the pk is
    read off the already-loaded row without a DB hit. Returns ``None`` for a
    missing/invisible target — only valid on a **nullable** FK field — or a
    malformed stored id.

    Hook precedence: ``entry.get_node_for_fk`` (if registered) beats
    ``entry.get_node`` beats ``entry.get_queryset``. The two ``get_node*``
    hooks exist separately because the singular ``xxx(id:)`` / relay
    ``node(id:)`` lookup (``get_node_from_global_id``, which only ever reads
    ``get_node``) and FK traversal (here) can have different per-request
    caching requirements for the same target type — see ``register_type``.
    """
    fk_pk = getattr(root, fk_id_attr, None)
    if fk_pk is None:
        return None
    entry = _TYPE_REGISTRY.get(node_type_name)
    if entry is None or entry.model is None:
        # Unregistered / non-model target — fall back to the plain attribute.
        return getattr(
            root, fk_id_attr[:-3] if fk_id_attr.endswith("_id") else fk_id_attr, None
        )
    try:
        if entry.get_node_for_fk is not None:
            # FK-traversal-specific hook — safe to cache per-request even
            # for types (like ``CorpusType``) whose singular ``get_node``
            # must stay uncached. See ``register_type``'s docstring.
            return entry.get_node_for_fk(info, fk_pk)
        if entry.get_node is not None:
            # Permission-aware hook (e.g. ``BaseService.get_or_none``), which
            # engages the request-scoped permission cache when passed the
            # request via ``info.context``.
            return entry.get_node(info, fk_pk)
        if entry.get_queryset is not None:
            queryset = apply_type_get_queryset(
                node_type_name, entry.model._default_manager.get_queryset(), info
            )
            return queryset.filter(pk=fk_pk).first()
        # No visibility hook on the target — parity with graphene's unfiltered
        # default resolver.
        return entry.model._default_manager.filter(pk=fk_pk).first()
    except (ValueError, TypeError, OverflowError):
        return None
