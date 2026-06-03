"""Add durable ``plan`` + ``memory`` state to ResearchReport.

These back the agentic context-management surface: a living high-level
plan that is re-injected into the system prompt every run, and a
key->entry memory store the agent writes to offload content beyond the
context window. Both survive context compaction and worker restarts so a
long-running research job can recover after a crash.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("research", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="researchreport",
            name="plan",
            field=models.TextField(
                blank=True,
                help_text=(
                    "The agent's living high-level plan. Re-injected into the "
                    "system prompt at the start of every run so the original "
                    "task and strategy survive context compaction and worker "
                    "restarts."
                ),
            ),
        ),
        migrations.AddField(
            model_name="researchreport",
            name="memory",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Durable key->entry memory store the agent writes to "
                    "offload content beyond the context window. Each entry is "
                    "{content, updated_at}. Survives compaction and worker "
                    "restarts."
                ),
            ),
        ),
    ]
