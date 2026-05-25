"""Add CorpusVote model + denormalized vote counts on Corpus.

Mirrors ``conversations/migrations/0006_messagevote_userreputation_and_more.py``
in shape — adds the voting table, two partial UNIQUE indexes (one for the
authenticated branch keyed on ``creator``, one for the anonymous branch keyed
on ``session_key``), the per-row indexes used by the count-recompute signal,
and the three denormalized count columns on ``Corpus``.

Note on the unique constraints: Postgres treats every NULL as distinct, so a
single ``UniqueConstraint(fields=["corpus", "creator"])`` would let an
unbounded number of anonymous rows (creator IS NULL) accumulate.  The two
partial UNIQUEs encode the actual one-vote-per-voter contract — see the model
docstring for the full rationale.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("corpuses", "0048_corpus_agent_memory"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------- #
        # Denormalized vote count fields on Corpus.  ``score`` is db_indexed
        # so the corpus list view can ORDER BY score without a JOIN-and-
        # aggregate per query.
        # ------------------------------------------------------------------- #
        migrations.AddField(
            model_name="corpus",
            name="upvote_count",
            field=models.IntegerField(
                default=0,
                help_text="Cached count of upvotes for this corpus",
            ),
        ),
        migrations.AddField(
            model_name="corpus",
            name="downvote_count",
            field=models.IntegerField(
                default=0,
                help_text="Cached count of downvotes for this corpus",
            ),
        ),
        migrations.AddField(
            model_name="corpus",
            name="score",
            field=models.IntegerField(
                default=0,
                db_index=True,
                help_text=("upvote_count - downvote_count, denormalized for sorting"),
            ),
        ),
        # ------------------------------------------------------------------- #
        # CorpusVote table.  ``creator`` is nullable so anonymous voters can
        # be represented by ``session_key`` alone; the two partial UNIQUEs
        # below enforce the actual one-vote-per-voter contract.
        # ------------------------------------------------------------------- #
        migrations.CreateModel(
            name="CorpusVote",
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
                ("backend_lock", models.BooleanField(default=False)),
                ("is_public", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("modified", models.DateTimeField(auto_now=True)),
                (
                    "vote_type",
                    models.CharField(
                        choices=[
                            ("upvote", "Upvote"),
                            ("downvote", "Downvote"),
                        ],
                        help_text="Type of vote (upvote or downvote)",
                        max_length=16,
                    ),
                ),
                (
                    "session_key",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        help_text=(
                            "Django session id for anonymous voters.  Null for "
                            "authenticated votes.  Forms half of the anonymous-"
                            "branch unique constraint."
                        ),
                        max_length=64,
                        null=True,
                    ),
                ),
                (
                    "ip_hash",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Salted SHA-256 of the voter's IP, stored only for "
                            "abuse-review/audit purposes.  NOT part of the "
                            "unique constraint (shared NATs would otherwise "
                            "block legitimate co-located voters)."
                        ),
                        max_length=64,
                        null=True,
                    ),
                ),
                (
                    "corpus",
                    models.ForeignKey(
                        help_text="The corpus being voted on",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="votes",
                        to="corpuses.corpus",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user_lock",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="locked_%(class)s_objects",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "permissions": (
                    ("permission_corpusvote", "permission corpusvote"),
                    ("create_corpusvote", "create corpusvote"),
                    ("read_corpusvote", "read corpusvote"),
                    ("update_corpusvote", "update corpusvote"),
                    ("remove_corpusvote", "delete corpusvote"),
                ),
            },
        ),
        # ------------------------------------------------------------------- #
        # Guardian per-row permission tables for CorpusVote.
        # ------------------------------------------------------------------- #
        migrations.CreateModel(
            name="CorpusVoteUserObjectPermission",
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
                (
                    "content_object",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="corpuses.corpusvote",
                    ),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="auth.permission",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
                "unique_together": {("user", "permission", "content_object")},
            },
        ),
        migrations.CreateModel(
            name="CorpusVoteGroupObjectPermission",
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
                (
                    "content_object",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="corpuses.corpusvote",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="auth.group",
                    ),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="auth.permission",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "unique_together": {("group", "permission", "content_object")},
            },
        ),
        # ------------------------------------------------------------------- #
        # Indexes used by the count-recompute signal (per-corpus aggregate)
        # and by the my_vote resolver (per-creator / per-session lookups).
        # ------------------------------------------------------------------- #
        migrations.AddIndex(
            model_name="corpusvote",
            index=models.Index(
                fields=["corpus", "vote_type"],
                name="corpuses_co_corpus__vote_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="corpusvote",
            index=models.Index(
                fields=["creator"],
                name="corpuses_co_creator_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="corpusvote",
            index=models.Index(
                fields=["session_key"],
                name="corpuses_co_session_idx",
            ),
        ),
        # ------------------------------------------------------------------- #
        # Two partial UNIQUE indexes — one per voter shape.  Postgres treats
        # every NULL as distinct, so a non-partial UNIQUE(corpus, creator)
        # would let unbounded NULL-creator rows accumulate; the partial
        # condition pins each branch to the column that actually identifies
        # the voter for that branch.
        # ------------------------------------------------------------------- #
        migrations.AddConstraint(
            model_name="corpusvote",
            constraint=models.UniqueConstraint(
                condition=models.Q(("creator__isnull", False)),
                fields=("corpus", "creator"),
                name="one_vote_per_user_per_corpus",
            ),
        ),
        migrations.AddConstraint(
            model_name="corpusvote",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("creator__isnull", True),
                    ("session_key__isnull", False),
                ),
                fields=("corpus", "session_key"),
                name="one_anon_vote_per_session_per_corpus",
            ),
        ),
    ]
