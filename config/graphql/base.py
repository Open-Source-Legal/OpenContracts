import inspect
import logging
import traceback
from abc import ABC

import django.db.models
import graphene
from django.core.exceptions import PermissionDenied
from graphene.relay import Node
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id, to_global_id

from opencontractserver.shared.resolvers import resolve_single_oc_model_from_id
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class OpenContractsNode(Node):
    class Meta:
        name = "Node"

    @classmethod
    def get_node_from_global_id(cls, info, global_id, only_type=None):

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
        return resolve_single_oc_model_from_id(
            model_type=graphene_type._meta.model,
            user=info.context.user,
            graphql_id=global_id,
        )


class CountableConnection(graphene.relay.Connection):
    class Meta:
        abstract = True

    total_count = graphene.Int()

    def resolve_total_count(root, info):
        return len(root.iterable)  # And no, root.iterable.count() did not work for me.


class DRFDeletion(graphene.Mutation):
    class IOSettings(ABC):
        lookup_field = "id"
        # Expect that the concrete mutation class defines the model attribute.
        model = None

    class Arguments:
        id = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @classmethod
    @login_required
    def mutate(cls, root, info, *args, **kwargs):
        logger.info(f"DRFDeletion: Processing {cls.__name__} mutation")

        # Extract the global id from arguments
        global_id = kwargs.get(cls.IOSettings.lookup_field)
        if not global_id:
            logger.error("DRFDeletion: Missing ID parameter")
            return cls(ok=False, message="Error: missing ID parameter")

        # Convert global ID to Django ID
        try:
            django_id = from_global_id(global_id)[1]
        except Exception:
            logger.error("DRFDeletion: Invalid global ID", exc_info=True)
            return cls(ok=False, message="Error: invalid ID parameter")

        logger.info(
            f"DRFDeletion: Looking up {cls.IOSettings.model.__name__} with ID {django_id}"
        )
        try:
            obj = cls.IOSettings.model.objects.get(pk=django_id)
        except cls.IOSettings.model.DoesNotExist:
            logger.warning(
                f"DRFDeletion: {cls.IOSettings.model.__name__} with ID {django_id} not found"
            )
            raise Exception(
                f"{cls.IOSettings.model.__name__} with ID {django_id} not found"
            )

        # Check for user lock (if applicable)
        if hasattr(obj, "user_lock") and obj.user_lock is not None:
            if info.context.user.id != obj.user_lock_id:
                logger.warning(
                    f"DRFDeletion: Object is locked by {obj.user_lock.username}"
                )
                raise PermissionDenied(f"Object is locked by {obj.user_lock.username}")
        logger.info("DRFDeletion: Object not locked or locked by current user")

        # Instead of manual permission checking, call our integrated delete_as() method.
        try:
            obj.delete_as(info.context.user)
        except PermissionDenied as e:
            logger.warning(f"DRFDeletion: Permission error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"DRFDeletion: Error during deletion: {str(e)}", exc_info=True)
            raise

        logger.info(
            f"DRFDeletion: Successfully deleted {obj.__class__.__name__} {django_id}"
        )
        return cls(ok=True, message="Success!")


class DRFMutation(graphene.Mutation):
    class IOSettings(ABC):
        # List of fields that need to be converted from global IDs.
        pk_fields: list[str | int] = []
        lookup_field = "id"
        # The Django model to work with.
        model: django.db.models.Model = None
        # The corresponding Graphene DjangoObjectType.
        graphene_model = None
        # The DRF serializer class for this model.
        serializer = None

    class Arguments:
        # You can extend this as needed.
        pass

    ok = graphene.Boolean()
    message = graphene.String()
    obj_id = graphene.ID()

    @classmethod
    @login_required
    def mutate(cls, root, info, *args, **kwargs):
        ok = False
        obj_id = None
        message = "Error: unknown problem occurred"
        try:
            # Ensure we have a user in context.
            if info.context.user:
                logger.info(f"User id: {info.context.user.id}")
                # Pass creator id to the serializer (if needed).
                kwargs["creator"] = info.context.user.id
            else:
                raise ValueError("No user in this request...")

            serializer_class = cls.IOSettings.serializer

            # Normalize primary key fields (if any) from global to Django IDs.
            if hasattr(cls.IOSettings, "pk_fields"):
                for pk_field in cls.IOSettings.pk_fields:
                    if pk_field in kwargs:
                        if isinstance(kwargs[pk_field], list):
                            kwargs[pk_field] = [
                                from_global_id(x)[1] for x in kwargs[pk_field]
                            ]
                        else:
                            kwargs[pk_field] = from_global_id(kwargs[pk_field])[1]

            # UPDATE branch: lookup_field provided means update.
            if cls.IOSettings.lookup_field in kwargs:
                django_id = from_global_id(kwargs.get(cls.IOSettings.lookup_field))[1]
                logger.info(
                    f"Looking up {cls.IOSettings.model.__name__} with ID {django_id}"
                )
                try:
                    obj = cls.IOSettings.model.objects.get(pk=django_id)
                except cls.IOSettings.model.DoesNotExist:
                    logger.warning(
                        f"{cls.IOSettings.model.__name__} with ID {django_id} not found"
                    )
                    raise Exception(
                        f"{cls.IOSettings.model.__name__} with ID {django_id} not found"
                    )

                logger.info(f"Retrieved object: {obj}")

                # Check if the object is locked by another user.
                if hasattr(obj, "user_lock") and obj.user_lock is not None:
                    if info.context.user.id != obj.user_lock_id:
                        raise PermissionDenied(
                            f"Object is locked by {obj.user_lock.username}. Cannot be updated by another user."
                        )
                # Check for backend lock.
                if hasattr(obj, "backend_lock") and obj.backend_lock:
                    raise PermissionDenied(
                        "This object has been locked by the backend for processing. You cannot edit it at the moment."
                    )

                # Verify update permission using our integrated permission logic.
                if not user_has_permission_for_obj(
                    info.context.user,
                    obj,
                    PermissionTypes.UPDATE,
                    include_group_permissions=True,
                ):
                    raise PermissionDenied(
                        "You do not have permission to modify this object"
                    )

                # Use the DRF serializer to update the object.
                serializer_instance = serializer_class(obj, data=kwargs, partial=True)
                serializer_instance.is_valid(raise_exception=True)
                # Call the serializer's update() method manually.
                updated_obj = serializer_instance.update(
                    obj, serializer_instance.validated_data
                )
                # Now enforce permissioned saving using our integrated save_as() method.
                updated_obj.save_as(info.context.user)
                ok = True
                message = "Success"
                obj_id = to_global_id(
                    cls.IOSettings.graphene_model._meta.name, updated_obj.id
                )
                logger.info("Succeeded updating object")
            else:
                # CREATE branch.
                serializer_instance = serializer_class(data=kwargs)
                serializer_instance.is_valid(raise_exception=True)
                new_obj = serializer_instance.create(serializer_instance.validated_data)
                # Use our integrated save_as() to enforce create permission.
                new_obj.save_as(info.context.user)
                # Assign full permissions (ALL) for new objects.
                set_permissions_for_obj_to_user(
                    info.context.user, new_obj, [PermissionTypes.ALL]
                )
                ok = True
                message = "Success"
                obj_id = to_global_id(
                    cls.IOSettings.graphene_model._meta.name, new_obj.id
                )
                logger.info("Succeeded creating object")
        except Exception as e:
            logger.error(traceback.format_exc())
            message = f"Mutation failed due to error: {e}"
            raise

        return cls(ok=ok, message=message, obj_id=obj_id)
