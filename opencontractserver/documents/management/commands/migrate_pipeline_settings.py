"""
Management command to migrate pipeline component settings to PipelineSettings database.

This command scans all registered pipeline components, extracts their Settings schemas,
reads current values from Django settings (using env_var metadata), and populates the
PipelineSettings singleton with the appropriate values.

Usage:
    python manage.py migrate_pipeline_settings --dry-run  # Show what would be migrated
    python manage.py migrate_pipeline_settings            # Perform migration
    python manage.py migrate_pipeline_settings --verify   # Verify all components configured
"""

import logging
from typing import Any

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Migrate pipeline settings from Django settings to PipelineSettings database.

    This command:
    1. Scans all registered pipeline components
    2. Extracts their Settings schemas (if defined)
    3. Reads current values from Django settings (using env_var metadata)
    4. Populates PipelineSettings.component_settings and encrypted_secrets
    5. Reports any required settings that are missing
    """

    help = (
        "Migrate pipeline component settings from Django settings/env vars "
        "to PipelineSettings database"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without making changes",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify all components have required settings configured",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed information about each component",
        )
        parser.add_argument(
            "--component",
            type=str,
            help="Only migrate settings for a specific component (by class name or full path)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing database values with environment/default values. "
            "Without this flag, existing DB values are preserved.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail if any required settings are missing (exit code 1)",
        )
        parser.add_argument(
            "--sync-preferences",
            action="store_true",
            help="Sync main pipeline preferences (PREFERRED_PARSERS, PREFERRED_EMBEDDERS, etc.) "
            "from Django settings to database. Useful after upgrading when Django settings "
            "have new defaults you want to adopt.",
        )
        parser.add_argument(
            "--init-only",
            action="store_true",
            help="Only populate fields that are currently empty/unset in the database. "
            "Existing non-empty values are preserved. Safe for use on every startup.",
        )
        parser.add_argument(
            "--list-components",
            action="store_true",
            help="List all available pipeline components and their settings schemas. "
            "Shows required settings, env var names, defaults, and descriptions.",
        )

    def handle(self, *args, **options):
        """Execute the migration command."""
        dry_run = options["dry_run"]
        verify_only = options["verify"]
        verbose = options["verbose"]
        specific_component = options.get("component")
        force_overwrite = options.get("force", False)
        strict_mode = options.get("strict", False)
        sync_preferences = options.get("sync_preferences", False)
        init_only = options.get("init_only", False)
        list_components = options.get("list_components", False)

        # Validate flag combinations
        if init_only and not sync_preferences:
            raise CommandError("--init-only requires --sync-preferences")

        # Handle --list-components first (doesn't need the header)
        if list_components:
            self._list_components(specific_component)
            return

        self.stdout.write(self.style.NOTICE("\n" + "=" * 70))
        self.stdout.write(self.style.NOTICE("Pipeline Settings Migration"))
        self.stdout.write(self.style.NOTICE("=" * 70 + "\n"))

        if not force_overwrite:
            self.stdout.write(
                self.style.NOTICE(
                    "Note: Existing database values will be preserved. "
                    "Use --force to overwrite.\n"
                )
            )

        if verify_only:
            self._verify_all_components(verbose)
            return

        if sync_preferences:
            self._sync_preferences(dry_run, verbose, init_only=init_only)
            return

        # Import here to avoid circular imports
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.base.settings_schema import (
            get_secret_settings,
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        pipeline_settings = PipelineSettings.get_instance(use_cache=False)

        # Collect all components
        all_components: list[Any] = []
        all_components.extend(registry.parsers)
        all_components.extend(registry.embedders)
        all_components.extend(registry.thumbnailers)
        all_components.extend(registry.post_processors)

        # Filter to specific component if requested
        if specific_component:
            all_components = [
                c
                for c in all_components
                if c.name == specific_component or c.class_name == specific_component
            ]
            if not all_components:
                self.stdout.write(
                    self.style.ERROR(f"Component '{specific_component}' not found")
                )
                return

        self.stdout.write(f"Found {len(all_components)} pipeline components\n")

        # Track migration stats. Mixed value types (counters and lists) so
        # we widen to ``Any`` so mypy treats the dict as heterogeneous.
        stats: dict[str, Any] = {
            "total": len(all_components),
            "with_schema": 0,
            "settings_migrated": 0,
            "secrets_migrated": 0,
            "missing_required": [],
            "errors": [],
        }

        # Current settings from DB
        current_component_settings = dict(pipeline_settings.component_settings or {})
        current_secrets = pipeline_settings.get_secrets()

        for component_def in all_components:
            component_class = component_def.component_class
            if component_class is None:
                continue

            class_path = component_def.class_name
            schema = get_settings_schema(component_class)

            if not schema:
                if verbose:
                    self.stdout.write(
                        f"  {component_def.name}: No Settings schema defined"
                    )
                continue

            stats["with_schema"] += 1
            secret_settings = get_secret_settings(component_class)

            self.stdout.write(
                f"\n{component_def.name} ({component_def.component_type.value})"
            )
            self.stdout.write(f"  Class: {class_path}")
            self.stdout.write(
                f"  Settings: {len(schema)} total, {len(secret_settings)} secrets"
            )

            # Prepare settings dicts
            non_secret_settings: dict[str, Any] = {}
            component_secrets: dict[str, Any] = {}

            for setting_name, info in schema.items():
                env_var = info.get("env_var")
                default = info.get("default")
                is_secret = setting_name in secret_settings
                is_required = info.get("required", False)

                # Check existing DB value first
                existing_db_value = None
                if class_path in current_component_settings:
                    existing_db_value = current_component_settings[class_path].get(
                        setting_name
                    )

                existing_secret_value = None
                if is_secret and class_path in current_secrets:
                    existing_secret_value = current_secrets[class_path].get(
                        setting_name
                    )

                # Determine if we should use existing DB value (preserve mode)
                # Without --force, existing DB values are preserved
                has_existing_db = (
                    existing_db_value is not None or existing_secret_value is not None
                )

                if has_existing_db and not force_overwrite:
                    # Preserve existing DB value
                    final_value = (
                        existing_secret_value
                        if is_secret and existing_secret_value is not None
                        else existing_db_value
                    )
                    if verbose:
                        self.stdout.write(
                            f"    {setting_name}: [PRESERVED] (use --force to overwrite)"
                        )
                else:
                    # Try to get value from Django settings/env
                    env_value = None
                    if env_var:
                        env_value = getattr(django_settings, env_var, None)

                    # Determine final value: env_value > default
                    final_value = env_value if env_value is not None else default

                # Track missing required settings
                if is_required and (final_value is None or final_value == ""):
                    stats["missing_required"].append(
                        {
                            "component": class_path,
                            "setting": setting_name,
                            "env_var": env_var,
                        }
                    )
                    if verbose:
                        self.stdout.write(
                            self.style.WARNING(
                                f"    {setting_name}: MISSING (required)"
                            )
                        )
                    continue

                # Skip if value was preserved from DB (already logged above)
                if has_existing_db and not force_overwrite:
                    # Still add to dicts to maintain consistency
                    if is_secret and final_value is not None and final_value != "":
                        component_secrets[setting_name] = final_value
                    elif not is_secret and final_value is not None:
                        non_secret_settings[setting_name] = final_value
                    continue

                # Add to appropriate dict
                if is_secret:
                    if final_value is not None and final_value != "":
                        component_secrets[setting_name] = final_value
                        stats["secrets_migrated"] += 1
                        if verbose:
                            self.stdout.write(
                                f"    {setting_name}: [SECRET] {'(from env)' if env_var else '(default)'}"
                            )
                else:
                    if final_value is not None:
                        non_secret_settings[setting_name] = final_value
                        stats["settings_migrated"] += 1
                        if verbose:
                            display_value = (
                                final_value
                                if len(str(final_value)) < 50
                                else str(final_value)[:47] + "..."
                            )
                            self.stdout.write(f"    {setting_name}: {display_value}")

            # Store in DB (unless dry-run)
            if not dry_run:
                if non_secret_settings:
                    # Merge settings instead of replacing to preserve untracked keys
                    if class_path not in current_component_settings:
                        current_component_settings[class_path] = {}
                    current_component_settings[class_path].update(non_secret_settings)

                if component_secrets:
                    if class_path not in current_secrets:
                        current_secrets[class_path] = {}
                    current_secrets[class_path].update(component_secrets)

        # Save to database
        if not dry_run:
            try:
                pipeline_settings.component_settings = current_component_settings
                if current_secrets:
                    pipeline_settings.set_secrets(current_secrets)
                pipeline_settings.save()
                self.stdout.write(
                    self.style.SUCCESS("\nSettings saved to database successfully")
                )
            except Exception as e:
                stats["errors"].append(str(e))
                self.stdout.write(self.style.ERROR(f"\nError saving settings: {e}"))
        else:
            self.stdout.write(
                self.style.NOTICE("\n[DRY RUN] No changes were made to the database")
            )

        # Print summary
        self._print_summary(stats, dry_run)

        # Strict mode: fail if required settings are missing
        if strict_mode and stats["missing_required"]:
            raise SystemExit(1)

    def _verify_all_components(self, verbose: bool):
        """Verify all components have required settings configured."""
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.base.settings_schema import (
            get_required_settings,
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        pipeline_settings = PipelineSettings.get_instance(use_cache=False)

        all_components: list[Any] = []
        all_components.extend(registry.parsers)
        all_components.extend(registry.embedders)
        all_components.extend(registry.thumbnailers)
        all_components.extend(registry.post_processors)

        all_valid = True
        missing_by_component: dict[str, list[str]] = {}

        for component_def in all_components:
            component_class = component_def.component_class
            if component_class is None:
                continue

            class_path = component_def.class_name
            schema = get_settings_schema(component_class)

            if not schema:
                continue

            required_settings = get_required_settings(component_class)
            if not required_settings:
                if verbose:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  {component_def.name}: OK (no required settings)"
                        )
                    )
                continue

            # Get current settings from DB
            db_settings = pipeline_settings.get_full_component_settings(class_path)

            missing = []
            for setting_name in required_settings:
                value = db_settings.get(setting_name)
                if value is None or value == "":
                    missing.append(setting_name)

            if missing:
                all_valid = False
                missing_by_component[class_path] = missing
                self.stdout.write(
                    self.style.ERROR(
                        f"  {component_def.name}: MISSING {len(missing)} required settings"
                    )
                )
                if verbose:
                    for m in missing:
                        self.stdout.write(f"    - {m}")
            else:
                self.stdout.write(self.style.SUCCESS(f"  {component_def.name}: OK"))

        self.stdout.write("\n" + "=" * 70)
        if all_valid:
            self.stdout.write(self.style.SUCCESS("VERIFICATION PASSED"))
            self.stdout.write("All components have required settings configured")
        else:
            self.stdout.write(self.style.ERROR("VERIFICATION FAILED"))
            total_missing = sum(len(v) for v in missing_by_component.values())
            self.stdout.write(
                f"{len(missing_by_component)} components have "
                f"{total_missing} missing required settings"
            )
        self.stdout.write("=" * 70 + "\n")

        if not all_valid:
            raise SystemExit(1)

    def _print_summary(self, stats: dict, dry_run: bool):
        """Print migration summary."""
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("MIGRATION SUMMARY")
        self.stdout.write("=" * 70)

        self.stdout.write(f"  Total components scanned: {stats['total']}")
        self.stdout.write(f"  Components with Settings schema: {stats['with_schema']}")
        self.stdout.write(
            f"  Non-secret settings migrated: {stats['settings_migrated']}"
        )
        self.stdout.write(f"  Secret settings migrated: {stats['secrets_migrated']}")

        if stats["missing_required"]:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  Missing required settings: {len(stats['missing_required'])}"
                )
            )
            for missing in stats["missing_required"]:
                env_hint = (
                    f" (set {missing['env_var']})" if missing.get("env_var") else ""
                )
                self.stdout.write(
                    f"    - {missing['component']}.{missing['setting']}{env_hint}"
                )

        if stats["errors"]:
            self.stdout.write(self.style.ERROR(f"\n  Errors: {len(stats['errors'])}"))
            for error in stats["errors"]:
                self.stdout.write(f"    - {error}")

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    "\n  [DRY RUN] Run without --dry-run to apply changes"
                )
            )

        self.stdout.write("=" * 70 + "\n")

    def _sync_preferences(self, dry_run: bool, verbose: bool, init_only: bool = False):
        """
        Sync main pipeline preferences from Django settings to database.

        This updates:
        - preferred_parsers from PREFERRED_PARSERS
        - preferred_embedders from PREFERRED_EMBEDDERS
        - preferred_thumbnailers from PREFERRED_THUMBNAILERS (if defined)
        - parser_kwargs from PARSER_KWARGS
        - default_embedder from DEFAULT_EMBEDDER
        - enabled_components from ENABLED_COMPONENTS (defaults to [] = all enabled)

        When init_only=True, fields that already have non-empty values in the
        database are preserved. This makes the command safe to run on every
        startup without overwriting admin-configured values.
        """
        from opencontractserver.documents.models import PipelineSettings

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)

        mode_label = " (init-only)" if init_only else ""
        self.stdout.write(
            f"Syncing main pipeline preferences from Django settings{mode_label}...\n"
        )

        # Map of DB field -> Django setting name
        preference_mappings = [
            ("preferred_parsers", "PREFERRED_PARSERS", {}),
            ("preferred_embedders", "PREFERRED_EMBEDDERS", {}),
            ("preferred_thumbnailers", "PREFERRED_THUMBNAILERS", {}),
            ("parser_kwargs", "PARSER_KWARGS", {}),
            ("default_embedder", "DEFAULT_EMBEDDER", ""),
            ("enabled_components", "ENABLED_COMPONENTS", []),
        ]

        changes = []
        skipped = []

        for db_field, setting_name, default in preference_mappings:
            current_value = getattr(pipeline_settings, db_field)
            new_value = getattr(django_settings, setting_name, default)

            # In init-only mode, skip fields that already have non-empty values
            if init_only and current_value not in (None, "", {}, []):
                skipped.append(db_field)
                if verbose:
                    self.stdout.write(f"  {db_field}: [PRESERVED] (already configured)")
                continue

            # Normalize for comparison (handle None vs empty dict/string)
            current_normalized = current_value if current_value else default
            new_normalized = new_value if new_value else default

            if current_normalized != new_normalized:
                changes.append(
                    {
                        "field": db_field,
                        "setting": setting_name,
                        "old": current_value,
                        "new": new_value,
                    }
                )
                if verbose:
                    self.stdout.write(f"  {db_field}:")
                    self.stdout.write(f"    Current: {current_value}")
                    self.stdout.write(f"    New:     {new_value}")

                if not dry_run:
                    setattr(pipeline_settings, db_field, new_value)
            else:
                if verbose:
                    self.stdout.write(f"  {db_field}: unchanged")

        if not dry_run and changes:
            pipeline_settings.save()

        # Print summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("SYNC PREFERENCES SUMMARY")
        self.stdout.write("=" * 70)

        if changes:
            self.stdout.write(f"  Fields updated: {len(changes)}")
            for change in changes:
                self.stdout.write(f"    - {change['field']} (from {change['setting']})")
        else:
            self.stdout.write(
                "  No changes needed - database already matches Django settings"
            )

        if skipped:
            self.stdout.write(
                f"  Fields preserved (already configured): {len(skipped)}"
            )
            for field in skipped:
                self.stdout.write(f"    - {field}")

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    "\n  [DRY RUN] Run without --dry-run to apply changes"
                )
            )
        elif changes:
            self.stdout.write(self.style.SUCCESS("\n  Preferences synced successfully"))

        self.stdout.write("=" * 70 + "\n")

    def _list_components(self, specific_component: str | None = None):
        """
        List all available pipeline components and their settings schemas.

        Shows component metadata, supported file types, and settings with:
        - Setting name and type
        - Whether it's required
        - Whether it's a secret (stored encrypted)
        - Environment variable name (if defined)
        - Default value
        - Description
        """
        from opencontractserver.pipeline.base.settings_schema import (
            get_secret_settings,
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()

        # Collect all components by type
        component_groups = [
            ("Parsers", registry.parsers),
            ("Embedders", registry.embedders),
            ("Thumbnailers", registry.thumbnailers),
            ("Post-Processors", registry.post_processors),
        ]

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write(self.style.SUCCESS("AVAILABLE PIPELINE COMPONENTS"))
        self.stdout.write("=" * 70)

        total_components = 0
        components_with_settings = 0

        for group_name, group_components in component_groups:
            # Filter if specific component requested
            components: list[Any] = list(group_components)
            if specific_component:
                components = [
                    c
                    for c in components
                    if c.name == specific_component
                    or c.class_name == specific_component
                    or specific_component.lower() in c.name.lower()
                ]
                if not components:
                    continue

            if not components:
                continue

            self.stdout.write(f"\n{self.style.MIGRATE_HEADING(group_name)}")
            self.stdout.write("-" * 40)

            for component_def in components:
                total_components += 1
                component_class = component_def.component_class
                schema = (
                    get_settings_schema(component_class) if component_class else None
                )

                # Component header
                self.stdout.write(f"\n  {self.style.SUCCESS(component_def.name)}")
                self.stdout.write(f"    Class: {component_def.class_name}")

                if component_def.title:
                    self.stdout.write(f"    Title: {component_def.title}")
                if component_def.description:
                    # Truncate long descriptions
                    desc = component_def.description
                    if len(desc) > 60:
                        desc = desc[:57] + "..."
                    self.stdout.write(f"    Description: {desc}")

                # Supported file types
                if component_def.supported_file_types:
                    types = ", ".join(
                        str(ft.value) if hasattr(ft, "value") else str(ft)
                        for ft in component_def.supported_file_types
                    )
                    self.stdout.write(f"    Supported types: {types}")

                # Settings schema
                if not schema:
                    self.stdout.write(
                        self.style.WARNING(
                            "    Settings: None (no configuration needed)"
                        )
                    )
                    continue

                components_with_settings += 1
                secret_settings = (
                    get_secret_settings(component_class) if component_class else set()
                )

                self.stdout.write(f"    Settings ({len(schema)}):")

                for setting_name, info in schema.items():
                    is_secret = setting_name in secret_settings
                    is_required = info.get("required", False)
                    env_var = info.get("env_var")
                    default = info.get("default")
                    description = info.get("description", "")
                    setting_type = info.get("type", "unknown")

                    # Build setting line
                    flags = []
                    if is_required:
                        flags.append(self.style.ERROR("REQUIRED"))
                    if is_secret:
                        flags.append(self.style.WARNING("SECRET"))

                    flag_str = f" [{', '.join(flags)}]" if flags else ""

                    self.stdout.write(
                        f"      - {setting_name}: {setting_type}{flag_str}"
                    )

                    # Details
                    if env_var:
                        self.stdout.write(f"          env: {env_var}")
                    if default is not None and not is_secret:
                        default_str = (
                            repr(default) if len(repr(default)) < 40 else "..."
                        )
                        self.stdout.write(f"          default: {default_str}")
                    if description:
                        # Truncate long descriptions
                        if len(description) > 50:
                            description = description[:47] + "..."
                        self.stdout.write(f"          {description}")

        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 70)
        self.stdout.write(f"  Total components: {total_components}")
        self.stdout.write(f"  Components with settings: {components_with_settings}")

        if specific_component and total_components == 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  No components found matching '{specific_component}'"
                )
            )

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("USAGE")
        self.stdout.write("=" * 70)
        self.stdout.write("  1. Set environment variables for required settings")
        self.stdout.write("  2. Run: python manage.py migrate_pipeline_settings")
        self.stdout.write(
            "  3. Verify: python manage.py migrate_pipeline_settings --verify"
        )
        self.stdout.write("=" * 70 + "\n")
