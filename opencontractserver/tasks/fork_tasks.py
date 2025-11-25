import logging
from pathlib import Path
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from config import celery_app
from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

User = get_user_model()


@celery_app.task()
def fork_corpus(
    new_corpus_id: str,
    doc_ids: list[str],
    label_set_id: str,
    annotation_ids: list[str],
    user_id: str,
) -> Optional[str]:

    logger.info(
        f"Start fork_corpus -----\n\tnew_corpus_id: {new_corpus_id}\n\tdoc_ids: "
        f"{doc_ids}\n\tannotation_ids: {annotation_ids}\n\tuser_id: {user_id}"
    )

    # We need reference to corpus model so we can unlock it upon completion
    corpus = Corpus.objects.get(pk=new_corpus_id)

    with transaction.atomic():

        try:

            label_map = {}
            doc_map = {}
            label_ids = []

            try:
                # Create the label set copy first.
                old_label_set = LabelSet.objects.get(pk=label_set_id)
                label_ids = list(
                    old_label_set.annotation_labels.all().values_list("id", flat=True)
                )

                label_set = LabelSet(
                    creator_id=user_id,
                    title=f"[FORK] {old_label_set.title}",
                    description=old_label_set.description,
                )
                label_set.save()
                logger.info(f"Cloned labelset: {label_set}")

                # If there's an icon... copy it to a new file
                if old_label_set.icon:
                    icon_obj = default_storage.open(old_label_set.icon.name)
                    icon_file = ContentFile(icon_obj.read())
                    logger.info(
                        f"Label set icon name: {Path(old_label_set.icon.name).name}"
                    )
                    label_set.icon.save(Path(old_label_set.icon.name).name, icon_file)
                    label_set.save()

            except Exception as e:
                logger.error(f"ERROR forking label_set for corpus {new_corpus_id}: {e}")
                raise e

            # Get old label objs (can't just get these earlier as manytomany values are cleared by django when we call
            # clear(), it seems)
            # Copy labels and add new labels to label_set
            logger.info("Cloning labels")
            try:
                for old_label in AnnotationLabel.objects.filter(pk__in=label_ids):

                    try:
                        new_label = AnnotationLabel(
                            creator_id=user_id,
                            label_type=old_label.label_type,
                            color=old_label.color,
                            description=old_label.description,
                            icon=old_label.icon,
                            text=old_label.text,
                        )
                        new_label.save()

                        # store map of old id to new id
                        label_map[old_label.id] = new_label.id

                        # Add to new labelset
                        label_set.annotation_labels.add(new_label)

                    except Exception as e:
                        logger.error(
                            f"ERROR - could not fork label for labelset {label_set_id}: {e}"
                        )

                # Save label_set
                label_set.save()

                # Update corpus LabelSet to point to cloned copy of original labelset:
                corpus.label_set = label_set

            except Exception as e:
                logger.error(
                    f"ERROR - could not populate labels for labelset {label_set_id}: {e}"
                )
                raise e

            # logger.info("Cloning documents")
            for document in Document.objects.filter(pk__in=doc_ids):

                try:
                    logger.info(f"Clone document: {document}")
                    old_id = document.pk

                    # First start by copying the document (the procedure below
                    # is a trick to get ORM to copy the Django database obj). Resetting
                    # pk to None will, on save, save a NEW object with old obj properties,
                    # except as modified
                    document.pk = None
                    document.title = f"[FORK] {document.title}"
                    document.creator_id = user_id
                    document.backend_lock = True  # Lock doc while we process stuff
                    document.save()

                    # If there's a text extract file... copy it to a new file
                    if document.txt_extract_file:
                        file_object = default_storage.open(
                            document.txt_extract_file.name
                        )
                        txt_file = ContentFile(file_object.read())
                        document.txt_extract_file.save(f"{document.id}.txt", txt_file)
                        document.save()
                        logger.info("Clone txt layer")

                    # If there's a pawls file... copy it to new file
                    if document.pawls_parse_file:
                        file_object = default_storage.open(
                            document.pawls_parse_file.name
                        )
                        pawls_file = ContentFile(file_object.read())
                        document.pawls_parse_file.save(
                            f"doc_{document.id}.pawls", pawls_file
                        )
                        document.save()
                        logger.info("Cloned pawls file")

                    # Unlock the document.
                    document.backend_lock = False
                    document.save()

                    set_permissions_for_obj_to_user(
                        user_id, document, [PermissionTypes.CRUD]
                    )

                    corpus.add_document(document=document, user=user_id)

                    # Store map of old id to new id
                    doc_map[old_id] = document.pk

                except Exception as e:
                    logger.error(f"ERROR - could not fork document {document}: {e}")
                    raise e

            # Save updated corpus with docs and new LabelSet.
            corpus.save()

            logger.info("Start Annotations...")
            logger.info(f"Label map: {label_map}")

            # Fetch annotations and map to new docs, labels and corpus
            for annotation in Annotation.objects.filter(pk__in=annotation_ids):

                try:
                    logger.info(f"Clone annotation: {annotation}")

                    # Copy the annotation, update label and doc object references using our
                    # object maps of old objs to new objs
                    annotation.pk = None
                    annotation.creator_id = user_id
                    annotation.corpus_id = new_corpus_id
                    annotation.document_id = doc_map[annotation.document.id]
                    annotation.annotation_label_id = label_map[
                        annotation.annotation_label.id
                    ]
                    annotation.save()

                    set_permissions_for_obj_to_user(
                        user_id, annotation, [PermissionTypes.CRUD]
                    )

                except Exception as e:
                    logger.error(f"ERROR - could not fork annotation {annotation}: {e}")
                    raise e

            logger.info("Annotations completed...")

            # Unlock the corpus
            corpus.backend_lock = False
            corpus.save()

            return corpus.id

        except Exception as e:
            logger.error(f"ERROR - Unable to fork corpus: {e}")
            corpus.backend_lock = False
            corpus.error = True
            corpus.save()
            return None
