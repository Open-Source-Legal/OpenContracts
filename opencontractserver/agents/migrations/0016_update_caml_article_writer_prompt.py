# Data migration: sync the seeded "CAML Article Writer" agent's system prompt
# to the current CAML authoring guide.
#
# The template + agent are seeded once (agents/0011) via the idempotent
# ``create_default_action_templates`` helper, which SKIPS any template that
# already exists by name. So edits to ``CAML_ARTICLE_SYSTEM_INSTRUCTIONS`` in
# ``corpuses/caml_authoring.py`` never reach already-seeded databases on their
# own — they must be propagated here. Mirrors the agents/0012 pattern for the
# default corpus agent.
#
# This run hardens the guide's block-nesting guidance (every ``::::`` block must
# live inside a ``::: chapter``) so the writer stops emitting top-level blocks
# that the renderer leaks as raw text.

from django.db import migrations


def update_caml_writer_prompt(apps, schema_editor):  # pragma: no cover
    """Set the CAML Article Writer agent's instructions to the current guide.

    Idempotent: only writes when the stored prompt differs from the canonical
    constant, so re-running (or running after a fresh seed that already used the
    new value) is a no-op.
    """
    from opencontractserver.corpuses.caml_authoring import (
        CAML_ARTICLE_SYSTEM_INSTRUCTIONS,
    )

    AgentConfiguration = apps.get_model("agents", "AgentConfiguration")
    # The seeder names the agent "<template name> Agent" (template_seeds.py).
    agent = AgentConfiguration.objects.filter(name="CAML Article Writer Agent").first()
    if agent is None:
        return
    if agent.system_instructions != CAML_ARTICLE_SYSTEM_INSTRUCTIONS:
        agent.system_instructions = CAML_ARTICLE_SYSTEM_INSTRUCTIONS
        agent.save(update_fields=["system_instructions"])


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0015_create_location_tagger_agent"),
    ]

    operations = [
        migrations.RunPython(update_caml_writer_prompt, migrations.RunPython.noop),
    ]
