"""Add ``preferred_llm`` override to AgentConfiguration.

When set, this overrides the corpus's ``preferred_llm`` for invocations
driven by this agent (e.g. a corpus uses Opus by default but a
summarizer agent in the same corpus uses Haiku). Null means "fall back
to the corpus default", preserving pre-feature behaviour for every
existing agent row.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0013_backfill_and_tighten_agent_slug"),
    ]

    operations = [
        migrations.AddField(
            model_name="agentconfiguration",
            name="preferred_llm",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Optional pydantic-ai model spec to use when this agent "
                    "runs (e.g. 'anthropic:claude-haiku-4-5'). Overrides "
                    "Corpus.preferred_llm. Empty falls back to the corpus "
                    "default, then settings."
                ),
                max_length=128,
                null=True,
            ),
        ),
    ]
