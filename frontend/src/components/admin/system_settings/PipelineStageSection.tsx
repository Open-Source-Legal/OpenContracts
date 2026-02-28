import React, { memo } from "react";
import { PipelineComponentType } from "../../../types/graphql-api";
import { SUPPORTED_MIME_TYPES } from "../../../assets/configurations/constants";
import { PipelineStageSectionProps } from "./types";
import { PipelineComponentCard } from "./PipelineComponentCard";
import { AdvancedSettingsPanel } from "./AdvancedSettingsPanel";
import {
  StageCardContainer,
  StageCardHeader,
  StageHeaderInfo,
  StageNumberBadge,
  StageTitle,
  StageSubtitle,
  MimeSelector,
  MimeButton,
  StageCardContent,
  ComponentGrid,
  NoComponents,
} from "./styles";

/**
 * Renders a complete pipeline stage with header, component grid, and settings.
 */
export const PipelineStageSection = memo<PipelineStageSectionProps>(
  ({
    stage,
    stageIndex,
    config,
    mimeType,
    components,
    currentSelection,
    configSettings,
    secretSettings,
    isExpanded,
    settingsKey,
    updating,
    onMimeTypeChange,
    onSelectComponent,
    onToggleSettings,
    onAddSecrets,
    onDeleteSecrets,
    onSaveConfig,
  }) => {
    const hasSelection = currentSelection !== null;

    return (
      <StageCardContainer $active={hasSelection}>
        <StageCardHeader>
          <StageHeaderInfo>
            <StageNumberBadge $active={hasSelection}>
              {stageIndex + 1}
            </StageNumberBadge>
            <div>
              <StageTitle>{config.title}</StageTitle>
              <StageSubtitle>{config.subtitle}</StageSubtitle>
            </div>
          </StageHeaderInfo>
          <MimeSelector
            role="group"
            aria-label={`${config.title} file type filter`}
          >
            {SUPPORTED_MIME_TYPES.map((mime) => (
              <MimeButton
                key={mime.value}
                $active={mimeType === mime.value}
                onClick={() => onMimeTypeChange(stage, mime.value)}
                aria-pressed={mimeType === mime.value}
                aria-label={`Filter ${config.title} by ${mime.label}`}
              >
                {mime.shortLabel}
              </MimeButton>
            ))}
          </MimeSelector>
        </StageCardHeader>
        <StageCardContent>
          {components.length > 0 ? (
            <ComponentGrid>
              {components
                .filter(
                  (
                    comp
                  ): comp is PipelineComponentType & {
                    className: string;
                  } => Boolean(comp?.className)
                )
                .map((comp) => (
                  <PipelineComponentCard
                    key={comp.className}
                    component={comp}
                    isSelected={currentSelection === comp.className}
                    color={config.color}
                    stageTitle={config.title}
                    disabled={updating}
                    onSelect={() =>
                      onSelectComponent(stage, mimeType, comp.className)
                    }
                  />
                ))}
            </ComponentGrid>
          ) : (
            <NoComponents>
              No components available for{" "}
              {SUPPORTED_MIME_TYPES.find((m) => m.value === mimeType)?.label ||
                mimeType}
            </NoComponents>
          )}

          {/* Advanced Settings */}
          {currentSelection && (
            <AdvancedSettingsPanel
              currentSelection={currentSelection}
              configSettings={configSettings}
              secretSettings={secretSettings}
              isExpanded={isExpanded}
              settingsKey={settingsKey}
              saving={updating}
              onToggle={() => onToggleSettings(settingsKey)}
              onAddSecrets={onAddSecrets}
              onDeleteSecrets={onDeleteSecrets}
              onSaveConfig={onSaveConfig}
            />
          )}
        </StageCardContent>
      </StageCardContainer>
    );
  }
);

PipelineStageSection.displayName = "PipelineStageSection";
