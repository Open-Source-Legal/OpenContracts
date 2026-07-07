# Pipeline Configuration Guide

This guide covers how to configure the document processing pipeline in OpenContracts, including first-time setup, upgrades, and runtime configuration.

## Overview

OpenContracts uses a **database-backed configuration system** for pipeline settings. This allows superusers to change parsers, embedders, and thumbnailers at runtime without code deployment.

The configuration is stored in a singleton `PipelineSettings` model that tracks:
- **Preferred parsers** per MIME type
- **Preferred embedders** per MIME type
- **Preferred thumbnailers** per MIME type
- **Parser kwargs** (component-specific configuration)
- **Component settings** (advanced overrides)
- **Default embedder** (fallback when no MIME-specific embedder exists)
- **Encrypted secrets** (API keys, credentials)

## Discovering Available Components

Before configuring, discover what pipeline components are available and what settings they need:

```bash
# List all components and their settings
docker compose -f local.yml run django python manage.py migrate_pipeline_settings --list-components

# Filter to a specific component
docker compose -f local.yml run django python manage.py migrate_pipeline_settings --list-components --component LlamaParse
```

Example output:
```
======================================================================
AVAILABLE PIPELINE COMPONENTS
======================================================================

Parsers
----------------------------------------

  DoclingParser
    Class: opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser
    Title: Docling Parser
    Description: Parse documents using Docling ML service
    Supported types: application/pdf
    Settings (2):
      - force_ocr: bool
          default: False
          Force OCR on all pages
      - roll_up_groups: bool
          default: True
          Combine grouped elements

  LlamaParseParser
    Class: opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser
    Settings (1):
      - api_key: str [REQUIRED, SECRET]
          env: LLAMAPARSE_API_KEY
          LlamaParse API key

...
======================================================================
USAGE
======================================================================
  1. Set environment variables for required settings
  2. Run: python manage.py migrate_pipeline_settings
  3. Verify: python manage.py migrate_pipeline_settings --verify
======================================================================
```

## First-Time Setup (Fresh Install)

On a fresh installation, pipeline settings are automatically initialized from Django settings during migration.

```bash
# 1. Discover what components exist and what they need
docker compose -f local.yml run django python manage.py migrate_pipeline_settings --list-components

# 2. Set any required environment variables (see output from step 1)
# export LLAMAPARSE_API_KEY=your-key  # if using LlamaParse

# 3. Run migrations - creates PipelineSettings singleton from Django settings
docker compose -f local.yml run django python manage.py migrate

# 4. Migrate component settings from environment variables to database
docker compose -f local.yml run django python manage.py migrate_pipeline_settings

# 5. Verify all components have required settings
docker compose -f local.yml run django python manage.py migrate_pipeline_settings --verify
```

**That's it for basic setup.** The system will use sensible defaults:
- **Docling parser** for PDFs
- **TxtParser** for text files
- **MicroserviceEmbedder** for embeddings

### Environment Variables for First Boot

Set these in your `.env` file or docker-compose environment before first migration:

```bash
# Parser selection (optional - defaults to docling)
PDF_PARSER=docling  # Options: docling, llamaparse

# LlamaParse (if using llamaparse parser)
LLAMAPARSE_API_KEY=your-api-key-here

# Multimodal embedder (if using)
MULTIMODAL_EMBEDDER_HOST=multimodal-embedder
MULTIMODAL_EMBEDDER_PORT=8000
MULTIMODAL_EMBEDDER_VECTOR_SIZE=768
```

## Upgrading Existing Installation

When upgrading OpenContracts, the migration system preserves your existing configuration (if you've already setup pipeline settings in the DB). However, if Django settings have new defaults you want to adopt, use `--sync-preferences`:

```bash
# 1. Run migrations
docker compose -f local.yml run django python manage.py migrate

# 2. (Optional) Preview what would change if syncing from Django settings
docker compose -f local.yml run django python manage.py migrate_pipeline_settings --sync-preferences --dry-run

# 3. (Optional) Apply new defaults from Django settings
docker compose -f local.yml run django python manage.py migrate_pipeline_settings --sync-preferences

# 4. (Optional) Migrate any new component settings from environment
docker compose -f local.yml run django python manage.py migrate_pipeline_settings
```

### Understanding the Sync Behavior

| Scenario | What Happens |
|----------|--------------|
| Fresh install | Migration creates singleton from Django settings |
| Upgrade (no action) | Existing DB settings preserved |
| `--sync-preferences` | Overwrites DB preferences with current Django settings |
| `migrate_pipeline_settings` | Migrates component-specific settings from env vars |

## Runtime Configuration (Admin UI)

Superusers can configure the pipeline at runtime through the Admin UI:

1. Navigate to **Admin → Pipeline Configuration**
2. Configure preferred components per MIME type
3. Add API keys via the **Component Secrets** section
4. Configure the per-MIME-type enrichment chain (ordered list of enrichers —
   see [Enrichers](pipeline_overview.md#enrichers)) via the **Enrichment
   Chains** editor
5. Configure agent tool credentials (e.g. the web search tool) via the
   **Agent Tools** panel — see
   `frontend/src/components/admin/system_settings/ToolSecretsPanel.tsx`

### UI Overview

On desktop, the Pipeline Configuration page uses a **two-column layout** with the Component Library on the left and Filetype Defaults on the right:

![Pipeline Configuration — desktop two-column layout](../assets/images/screenshots/auto/admin--pipeline-settings--two-column-desktop.png)

On mobile and tablet viewports, the two sections collapse into a **tabbed interface**:

![Pipeline Configuration — mobile tab view](../assets/images/screenshots/auto/admin--pipeline-settings--mobile-tabs.png)

Switching to the Filetype Defaults tab shows the per-MIME-type parser/embedder/thumbnailer assignment:

![Pipeline Configuration — mobile filetype defaults tab](../assets/images/screenshots/auto/admin--pipeline-settings--mobile-filetype-tab.png)

### Component Secrets

Sensitive configuration (API keys, credentials) is stored encrypted in the database. Secrets are encrypted using Django's `SECRET_KEY`.

> **Warning**: If you rotate `SECRET_KEY`, all encrypted secrets become unrecoverable. Before rotating:
> 1. Export secrets via Django shell: `PipelineSettings.get_instance().get_secrets()`
> 2. After rotation, re-import: `instance.set_secrets(exported_secrets); instance.save()`

## Management Command Reference

### `migrate_pipeline_settings`

```bash
# List all available components and their settings schemas
python manage.py migrate_pipeline_settings --list-components

# Filter to specific component
python manage.py migrate_pipeline_settings --list-components --component DoclingParser

# Preview what would be migrated
python manage.py migrate_pipeline_settings --dry-run

# Migrate component settings from environment variables
python manage.py migrate_pipeline_settings

# Force overwrite existing DB values with environment values
python manage.py migrate_pipeline_settings --force

# Verify all components have required settings
python manage.py migrate_pipeline_settings --verify

# Sync main preferences (PREFERRED_PARSERS, etc.) from Django settings
python manage.py migrate_pipeline_settings --sync-preferences

# Migrate settings for a specific component only
python manage.py migrate_pipeline_settings --component LlamaParseParser

# Verbose output showing all settings
python manage.py migrate_pipeline_settings --verbose

# Fail with exit code 1 if required settings are missing
python manage.py migrate_pipeline_settings --strict
```

## Configuration Priority

The system uses **database-only configuration** at runtime:

1. **Database settings** (`PipelineSettings` model) - the single source of truth
2. **Component defaults** - built-in defaults when no DB settings exist

> **Note**: Django settings (`PREFERRED_PARSERS`, etc.) are only read during initial migration to populate the database. At runtime, all configuration comes from the database. Use `--sync-preferences` to re-sync from Django settings after upgrades.

## Production Deployment

For production deployments:

```bash
# 1. Always run migrations first
docker compose -f production.yml --profile migrate up migrate

# 2. (First deploy only) Migrate settings from environment
docker compose -f production.yml run django python manage.py migrate_pipeline_settings

# 3. Start services
docker compose -f production.yml up -d
```

### Recommended Production Settings

```bash
# .env.production

# Use Docling parser (default, no API key needed)
PDF_PARSER=docling

# Or use LlamaParse (requires API key)
# PDF_PARSER=llamaparse
# LLAMAPARSE_API_KEY=your-production-key

# Embedder settings
DEFAULT_EMBEDDER=opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder
```

## Troubleshooting

### Components Not Available

If a component doesn't appear in the UI:

```bash
# Check registered components
python manage.py migrate_pipeline_settings --verify --verbose
```

### Missing Required Settings

```bash
# Identify missing settings
python manage.py migrate_pipeline_settings --verify

# The output will show which settings need to be configured
```

### Reset to Defaults

To reset pipeline component assignments and settings to Django defaults:

1. Via Admin UI: Click "Reset to Defaults" button
2. Via management command:
   ```bash
   python manage.py migrate_pipeline_settings --sync-preferences --force
   ```

Reset restores `preferred_parsers`/`preferred_embedders`/`preferred_thumbnailers`/
`preferred_enrichers`/`parser_kwargs`/`component_settings`/the `default_*`
fields/`enabled_components` from their Django settings counterparts (see
`ResetPipelineSettingsMutation` in `config/graphql/pipeline_settings_mutations.py`).
**Stored secrets are never touched by Reset** — component secrets and agent
tool secrets (e.g. the web search tool's API key, see
`UpdateToolSecretsMutation`/`DeleteToolSecretsMutation`) must be cleared
separately via their own delete mutations if desired.

## See Also

- [Pipeline Architecture Overview](pipeline_overview.md)
- [Docling Parser](docling_parser.md)
- [LlamaParse Parser](llamaparse_parser.md)
- [Multimodal Embedder](multimodal_embedder.md)
