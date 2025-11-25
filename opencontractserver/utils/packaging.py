from __future__ import annotations

import base64
import logging
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.types.dicts import (
    OpenContractCorpusType,
    OpenContractCorpusV2Type,
    OpenContractsLabelSetType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)

User = get_user_model()


def package_corpus_for_export(
    corpus: Corpus, v2_format: bool = False
) -> OpenContractCorpusType | OpenContractCorpusV2Type | None:
    try:

        if corpus.icon:
            base64_encoded_icon = base64.b64encode(corpus.icon.read()).decode("utf-8")
        else:
            base64_encoded_icon = ""

        base_export = {
            "id": corpus.id,
            "title": corpus.title,
            "description": corpus.description,
            "icon_name": Path(corpus.icon.name).name if corpus.icon else "",
            "icon_data": base64_encoded_icon,
            "creator": corpus.creator.email,
            "label_set": corpus.label_set.id if corpus.label_set else "",
        }

        # Add V2-specific fields if requested
        if v2_format:
            base_export.update(
                {
                    "slug": corpus.slug,
                    "post_processors": corpus.post_processors or [],
                    "preferred_embedder": corpus.preferred_embedder,
                    "corpus_agent_instructions": corpus.corpus_agent_instructions,
                    "document_agent_instructions": corpus.document_agent_instructions,
                    "allow_comments": corpus.allow_comments,
                }
            )

        return base_export

    except Exception as e:
        logger.error(f"Error packaging corpus {corpus.id} for export: {e}")
        return None


def package_label_set_for_export(
    labelset: LabelSet,
) -> OpenContractsLabelSetType | None:
    try:

        if labelset.icon:
            base64_encoded_icon = base64.b64encode(labelset.icon.read()).decode("utf-8")
        else:
            base64_encoded_icon = ""

        return {
            "id": labelset.id,
            "title": labelset.title,
            "description": labelset.description,
            "icon_name": Path(labelset.icon.name).name,
            "icon_data": base64_encoded_icon,
            "creator": labelset.creator.email,
        }

    except Exception:
        return None


def turn_base64_encoded_file_to_django_content_file(
    base64_string: str, filename: str
) -> ContentFile:

    icon_base64_string = base64_string.encode("utf-8")
    icon_data = base64.decodebytes(icon_base64_string)
    icon_file = ContentFile(icon_data, name=filename)
    return icon_file


def unpack_label_set_from_export(
    data: OpenContractsLabelSetType, user: int | User
) -> LabelSet | None:

    label_set = None
    try:
        icon_file = turn_base64_encoded_file_to_django_content_file(
            base64_string=data["icon_data"], filename=data["icon_name"]
        )

        if isinstance(user, str):
            label_set = LabelSet.objects.create(
                icon=icon_file,
                creator_id=user,
                title=data["title"],
                description=data["description"],
            )
        else:
            label_set = LabelSet.objects.create(
                icon=icon_file,
                creator=user,
                title=data["title"],
                description=data["description"],
            )
        set_permissions_for_obj_to_user(user, label_set, [PermissionTypes.ALL])

    except Exception as e:
        logger.error(
            f"unpack_label_set_from_export() - Unable to unpack label_set: {e}"
        )

    return label_set


def unpack_corpus_from_export(
    data: OpenContractCorpusType,
    user: int | User,
    label_set_id: int,
    corpus_id: int | None,
) -> Corpus | None:
    """
    Unpacks corpus (including base64 encoded icon) into a Corpus
    obj in the database. If you pass in a corpus_id, the imported
    corpus details are overwritten into the corpus with corpus_id
    """

    corpus = None
    try:
        icon_base64_string = data["icon_data"].encode("utf-8")
        icon_data = base64.decodebytes(icon_base64_string)
        icon_file = ContentFile(icon_data, name=data["icon_name"])

        # Prepare V2 fields if present
        v2_fields = {}
        if "post_processors" in data:
            v2_fields["post_processors"] = data["post_processors"]
        if "preferred_embedder" in data:
            v2_fields["preferred_embedder"] = data["preferred_embedder"]
        if "corpus_agent_instructions" in data:
            v2_fields["corpus_agent_instructions"] = data["corpus_agent_instructions"]
        if "document_agent_instructions" in data:
            v2_fields["document_agent_instructions"] = data[
                "document_agent_instructions"
            ]
        if "allow_comments" in data:
            v2_fields["allow_comments"] = data["allow_comments"]

        if corpus_id:
            corpus = Corpus.objects.get(id=corpus_id)
            corpus.icon = icon_file
            corpus.title = data["title"]
            corpus.description = data["description"]
            corpus.label_set_id = label_set_id
            # Update V2 fields if present
            for field_name, field_value in v2_fields.items():
                setattr(corpus, field_name, field_value)
            corpus.save()
        else:
            base_fields = {
                "icon": icon_file,
                "title": data["title"],
                "description": data["description"],
                "label_set_id": label_set_id,
            }
            # Add V2 fields if present
            base_fields.update(v2_fields)

            if isinstance(user, str):
                corpus = Corpus.objects.create(
                    creator_id=user,
                    **base_fields,
                )
            else:
                corpus = Corpus.objects.create(
                    creator=user,
                    **base_fields,
                )

        set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.ALL])

    except Exception as e:
        logger.error(f"unpack_corpus_from_export() - Unable to unpack corpus: {e}")

    return corpus
