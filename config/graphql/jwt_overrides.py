from typing import Any

from graphql_jwt.compat import get_operation_name
from graphql_jwt.settings import jwt_settings


def allow_any(info, **kwargs) -> Any:
    try:
        operation_name = get_operation_name(info.operation.operation).title()
        operation_type = info.schema.get_type(operation_name)

        if hasattr(operation_type, "fields"):

            field = operation_type.fields.get(info.field_name)

            if field is None:
                return False

        else:
            return False

        graphene_type = getattr(field.type, "graphene_type", None)

        return graphene_type is not None and issubclass(
            graphene_type, tuple(jwt_settings.JWT_ALLOW_ANY_CLASSES)
        )
    except Exception:
        return False
