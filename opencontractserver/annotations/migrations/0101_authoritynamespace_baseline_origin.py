# Adds AuthorityNamespace.baseline_origin: provenance "which baseline writer"
# (the core YAML vs. a specific pack's mappings YAML) so two source="baseline"
# writers on the same prefix no longer silently last-write-wins (issue #2057).
# Existing baseline rows stay NULL and are adopted (stamped) by the next owning
# loader run / post_migrate seed.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("annotations", "0100_alter_authorityfrontier_discovery_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="authoritynamespace",
            name="baseline_origin",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
