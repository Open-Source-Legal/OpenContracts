import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("corpuses", "0047_corpus_license_fields"),
        ("documents", "0035_add_enabled_components_to_pipeline_settings"),
    ]

    operations = [
        migrations.CreateModel(
            name="LegalAreaCorpus",
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
                    "area",
                    models.CharField(
                        choices=[
                            ("constitucional", "Derecho Constitucional"),
                            ("penal", "Derecho Penal"),
                            ("civil", "Derecho Civil"),
                            ("administrativo", "Derecho Administrativo"),
                            ("laboral", "Derecho Laboral"),
                            ("tributario", "Derecho Tributario"),
                            ("familia", "Derecho de Familia"),
                            ("comercial", "Derecho Comercial"),
                            ("agrario", "Derecho Agrario"),
                            ("ambiental", "Derecho Ambiental"),
                            ("otros", "Otros"),
                        ],
                        max_length=32,
                        unique=True,
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "corpus",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bolivian_law_area",
                        to="corpuses.corpus",
                    ),
                ),
            ],
            options={
                "verbose_name": "Bolivian Legal Area Corpus",
                "verbose_name_plural": "Bolivian Legal Area Corpora",
            },
        ),
        migrations.CreateModel(
            name="BolivianLegalDocument",
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
                    "area",
                    models.CharField(
                        choices=[
                            ("constitucional", "Derecho Constitucional"),
                            ("penal", "Derecho Penal"),
                            ("civil", "Derecho Civil"),
                            ("administrativo", "Derecho Administrativo"),
                            ("laboral", "Derecho Laboral"),
                            ("tributario", "Derecho Tributario"),
                            ("familia", "Derecho de Familia"),
                            ("comercial", "Derecho Comercial"),
                            ("agrario", "Derecho Agrario"),
                            ("ambiental", "Derecho Ambiental"),
                            ("otros", "Otros"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("gaceta", "Gaceta Oficial de Bolivia"),
                            ("tsj", "Tribunal Supremo de Justicia"),
                            ("tcp", "Tribunal Constitucional Plurinacional"),
                            ("manual", "Carga manual"),
                        ],
                        default="manual",
                        max_length=16,
                    ),
                ),
                (
                    "external_id",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Identificador externo (número de gaceta, sentencia, "
                            "etc.). Opcional; depende de la fuente."
                        ),
                        max_length=255,
                    ),
                ),
                ("title", models.CharField(max_length=1024)),
                ("published_at", models.DateField(blank=True, null=True)),
                (
                    "pdf_sha256",
                    models.CharField(max_length=64, unique=True),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pendiente"),
                            ("ingested", "Ingestado"),
                            ("failed", "Fallido"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("last_error", models.TextField(blank=True, default="")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("ingested_at", models.DateTimeField(blank=True, null=True)),
                (
                    "corpus",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bolivian_legal_records",
                        to="corpuses.corpus",
                    ),
                ),
                (
                    "document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bolivian_legal_records",
                        to="documents.document",
                    ),
                ),
            ],
            options={
                "verbose_name": "Bolivian Legal Document",
                "verbose_name_plural": "Bolivian Legal Documents",
                "indexes": [
                    models.Index(
                        fields=["area", "status"],
                        name="bolivian_la_area_a92e57_idx",
                    ),
                    models.Index(
                        fields=["source", "status"],
                        name="bolivian_la_source_8a08f0_idx",
                    ),
                ],
            },
        ),
    ]
