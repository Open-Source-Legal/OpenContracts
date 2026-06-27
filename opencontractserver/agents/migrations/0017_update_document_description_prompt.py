# Data migration: sync the seeded "Document Description Updater" template's
# task instructions to the current prompt.
#
# The template is seeded once (agents/0010) via the idempotent
# ``create_default_action_templates`` helper, which SKIPS any template that
# already exists by name. So edits to ``DOCUMENT_DESCRIPTION_INSTRUCTIONS`` in
# ``corpuses/template_seeds.py`` never reach already-seeded databases on their
# own — they must be propagated here. Mirrors agents/0016 (CAML writer prompt).
#
# This run rewrites the prompt to lead with the document's subject matter
# (goods, services, rights, obligations) instead of restating its type/title,
# and to drop the "This document is …" lead-in.

from django.db import migrations


def update_document_description_prompt(apps, schema_editor):  # pragma: no cover
    """Set the Document Description Updater template's task instructions.

    Idempotent: only writes when the stored prompt differs from the canonical
    constant, so re-running (or running after a fresh seed that already used the
    new value) is a no-op.
    """
    from opencontractserver.corpuses.template_seeds import (
        DOCUMENT_DESCRIPTION_INSTRUCTIONS,
    )

    CorpusActionTemplate = apps.get_model("corpuses", "CorpusActionTemplate")
    tmpl = CorpusActionTemplate.objects.filter(
        name="Document Description Updater"
    ).first()
    if tmpl is None:
        return
    if tmpl.task_instructions != DOCUMENT_DESCRIPTION_INSTRUCTIONS:
        tmpl.task_instructions = DOCUMENT_DESCRIPTION_INSTRUCTIONS
        tmpl.save(update_fields=["task_instructions"])


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0016_update_caml_article_writer_prompt"),
    ]

    operations = [
        migrations.RunPython(
            update_document_description_prompt, migrations.RunPython.noop
        ),
    ]
