import React from "react";
import { FileText, Cpu, Image, Bot, FileOutput } from "lucide-react";
import { StageType, LibraryStageType, PipelineMappingKey } from "./types";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

/**
 * Stage configuration with properly typed settings keys.
 *
 * Covers only the per-MIME-assignable stages (see `StageType`). Embedders are
 * NOT here — `preferred_embedders` has no per-MIME settingsKey to assign
 * through this table (issue #2114); their Component Library display config
 * lives directly in {@link LIBRARY_STAGE_CONFIG} below.
 */
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
};

/**
 * Display metadata for the Component Library list. Covers every library stage,
 * including ones which are NOT file-type-scoped and therefore absent from
 * {@link STAGE_CONFIG} (which carries the per-MIME `settingsKey`): LLM
 * providers, file converters, and embedders (see `types.ts` for why embedders
 * are excluded from `STAGE_CONFIG`/`StageType`). The two filetype stages are
 * reused from `STAGE_CONFIG` to keep colors/icons in one place.
 */
type LibraryStageDisplay = {
  color: string;
  icon: React.FC;
  title: string;
  subtitle: string;
};

/** Reuse a STAGE_CONFIG entry's display fields, dropping the per-MIME
 *  `settingsKey` that is irrelevant to the library list (and absent from the
 *  display-only value type). */
const toLibraryDisplay = (stage: StageType): LibraryStageDisplay => {
  const { color, icon, title, subtitle } = STAGE_CONFIG[stage];
  return { color, icon, title, subtitle };
};

export const LIBRARY_STAGE_CONFIG: Record<
  LibraryStageType,
  LibraryStageDisplay
> = {
  parsers: toLibraryDisplay("parsers"),
  thumbnailers: toLibraryDisplay("thumbnailers"),
  embedders: {
    color: OS_LEGAL_COLORS.greenMedium,
    icon: Cpu,
    title: "Embedder",
    subtitle: "Create vector embeddings",
  },
  llmProviders: {
    // Violet, distinct from the three filetype stages. Literal hex matches the
    // existing per-stage color convention in this file (e.g. thumbnailers).
    color: "#8B5CF6",
    icon: Bot,
    title: "LLM Provider",
    subtitle: "Power agents & chat",
  },
  fileConverters: {
    // Amber, distinct from the other stages (same literal-hex convention).
    color: "#F59E0B",
    icon: FileOutput,
    title: "File Converter",
    subtitle: "Convert uploads to PDF before parsing",
  },
};
