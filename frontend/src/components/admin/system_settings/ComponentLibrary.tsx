import React, { memo, useMemo, useState, useCallback } from "react";
import { Input } from "@os-legal/ui";
import { Package, Search, Key } from "lucide-react";
import { PipelineComponentType } from "../../../types/graphql-api";
import { MIME_TO_SHORT_LABEL } from "../../../assets/configurations/constants";
import { getComponentDisplayName } from "../PipelineIcons";
import { SettingsSchemaEntry, LibraryStageType } from "./types";
import { LIBRARY_STAGE_CONFIG } from "./config";
import { AdvancedSettingsPanel } from "./AdvancedSettingsPanel";
import {
  Section,
  SectionHeader,
  SectionTitle,
  LibraryContainer,
  FilterBar,
  FilterChip,
  SearchInputWrapper,
  ComponentListItem,
  ComponentInfo,
  ComponentTitle,
  ComponentDescription,
  BadgeRow,
  StageBadge,
  FileTypeBadge,
  NoComponents,
} from "./styles";

// ============================================================================
// Types
// ============================================================================

type FilterCategory = "all" | LibraryStageType;

interface FlatComponent {
  component: PipelineComponentType & { className: string };
  stage: LibraryStageType;
}

interface ComponentLibraryProps {
  components: {
    parsers: (PipelineComponentType & { className: string })[];
    embedders: (PipelineComponentType & { className: string })[];
    thumbnailers: (PipelineComponentType & { className: string })[];
    llmProviders: (PipelineComponentType & { className: string })[];
  };
  updating: boolean;
  componentsLoading: boolean;
  settingsLoading: boolean;
  onToggleEnabled: (className: string, enabled: boolean) => void;
  onAddSecrets: (componentPath: string) => void;
  onDeleteSecrets: (componentPath: string) => void;
  onSaveConfig: (componentPath: string, values: Record<string, string>) => void;
  getConfigSettings: (className: string) => SettingsSchemaEntry[];
  getSecretSettings: (className: string) => SettingsSchemaEntry[];
}

// ============================================================================
// Filter categories
// ============================================================================

const FILTER_OPTIONS: { value: FilterCategory; label: string }[] = [
  { value: "all", label: "All" },
  { value: "parsers", label: "Parsers" },
  { value: "embedders", label: "Embedders" },
  { value: "thumbnailers", label: "Thumbnailers" },
  { value: "llmProviders", label: "LLM Providers" },
];

// ============================================================================
// Component
// ============================================================================

export const ComponentLibrary = memo<ComponentLibraryProps>(
  ({
    components,
    updating,
    componentsLoading,
    settingsLoading,
    onToggleEnabled,
    onAddSecrets,
    onDeleteSecrets,
    onSaveConfig,
    getConfigSettings,
    getSecretSettings,
  }) => {
    const [filter, setFilter] = useState<FilterCategory>("all");
    const [searchQuery, setSearchQuery] = useState("");
    const [expandedComponent, setExpandedComponent] = useState<string | null>(
      null
    );

    // Flatten all components into a single list with stage metadata
    const allComponents = useMemo<FlatComponent[]>(() => {
      const result: FlatComponent[] = [];
      const stages: LibraryStageType[] = [
        "parsers",
        "embedders",
        "thumbnailers",
        "llmProviders",
      ];
      for (const stage of stages) {
        for (const comp of components[stage]) {
          if (comp?.className) {
            result.push({ component: comp, stage });
          }
        }
      }
      return result;
    }, [components]);

    // Filter and search
    const filteredComponents = useMemo(() => {
      let items = allComponents;

      // Stage filter
      if (filter !== "all") {
        items = items.filter((item) => item.stage === filter);
      }

      // Search filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        items = items.filter((item) => {
          const displayName = getComponentDisplayName(
            item.component.className,
            item.component.title || undefined
          ).toLowerCase();
          const description = (item.component.description || "").toLowerCase();
          const className = item.component.className.toLowerCase();
          return (
            displayName.includes(query) ||
            description.includes(query) ||
            className.includes(query)
          );
        });
      }

      return items;
    }, [allComponents, filter, searchQuery]);

    const handleToggleSettings = useCallback((className: string) => {
      setExpandedComponent((prev) => (prev === className ? null : className));
    }, []);

    const handleSearchChange = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>) => {
        setSearchQuery(e.target.value);
      },
      []
    );

    return (
      <Section data-testid="component-library">
        <SectionHeader>
          <SectionTitle>
            <Package />
            Pipeline Components
          </SectionTitle>
        </SectionHeader>

        <LibraryContainer>
          {/* Filter bar */}
          <FilterBar>
            {FILTER_OPTIONS.map((opt) => (
              <FilterChip
                key={opt.value}
                data-testid={`library-filter-${opt.value}`}
                $active={filter === opt.value}
                onClick={() => setFilter(opt.value)}
                aria-pressed={filter === opt.value}
              >
                {opt.label}
              </FilterChip>
            ))}
            <SearchInputWrapper>
              <Input
                placeholder="Search components..."
                value={searchQuery}
                onChange={handleSearchChange}
                fullWidth
                leftIcon={<Search style={{ width: 14, height: 14 }} />}
              />
            </SearchInputWrapper>
          </FilterBar>

          {/* Component list */}
          {filteredComponents.length > 0 ? (
            filteredComponents.map(({ component, stage }) => {
              const isEnabled = component.enabled ?? true;
              const stageConfig = LIBRARY_STAGE_CONFIG[stage];
              const isLlmProvider = stage === "llmProviders";
              const displayName = getComponentDisplayName(
                component.className,
                component.title || undefined
              );
              const settingsKey = `library-${component.className}`;
              const isExpanded = expandedComponent === component.className;
              const configSettings = getConfigSettings(component.className);
              const secretSettings = getSecretSettings(component.className);
              const hasSettings =
                configSettings.length > 0 || secretSettings.length > 0;

              // LLM providers are not file-type-scoped: surface their suggested
              // models as chips instead of file-type badges. Other stages map
              // their supported file types to short labels.
              const modelBadges = isLlmProvider
                ? (component.supportedModels || []).filter((m): m is string =>
                    Boolean(m)
                  )
                : [];
              const fileTypeBadges = isLlmProvider
                ? []
                : (component.supportedFileTypes || []).map((ft) => {
                    const label =
                      MIME_TO_SHORT_LABEL[ft] ||
                      ft.split("/").pop()?.toUpperCase() ||
                      ft;
                    return label;
                  });

              return (
                <ComponentListItem
                  key={component.className}
                  $disabled={!isEnabled}
                >
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    disabled={updating || componentsLoading || settingsLoading}
                    onChange={(e) =>
                      onToggleEnabled(component.className, e.target.checked)
                    }
                    aria-label={`${
                      isEnabled ? "Disable" : "Enable"
                    } ${displayName}`}
                    style={{
                      width: 16,
                      height: 16,
                      marginTop: 2,
                      cursor:
                        updating || componentsLoading || settingsLoading
                          ? "not-allowed"
                          : "pointer",
                      accentColor: stageConfig.color,
                    }}
                  />
                  <ComponentInfo>
                    <div>
                      <ComponentTitle>{displayName}</ComponentTitle>
                    </div>
                    {component.description && (
                      <div>
                        <ComponentDescription>
                          {component.description}
                        </ComponentDescription>
                      </div>
                    )}
                    <BadgeRow>
                      <StageBadge $color={stageConfig.color}>
                        {stageConfig.title}
                      </StageBadge>
                      {isLlmProvider && component.requiresApiKey && (
                        <FileTypeBadge
                          title="This provider needs an API credential. Set it below (stored encrypted) to configure it live, or leave it to the process environment (e.g. ANTHROPIC_API_KEY)."
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                          }}
                        >
                          <Key style={{ width: 11, height: 11 }} />
                          API key
                        </FileTypeBadge>
                      )}
                      {modelBadges.map((model) => (
                        <FileTypeBadge key={model}>{model}</FileTypeBadge>
                      ))}
                      {fileTypeBadges.map((label) => (
                        <FileTypeBadge key={label}>{label}</FileTypeBadge>
                      ))}
                    </BadgeRow>

                    {/* Expandable settings */}
                    {hasSettings && (
                      <AdvancedSettingsPanel
                        currentSelection={component.className}
                        configSettings={configSettings}
                        secretSettings={secretSettings}
                        isExpanded={isExpanded}
                        settingsKey={settingsKey}
                        saving={updating}
                        onToggle={() =>
                          handleToggleSettings(component.className)
                        }
                        onAddSecrets={onAddSecrets}
                        onDeleteSecrets={onDeleteSecrets}
                        onSaveConfig={onSaveConfig}
                      />
                    )}
                  </ComponentInfo>
                </ComponentListItem>
              );
            })
          ) : (
            <NoComponents>No components match the current filter</NoComponents>
          )}
        </LibraryContainer>
      </Section>
    );
  }
);

ComponentLibrary.displayName = "ComponentLibrary";
