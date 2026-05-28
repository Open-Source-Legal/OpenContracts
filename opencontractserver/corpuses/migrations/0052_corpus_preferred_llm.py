"""Add ``preferred_llm`` and ``created_with_llm`` to Corpus.

Introduces per-corpus LLM model selection (issue: runtime LLM
configuration). ``preferred_llm`` stores a pydantic-ai model spec
(e.g. ``"anthropic:claude-opus-4-6"``) and is mutable — swapping the
LLM does not invalidate any stored data, only influences subsequent
agent invocations. ``created_with_llm`` is an audit-trail field that
never changes after creation, mirroring the existing
``created_with_embedder`` pattern.

The data migration backfills ``created_with_llm`` for existing rows so
the audit trail starts populated. ``preferred_llm`` is intentionally
left null on existing rows — null means "use the global default", which
is the pre-feature behaviour.
"""

from django.conf import settings
from django.db import migrations, models


def backfill_created_with_llm(apps, schema_editor):
    """Stamp the legacy default model on every existing corpus."""
    Corpus = apps.get_model("corpuses", "Corpus")
    default_llm = getattr(settings, "DEFAULT_LLM", None) or getattr(
        settings, "OPENAI_MODEL", "gpt-4o"
    )
    # The DB column stores whatever was active at creation time. For
    # corpuses created before this migration, the legacy default is the
    # closest historical truth we have. Bare model strings (no colon)
    # are still valid — the resolver treats them as openai.
    Corpus.objects.filter(
        models.Q(created_with_llm__isnull=True) | models.Q(created_with_llm="")
    ).update(created_with_llm=default_llm)


class Migration(migrations.Migration):

    dependencies = [
        ("corpuses", "0051_add_manual_batch_trigger"),
    ]

    operations = [
        migrations.AddField(
            model_name="corpus",
            name="preferred_llm",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Preferred pydantic-ai model spec for agents in this "
                    "corpus (e.g. 'anthropic:claude-opus-4-6'). Overridable "
                    "per-agent via AgentConfiguration.preferred_llm. Falls "
                    "back to settings.DEFAULT_LLM / settings.OPENAI_MODEL "
                    "when unset."
                ),
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="corpus",
            name="created_with_llm",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text=(
                    "The LLM model spec that was active when this corpus "
                    "was created. Set automatically and never changes "
                    "(audit trail)."
                ),
                max_length=128,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_created_with_llm,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
