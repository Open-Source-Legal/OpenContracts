import React from "react";
import { FileText, Cpu, Image, Bot } from "lucide-react";
import { StageType, LibraryStageType, PipelineMappingKey } from "./types";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

/** Stage configuration with properly typed settings keys */
export const STAGE_CONFIG: Record<
  StageType,
  {
    color: string;
    icon: React.FC;
    title: string;
    subtitle: string;
    settingsKey: PipelineMappingKey;
  }
> = {
  parsers: {
    color: OS_LEGAL_COLORS.primaryBlue,
    icon: FileText,
    title: "Parser",
    subtitle: "Extract text and structure",
    settingsKey: "preferredParsers",
  },
  thumbnailers: {
    color: "#EC4899",
    icon: Image,
    title: "Thumbnailer",
    subtitle: "Generate document previews",
    settingsKey: "preferredThumbnailers",
  },
  embedders: {
    color: OS_LEGAL_COLORS.greenMedium,
    icon: Cpu,
    title: "Embedder",
    subtitle: "Create vector embeddings",
    settingsKey: "preferredEmbedders",
  },
};

/**
 * Display metadata for the Component Library list. Covers every library stage,
 * including LLM providers which are NOT file-type-scoped and therefore absent
 * from {@link STAGE_CONFIG} (which carries the per-MIME `settingsKey`). The
 * three filetype stages are reused from `STAGE_CONFIG` to keep colors/icons in
 * one place.
 */
export const LIBRARY_STAGE_CONFIG: Record<
  LibraryStageType,
  { color: string; icon: React.FC; title: string; subtitle: string }
> = {
  ...STAGE_CONFIG,
  llmProviders: {
    // Violet, distinct from the three filetype stages. Literal hex matches the
    // existing per-stage color convention in this file (e.g. thumbnailers).
    color: "#8B5CF6",
    icon: Bot,
    title: "LLM Provider",
    subtitle: "Power agents & chat",
  },
};
