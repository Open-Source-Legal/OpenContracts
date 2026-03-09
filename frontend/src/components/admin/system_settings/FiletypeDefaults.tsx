import React, { memo, useMemo, useCallback } from "react";
import { Button } from "@os-legal/ui";
import { FileText, Cpu, Settings, AlertTriangle } from "lucide-react";
import {
  PipelineComponentType,
  SupportedFileTypeInfo,
} from "../../../types/graphql-api";
import { getComponentDisplayName } from "../PipelineIcons";
import { StageType } from "./types";
import { isComponentAvailable } from "./utils";
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
  supportedFileTypes?: SupportedFileTypeInfo[];
  enabledComponents: string[];
  preferredParsers: Record<string, string>;
  preferredEmbedders: Record<string, string>;
  preferredThumbnailers: Record<string, string>;
  defaultEmbedder: string;
  updating: boolean;
  onAssign: (
    stage: "parsers" | "embedders" | "thumbnailers",
    mimeType: string,
    className: string
  ) => void;
  onEditDefaultEmbedder: () => void;
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
    supportedFileTypes,
    enabledComponents,
    preferredParsers,
    preferredEmbedders,
    preferredThumbnailers,
    defaultEmbedder,
    updating,
    onAssign,
    onEditDefaultEmbedder,
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

    // Use dynamically-derived file types from the registry
    const fileTypes = useMemo(
      () => supportedFileTypes ?? [],
      [supportedFileTypes]
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

      for (const ft of fileTypes) {
        for (const stage of STAGES) {
          result[stage.key][ft.mimetype] = components[stage.key].filter(
            (comp) =>
              isComponentAvailable(comp, ft.shortLabel, enabledComponents)
          );
        }
      }

      return result;
    }, [components, enabledComponents, fileTypes]);

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

          {/* One row per dynamically-derived MIME type */}
          {fileTypes.map((ft) => {
            return (
              <FiletypeRow key={ft.mimetype}>
                <FiletypeLabel>
                  <FileText />
                  {ft.shortLabel}
                  {!ft.fullCoverage && (
                    <AlertTriangle
                      size={14}
                      style={{ color: "#d97706", marginLeft: 4 }}
                      title={
                        "Partial coverage: " +
                        (!ft.hasParser ? "no parser " : "") +
                        (!ft.hasEmbedder ? "no embedder " : "") +
                        (!ft.hasThumbnailer ? "no thumbnailer" : "")
                      }
                    />
                  )}
                </FiletypeLabel>

                {STAGES.map((stage) => {
                  const currentValue =
                    preferredByStage[stage.key]?.[ft.mimetype] || "";
                  const available =
                    availableComponents[stage.key][ft.mimetype] ?? [];
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
                          handleChange(stage.key, ft.mimetype, e.target.value)
                        }
                        aria-label={`${stage.label} for ${ft.label}`}
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
                  onClick={onEditDefaultEmbedder}
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
