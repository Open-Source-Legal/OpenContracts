"""Initial migration for the deep-research app."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("corpuses", "0049_corpusvote_corpus_upvote_count_and_more"),
        ("conversations", "0018_conversation_memory_curated"),
        ("documents", "0039_add_preferred_enrichers_to_pipeline_settings"),
        ("annotations", "0074_annotation_raw_text_trigram_index"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResearchReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("backend_lock", models.BooleanField(default=False, db_index=True)),
                ("is_public", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(default="Untitled Research Report", max_length=255)),
                ("slug", models.SlugField(blank=True, max_length=160, unique=True)),
                ("prompt", models.TextField(help_text="The user's research task")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("CREATED", "CREATED"),
                            ("QUEUED", "QUEUED"),
                            ("RUNNING", "RUNNING"),
                            ("COMPLETED", "COMPLETED"),
                            ("FAILED", "FAILED"),
                            ("CANCELLED", "CANCELLED"),
                        ],
                        db_index=True,
                        default="QUEUED",
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_progress_at",
                    models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                ("error_message", models.TextField(blank=True)),
                ("cancel_requested", models.BooleanField(default=False)),
                ("max_steps", models.IntegerField(default=60)),
                ("step_count", models.IntegerField(default=0)),
                (
                    "content",
                    models.TextField(
                        blank=True,
                        help_text="Rendered final markdown report with footnote citations",
                    ),
                ),
                (
                    "findings",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Structured scratchpad of agent findings",
                    ),
                ),
                (
                    "citations",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Ordered footnote table: [{footnote, annotation_id, document_id, page, raw_text, similarity_score}]",
                    ),
                ),
                (
                    "tool_call_log",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Per-step tool invocation summary",
                    ),
                ),
                (
                    "model_usage",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Token counts, model/provider, est. cost",
                    ),
                ),
                (
                    "warnings",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Non-fatal warnings (e.g. ['budget_exhausted'])",
                    ),
                ),
                (
                    "corpus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="research_reports",
                        to="corpuses.corpus",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_lock",
                    models.ForeignKey(
                        blank=True,
                        db_index=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="locked_%(class)s_objects",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "conversation",
                    models.ForeignKey(
                        blank=True,
                        help_text="Chat conversation that kicked this off, if any",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="research_reports",
                        to="conversations.conversation",
                    ),
                ),
                (
                    "originating_message",
                    models.ForeignKey(
                        blank=True,
                        help_text="User chat message that triggered this run, if any",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="triggered_research_reports",
                        to="conversations.chatmessage",
                    ),
                ),
                (
                    "source_annotations",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Annotations cited in the final report",
                        related_name="cited_in_research_reports",
                        to="annotations.annotation",
                    ),
                ),
                (
                    "source_documents",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Documents touched (vector-search hits, summaries loaded, etc.)",
                        related_name="cited_in_research_reports",
                        to="documents.document",
                    ),
                ),
            ],
            options={
                "ordering": ["-created"],
            },
        ),
        migrations.AddIndex(
            model_name="researchreport",
            index=models.Index(
                fields=["corpus", "status"], name="research_re_corpus__c00b86_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="researchreport",
            index=models.Index(
                fields=["creator", "-created"], name="research_re_creator_a4eaa6_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="researchreport",
            index=models.Index(
                fields=["status", "last_progress_at"],
                name="research_re_status_b7a9f2_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="researchreport",
            constraint=models.CheckConstraint(
                check=models.Q(("max_steps__gt", 0)),
                name="research_report_max_steps_positive",
            ),
        ),
    ]
