# Data migration: sync the seeded "Document Description Updater" template's
# task instructions and description to the current values.
#
# The template is seeded once (agents/0010) via the idempotent
# ``create_default_action_templates`` helper, which SKIPS any template that
# already exists by name. So edits to ``DOCUMENT_DESCRIPTION_INSTRUCTIONS`` or
# the template's ``description`` in ``corpuses/template_seeds.py`` never reach
# already-seeded databases on their own — they must be propagated here.
# Mirrors agents/0016 (CAML writer prompt).
#
# This run rewrites the prompt to lead with the document's subject matter
# (goods, services, rights, obligations) instead of restating its type/title,
# and to drop the "This document is …" lead-in.  The UI-visible description is
# updated to match the new behaviour.
#
# Strings are inlined here (not imported from template_seeds) so this migration
# remains a self-contained frozen snapshot: a future rename or move of the
# source constant cannot break ``migrate`` from a clean database.

from django.db import migrations

_TASK_INSTRUCTIONS = (
    "Write ONE concise sentence (about 12-25 words) capturing what this "
    "document is actually about: the specific subject matter -- the goods, "
    "services, rights, obligations, or events it concerns -- and the key "
    "parties involved. Lead with the substance, not the document type or title "
    '(e.g. "Renewal of an agreement with Acme Foods to supply potatoes to city '
    'facilities", not "A renewal agreement titled ..."). Do not begin with '
    '"This document is" or "This is", and do not simply restate the title. '
    "Mention the document or instrument type only as brief context, not the "
    "focus. Use update_document_description to save your result; rewrite any "
    "existing description to meet this bar."
)

_UI_DESCRIPTION = (
    "Reads a newly added document and writes a one-sentence summary "
    "leading with its subject matter and key parties."
)


def update_document_description_prompt(apps, schema_editor):  # pragma: no cover
    """Set the Document Description Updater template's task instructions and description.

    Idempotent: each field is only written when the stored value differs from
    the target, so re-running (or running after a fresh seed that already used
    the new values) is a no-op.
    """
    CorpusActionTemplate = apps.get_model("corpuses", "CorpusActionTemplate")
    tmpl = CorpusActionTemplate.objects.filter(
        name="Document Description Updater"
    ).first()
    if tmpl is None:
        return

    update_fields = []
    if tmpl.task_instructions != _TASK_INSTRUCTIONS:
        tmpl.task_instructions = _TASK_INSTRUCTIONS
        update_fields.append("task_instructions")
    if tmpl.description != _UI_DESCRIPTION:
        tmpl.description = _UI_DESCRIPTION
        update_fields.append("description")
    if update_fields:
        tmpl.save(update_fields=update_fields)

    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    agent = AgentConfiguration.objects.filter(
        name="Document Description Updater Agent"
    ).first()
    if agent is not None and agent.description != _UI_DESCRIPTION:
        agent.description = _UI_DESCRIPTION
        agent.save(update_fields=["description"])


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0016_update_caml_article_writer_prompt"),
    ]

    operations = [
        migrations.RunPython(
            update_document_description_prompt, migrations.RunPython.noop
        ),
    ]
