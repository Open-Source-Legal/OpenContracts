"""
Migrate structural annotations from StructuralAnnotationSet to Document.

This data migration moves all annotations and relationships that currently
point to a structural_set to instead point directly to their document.

The structural=True flag is preserved, allowing us to identify which
annotations were originally structural.
"""

from django.db import migrations


def migrate_structural_to_documents(apps, schema_editor):
    """
    For each Document with a structural_annotation_set:
    1. Update all structural annotations to point to document instead of set
    2. Update all structural relationships to point to document instead of set
    """
    Document = apps.get_model("documents", "Document")
    Annotation = apps.get_model("annotations", "Annotation")
    Relationship = apps.get_model("annotations", "Relationship")

    # Get all documents with structural_annotation_set
    documents_with_sets = Document.objects.filter(
        structural_annotation_set__isnull=False
    ).values_list("id", "structural_annotation_set_id")

    for doc_id, struct_set_id in documents_with_sets:
        # Move annotations from structural_set to document
        Annotation.objects.filter(structural_set_id=struct_set_id).update(
            document_id=doc_id,
            structural_set_id=None,
        )

        # Move relationships from structural_set to document
        Relationship.objects.filter(structural_set_id=struct_set_id).update(
            document_id=doc_id,
            structural_set_id=None,
        )


def reverse_migration(apps, schema_editor):
    """
    Reverse: Move structural=True annotations back to structural sets.

    This recreates StructuralAnnotationSet instances for documents that have
    structural annotations, and moves those annotations to the new sets.
    """
    Document = apps.get_model("documents", "Document")
    Annotation = apps.get_model("annotations", "Annotation")
    Relationship = apps.get_model("annotations", "Relationship")
    StructuralAnnotationSet = apps.get_model("annotations", "StructuralAnnotationSet")
    User = apps.get_model("users", "User")

    # Get system user for creator
    system_user = User.objects.filter(is_superuser=True).first()

    # Find all documents with structural annotations
    doc_ids_with_structural = (
        Annotation.objects.filter(structural=True, document__isnull=False)
        .values_list("document_id", flat=True)
        .distinct()
    )

    for doc_id in doc_ids_with_structural:
        doc = Document.objects.get(id=doc_id)

        # Create a new structural annotation set
        content_hash = f"{doc.pdf_file_hash or 'doc'}_{doc_id}_restored"
        struct_set = StructuralAnnotationSet.objects.create(
            content_hash=content_hash,
            creator=system_user,
            page_count=doc.page_count,
            pawls_parse_file=doc.pawls_parse_file.name if doc.pawls_parse_file else None,
            txt_extract_file=doc.txt_extract_file.name if doc.txt_extract_file else None,
        )

        # Move structural annotations to the set
        Annotation.objects.filter(document_id=doc_id, structural=True).update(
            structural_set_id=struct_set.id,
            document_id=None,
        )

        # Move structural relationships to the set
        Relationship.objects.filter(document_id=doc_id, structural=True).update(
            structural_set_id=struct_set.id,
            document_id=None,
        )

        # Link document to the set
        doc.structural_annotation_set = struct_set
        doc.save(update_fields=["structural_annotation_set"])


class Migration(migrations.Migration):

    dependencies = [
        ("annotations", "0057_remove_structural_set_constraints"),
        ("documents", "0029_alter_documentrelationshipuserobjectpermission_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(
            migrate_structural_to_documents,
            reverse_code=reverse_migration,
        ),
    ]
