import { ComponentSettingSchemaType } from "../../../types/graphql-api";

// ============================================================================
// Types
// ============================================================================

export type StageType = "parsers" | "embedders" | "thumbnailers";

/**
 * Component-library stages, including ones that are NOT file-type-scoped and
 * therefore have no per-MIME filetype-default mapping (LLM providers and file
 * converters — the latter are keyed by source-file EXTENSION and selected via
 * the single defaultFileConverter setting). Used by the Component Library
 * list/filters; `StageType` remains the set of stages that participate in
 * `PipelineMappingKey` filetype assignment.
 */
export type LibraryStageType = StageType | "llmProviders" | "fileConverters";

/** Type for pipeline settings keys that hold MIME-type mappings */
export type PipelineMappingKey =
  | "preferredParsers"
  | "preferredEmbedders"
  | "preferredThumbnailers";

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
