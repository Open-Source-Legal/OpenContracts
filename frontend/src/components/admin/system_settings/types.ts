import { ComponentSettingSchemaType } from "../../../types/graphql-api";

// ============================================================================
// Types
// ============================================================================

/**
 * Stages that are per-MIME-type assignable in the Filetype Defaults table.
 *
 * Embedders are deliberately excluded (issue #2114): the per-MIME
 * `preferred_embedders` mapping has no effect at ingest — the dual-embedding
 * strategy always resolves the single global `default_embedder`, because
 * letting different MIME types resolve to different embedder
 * classes/dimensions would fragment the shared cross-corpus vector index.
 * The GUI column was removed rather than wiring a resolver that would create
 * that hazard. `preferredEmbedders` remains a valid, API-only GraphQL field
 * (see `graphql.ts`) — it is simply no longer editable per-MIME here.
 */
export type StageType = "parsers" | "thumbnailers";

/**
 * Component-library stages, including ones that are NOT file-type-scoped and
 * therefore have no per-MIME filetype-default mapping (LLM providers and file
 * converters — the latter are keyed by source-file EXTENSION and selected via
 * the single defaultFileConverter setting) and embedders (see `StageType`
 * above — still a manageable/listable component category, just not
 * per-MIME-assignable). Used by the Component Library list/filters;
 * `StageType` remains the narrower set of stages that participate in
 * `PipelineMappingKey` filetype assignment.
 */
export type LibraryStageType =
  | StageType
  | "embedders"
  | "llmProviders"
  | "fileConverters";

/** Type for pipeline settings keys that hold MIME-type mappings */
export type PipelineMappingKey = "preferredParsers" | "preferredThumbnailers";

/**
 * Mapping of MIME types to ORDERED LISTS of enricher class paths (the
 * enrichment chain run between parsing and persistence). Deliberately NOT a
 * `StageType`/`PipelineMappingKey` — those model a single class path per MIME
 * type via a `<select>`, while `preferred_enrichers` is a per-MIME ordered
 * list requiring its own add/remove/reorder UI (see `EnricherChainEditor`).
 */
export type PreferredEnrichersMap = Record<string, string[]>;

export type SettingsSchemaEntry = ComponentSettingSchemaType;

// ============================================================================
// Props Interfaces
// ============================================================================

export interface AdvancedSettingsPanelProps {
  currentSelection: string;
  configSettings: ComponentSettingSchemaType[];
  secretSettings: ComponentSettingSchemaType[];
  isExpanded: boolean;
  settingsKey: string;
  saving: boolean;
  onToggle: () => void;
  onAddSecrets: (componentPath: string) => void;
  onDeleteSecrets: (componentPath: string) => void;
  onSaveConfig: (componentPath: string, values: Record<string, string>) => void;
}
