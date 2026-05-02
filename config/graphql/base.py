import inspect
import logging
import traceback
from abc import ABC
from collections.abc import Sequence
from typing import Any, ClassVar, Optional

import django.db.models
import graphene
from graphene.relay import Node
from graphene_django import DjangoObjectType
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id, to_global_id
from rest_framework import serializers

from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


def _require_io_setting(mutation_cls: type, name: str) -> Any:
    """Raise ``NotImplementedError`` if ``cls.IOSettings.<name>`` is missing or ``None``."""
    io_settings = getattr(mutation_cls, "IOSettings", None)
    if io_settings is None:
        raise NotImplementedError(
            f"{mutation_cls.__name__} must define an IOSettings class."
        )
    value = getattr(io_settings, name, None)
    if value is None:
        raise NotImplementedError(
            f"{mutation_cls.__name__}.IOSettings.{name} must be set by the "
            f"subclass."
        )
    return value


class OpenContractsNode(Node):
    class Meta:
        name = "Node"

    @classmethod
    def get_node_from_global_id(
        cls, info: Any, global_id: str, only_type: Any | None = None
    ) -> Any:

        _type, _id = from_global_id(global_id)

        graphene_type = info.schema.get_type(_type)
        if graphene_type is None:
            raise Exception(f'Relay Node "{_type}" not found in schema')

        graphene_type = graphene_type.graphene_type
        logger.info(f"Graphene type: {graphene_type}")

        if only_type:
            assert (
                graphene_type == only_type
            ), f"Must receive a {only_type._meta.name} id."

        # We make sure the ObjectType implements the "Node" interface, parent of
        # this subclass of Node. Using inspect module: https://www.geeksforgeeks.org/inspect-module-in-python/
        if inspect.getmro(cls)[1] not in graphene_type._meta.interfaces:
            raise Exception(
                f'ObjectType "{_type}" does not implement the "{super()}" interface.'
            )

        # Here's where we replace the base Graphene Relay get_node code with a custom
        # resolver that is permission-aware... it was kind of a pain in the @ss to figure this out...
        _, pk = from_global_id(global_id)
        return graphene_type._meta.model.objects.visible_to_user(info.context.user).get(
            id=pk
        )


class CountableConnection(graphene.relay.Connection):
    class Meta:
        abstract = True

    total_count = graphene.Int()

    def resolve_total_count(root, info, **kwargs) -> Any:
        if isinstance(root.iterable, django.db.models.QuerySet):
            return root.iterable.count()
        else:
            return len(root.iterable)


class DRFDeletion(graphene.Mutation):
    class IOSettings(ABC):
        lookup_field: ClassVar[str] = "id"
        model: ClassVar[Optional[type[django.db.models.Model]]] = None

    class Arguments:
        id = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()

    @classmethod
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(cls, root, info, *args, **kwargs) -> "DRFDeletion":

        # Unlike ``DRFMutation.mutate`` below, this method intentionally does
        # NOT wrap the body in ``except Exception``. Errors (including the
        # ``NotImplementedError`` from ``_require_io_setting`` and the
        # ``ValueError`` for missing lookup args) propagate to the GraphQL
        # framework as raw execution errors.
        ok = False

        model = _require_io_setting(cls, "model")
        lookup_field = cls.IOSettings.lookup_field
        lookup_value = kwargs.get(lookup_field)
        if lookup_value is None:
            raise ValueError(
                f"'{lookup_field}' is required to identify the object to delete."
            )
        id = from_global_id(lookup_value)[1]
        # Filter through visible_to_user() to prevent IDOR -- returns same
        # DoesNotExist error whether object is missing or user lacks access.
        obj = model.objects.visible_to_user(info.context.user).get(pk=id)

        # if there's a user lock, only the lock holder (or superuser) can proceed
        if hasattr(obj, "user_lock") and obj.user_lock is not None:
            if info.context.user.id != obj.user_lock_id:
                raise PermissionError(
                    "Specified object is locked by another user. Cannot be " "deleted."
                )

        # NOTE - we are explicitly ALLOWING deletion of something that's been locked by the backend. If an important
        # or processing job goes sour, we want a frontend user to be able to intervene and delete it without
        # needing someone to drop in the admin dash.

        # Check user permissions
        if not user_has_permission_for_obj(
            info.context.user,
            obj,
            PermissionTypes.DELETE,
            include_group_permissions=True,
        ):
            raise PermissionError(
                "You do not have sufficient permissions to delete requested object"
            )

        obj.delete()
        ok = True
        message = "Success!"

        return cls(ok=ok, message=message)


class DRFMutation(graphene.Mutation):
    class IOSettings(ABC):
        # Frozen default — subclasses override with their own list/tuple.
        # Using a tuple here avoids the shared-mutable-default footgun.
        pk_fields: ClassVar[Sequence[str]] = ()
        lookup_field: ClassVar[str] = "id"
        model: ClassVar[Optional[type[django.db.models.Model]]] = None
        graphene_model: ClassVar[Optional[type[DjangoObjectType]]] = None
        serializer: ClassVar[Optional[type[serializers.Serializer]]] = None

    class Arguments:
        pass

    ok = graphene.Boolean()
    message = graphene.String()
    obj_id = graphene.ID()

    @staticmethod
    def format_validation_error(ve: serializers.ValidationError) -> str:
        """Surface validation errors with clean formatting.

        ``str(ValidationError)`` renders as
        ``[ErrorDetail(string='...', code='invalid')]`` which leaks internal
        structure.  This method produces a human-readable string instead.
        """
        if isinstance(ve.detail, dict):
            errors = "; ".join(
                f"{field}: {', '.join(str(e) for e in errs)}"
                for field, errs in ve.detail.items()
            )
        elif isinstance(ve.detail, list):
            errors = "; ".join(str(e) for e in ve.detail)
        else:
            errors = str(ve.detail)
        return f"Mutation failed due to error: {errors}"

    @classmethod
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(cls, root, info, *args, **kwargs) -> "DRFMutation":

        ok = False
        obj_id = None

        try:
            logger.info("Test if context has user")
            if info.context.user:
                logger.info(f"User id: {info.context.user.id}")
                # We're using the DRF Serializers to build data and edit / save objs
                # We want to pass an ID into the creator field, not the user obj
                kwargs["creator"] = info.context.user.id
            else:
                logger.info("No user")
                raise ValueError("No user in this request...")

            logger.info(f"DRFMutation - kwargs: {kwargs}")
            serializer = _require_io_setting(cls, "serializer")
            model = _require_io_setting(cls, "model")
            # ``graphene_model`` is the class itself; ``__name__`` is the GraphQL
            # type name (e.g. ``"CorpusType"``). ``__class__.__name__`` would
            # return the metaclass name (``"SubclassWithMeta_Meta"``) which is
            # the bug this PR fixes — kept dereferenced as ``__name__`` below.
            graphene_model = _require_io_setting(cls, "graphene_model")

            if hasattr(cls.IOSettings, "pk_fields"):
                for pk_field in cls.IOSettings.pk_fields:
                    if pk_field in kwargs:
                        raw_value = kwargs[pk_field]
                        if isinstance(raw_value, list):
                            kwargs[pk_field] = [
                                from_global_id(global_id)[1] for global_id in raw_value
                            ]
                        else:
                            logger.info(f"pk field is: {raw_value}")
                            kwargs[pk_field] = from_global_id(raw_value)[1]

            # Check if lookup_field exists in IOSettings and if it's in kwargs
            # This allows create mutations to work without requiring lookup_field
            is_update = (
                hasattr(cls.IOSettings, "lookup_field")
                and cls.IOSettings.lookup_field in kwargs
            )

            if is_update:
                logger.info("Lookup_field specified - update")
                # Filter through visible_to_user() to prevent IDOR --
                # returns same DoesNotExist whether missing or no access.
                obj = model.objects.visible_to_user(info.context.user).get(
                    pk=from_global_id(kwargs[cls.IOSettings.lookup_field])[1]
                )

                logger.info(f"Retrieved obj: {obj}")

                # Check the object isn't locked by another user
                if hasattr(obj, "user_lock") and obj.user_lock is not None:
                    if info.context.user.id != obj.user_lock_id:
                        raise PermissionError(
                            "Specified object is locked by another user. Cannot be "
                            "updated / edited."
                        )

                # Check that the object hasn't been locked by the backend
                if hasattr(obj, "backend_lock") and obj.backend_lock:
                    raise PermissionError(
                        "This object has been locked by the backend for processing. You cannot edit "
                        "it at the moment."
                    )

                # Check that the user has update permissions
                if not user_has_permission_for_obj(
                    info.context.user,
                    obj,
                    PermissionTypes.UPDATE,
                    include_group_permissions=True,
                ):
                    raise PermissionError(
                        "You do not have permission to modify this object"
                    )

                obj_serializer = serializer(obj, data=kwargs, partial=True)
                obj_serializer.is_valid(raise_exception=True)
                obj_serializer.save()
                ok = True
                message = "Success"
                obj_id = to_global_id(graphene_model.__name__, obj.id)
                logger.info("Succeeded updating obj")

            else:
                # Create operation
                logger.info("No lookup_field specified or not in kwargs - create")
                logger.info(f"Obj kwargs: {kwargs}")
                obj_serializer = serializer(data=kwargs)
                obj_serializer.is_valid(raise_exception=True)
                obj = obj_serializer.save()
                logger.info(f"Created obj with id: {obj.id}")

                # If we created new obj... give user proper permissions
                set_permissions_for_obj_to_user(
                    info.context.user, obj, [PermissionTypes.CRUD]
                )
                logger.info(f"Permissioned obj for user: {info.context.user.id}")

                ok = True
                message = "Success"
                obj_id = to_global_id(graphene_model.__name__, obj.id)

        except serializers.ValidationError as ve:
            logger.warning(f"Validation error in mutation: {ve.detail}")
            message = cls.format_validation_error(ve)

        except Exception:
            logger.error(traceback.format_exc())
            message = "Mutation failed due to an internal error."

        return cls(ok=ok, message=message, obj_id=obj_id)
