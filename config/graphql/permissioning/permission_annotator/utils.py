from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import AbstractUser

from config.graphql.permissioning.permission_annotator.middleware import (
    get_permissions_for_user_on_model_in_app,
)
from opencontractserver.shared.Models import BaseOCModel

logger = logging.getLogger(__name__)


def generate_permission_annotations_dict(
    model_django_type: type[BaseOCModel], user: AbstractUser | None
) -> Any:

    model_name = model_django_type._meta.model_name or ""
    app_name = model_django_type._meta.app_label

    return get_permissions_for_user_on_model_in_app(app_name, model_name, user)
