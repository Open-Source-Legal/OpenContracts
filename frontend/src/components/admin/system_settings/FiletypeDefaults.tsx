import React, { memo, useMemo, useCallback } from "react";
import { Button, Spinner } from "@os-legal/ui";
import { AlertTriangle, FileText, Cpu, Settings, Bot } from "lucide-react";
import {
  PipelineComponentType,
  SupportedMimeTypeType,
} from "../../../types/graphql-api";
import { getComponentDisplayName } from "../PipelineIcons";
import { StageType } from "./types";
import { isComponentAvailable } from "./utils";
import { PARTIALLY_SUPPORTED_WARNING_COLOR } from "../../../assets/configurations/constants";
import {
  Section,
  SectionHeader,
  SectionTitle,
  DefaultEmbedderDisplay,
  DefaultEmbedderInfo,
  DefaultEmbedderPath,
  ComponentName,
  EmptyValue,
  DefaultsContainer,
  DefaultsHeaderRow,
  FiletypeRow,
  FiletypeLabel,
  StageDropdownLabel,
  StyledSelect,
} from "./styles";

// ============================================================================
// Types
// ============================================================================

interface FiletypeDefaultsProps {
  components: {
    parsers: (PipelineComponentType & { className: string })[];
    embedders: (PipelineComponentType & { className: string })[];
    thumbnailers: (PipelineComponentType & { className: string })[];
  };
  supportedMimeTypes: SupportedMimeTypeType[];
  mimeTypesLoading?: boolean;
  enabledComponents: string[];
  preferredParsers: Record<string, string>;
  preferredEmbedders: Record<string, string>;
  preferredThumbnailers: Record<string, string>;
  defaultEmbedder: string;
  defaultLlm: string;
  updating: boolean;
  onAssign: (
    stage: "parsers" | "embedders" | "thumbnailers",
    mimeType: string,
    className: string
  ) => void;
  onEditDefaultEmbedder: () => void;
  onEditDefaultLlm: () => void;
}

// ============================================================================
// Helpers
// ============================================================================

const STAGES: { key: StageType; label: string }[] = [
  { key: "parsers", label: "Parser" },
  { key: "embedders", label: "Embedder" },
  { key: "thumbnailers", label: "Thumbnailer" },
];

// ============================================================================
// Component
// ============================================================================

export const FiletypeDefaults = memo<FiletypeDefaultsProps>(
  ({
    components,
    supportedMimeTypes,
    mimeTypesLoading,
    enabledComponents,
    preferredParsers,
    preferredEmbedders,
    preferredThumbnailers,
    defaultEmbedder,
    defaultLlm,
    updating,
    onAssign,
    onEditDefaultEmbedder,
    onEditDefaultLlm,
  }) => {
    // Build a lookup from stage key to its preferred mapping
    const preferredByStage = useMemo(
      () => ({
        parsers: preferredParsers,
        embedders: preferredEmbedders,
        thumbnailers: preferredThumbnailers,
      }),
      [preferredParsers, preferredEmbedders, preferredThumbnailers]
    );

    // Pre-compute available components per stage per MIME type
    const availableComponents = useMemo(() => {
      const result: Record<
        StageType,
        Record<string, (PipelineComponentType & { className: string })[]>
      > = {
        parsers: {},
        embedders: {},
        thumbnailers: {},
      };

      for (const mime of supportedMimeTypes) {
        const shortLabel = mime.fileType.toUpperCase();
        for (const stage of STAGES) {
          result[stage.key][mime.mimetype] = components[stage.key].filter(
            (comp) => isComponentAvailable(comp, shortLabel, enabledComponents)
          );
        }
      }

      return result;
    }, [components, supportedMimeTypes, enabledComponents]);

    const handleChange = useCallback(
      (stage: StageType, mimeType: string, value: string) => {
        onAssign(stage, mimeType, value);
      },
      [onAssign]
    );

    return (
      <Section data-testid="filetype-defaults">
        <SectionHeader>
          <SectionTitle>
            <Settings />
            Filetype Defaults
          </SectionTitle>
        </SectionHeader>

        <DefaultsContainer>
          {/* Header row - hidden on mobile */}
          <DefaultsHeaderRow>
            <span>File Type</span>
            <span>Parser</span>
            <span>Embedder</span>
            <span>Thumbnailer</span>
          </DefaultsHeaderRow>

          {/* One row per MIME type */}
          {mimeTypesLoading && supportedMimeTypes.length === 0 ? (
            <FiletypeRow>
              <div
                style={{
                  gridColumn: "1 / -1",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.5rem",
                  padding: "1rem",
                }}
              >
                <Spinner size="sm" />
                <span>Loading file types...</span>
              </div>
            </FiletypeRow>
          ) : null}
          {supportedMimeTypes.map((mime) => {
            return (
              <FiletypeRow key={mime.mimetype}>
                <FiletypeLabel>
                  {mime.fullySupported ? (
                    <FileText />
                  ) : (
                    <span title="Partially supported: missing pipeline components for some stages">
                      <AlertTriangle
                        style={{ color: PARTIALLY_SUPPORTED_WARNING_COLOR }}
                      />
                    </span>
                  )}
                  {mime.label}
                </FiletypeLabel>

                {STAGES.map((stage) => {
                  const currentValue =
                    preferredByStage[stage.key]?.[mime.mimetype] || "";
                  const available =
                    availableComponents[stage.key][mime.mimetype];
                  const hasNoOptions = available.length === 0;
                  const isUnassigned = !currentValue;

                  return (
                    <div key={stage.key}>
                      <StageDropdownLabel>{stage.label}</StageDropdownLabel>
                      <StyledSelect
                        value={currentValue}
                        $warning={isUnassigned && !hasNoOptions}
                        disabled={updating || hasNoOptions}
                        onChange={(e) =>
                          handleChange(stage.key, mime.mimetype, e.target.value)
                        }
                        aria-label={`${stage.label} for ${mime.label} files`}
                      >
                        {hasNoOptions ? (
                          <option value="">None available</option>
                        ) : (
                          <>
                            <option value="">-- Unassigned --</option>
                            {available.map((comp) => (
                              <option
                                key={comp.className}
                                value={comp.className}
                              >
                                {getComponentDisplayName(
                                  comp.className,
                                  comp.title || undefined
                                )}
                              </option>
                            ))}
                          </>
                        )}
                      </StyledSelect>
                    </div>
                  );
                })}
              </FiletypeRow>
            );
          })}

          {/* Default Embedder row */}
          <FiletypeRow>
            <FiletypeLabel>
              <Cpu />
              Default Embedder
            </FiletypeLabel>
            <div style={{ gridColumn: "2 / -1" }}>
              <DefaultEmbedderDisplay>
                {defaultEmbedder ? (
                  <DefaultEmbedderInfo>
                    <ComponentName>
                      {getComponentDisplayName(defaultEmbedder)}
                    </ComponentName>
                    <DefaultEmbedderPath>{defaultEmbedder}</DefaultEmbedderPath>
                  </DefaultEmbedderInfo>
                ) : (
                  <EmptyValue>Using system default</EmptyValue>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  data-testid="edit-default-embedder"
                  onClick={onEditDefaultEmbedder}
                >
                  Edit
                </Button>
              </DefaultEmbedderDisplay>
            </div>
          </FiletypeRow>

          {/* Default LLM row. Not file-type-scoped: this is the install-wide
              fallback model for agents/chat when no per-corpus or per-agent
              override is set. */}
          <FiletypeRow>
            <FiletypeLabel>
              <Bot />
              Default LLM
            </FiletypeLabel>
            <div style={{ gridColumn: "2 / -1" }}>
              <DefaultEmbedderDisplay>
                {defaultLlm ? (
                  <DefaultEmbedderInfo>
                    <ComponentName>{defaultLlm}</ComponentName>
                  </DefaultEmbedderInfo>
                ) : (
                  <EmptyValue>Using server default</EmptyValue>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  data-testid="edit-default-llm"
                  onClick={onEditDefaultLlm}
                >
                  Edit
                </Button>
              </DefaultEmbedderDisplay>
            </div>
          </FiletypeRow>
        </DefaultsContainer>
      </Section>
    );
  }
);

FiletypeDefaults.displayName = "FiletypeDefaults";
