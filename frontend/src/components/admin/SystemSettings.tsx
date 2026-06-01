import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery, useMutation } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Spinner,
} from "@os-legal/ui";
import {
  Settings,
  ChevronLeft,
  Save,
  RotateCcw,
  AlertTriangle,
  Info,
  Trash2,
  CircleCheck,
  CircleAlert,
} from "lucide-react";
import { toast } from "react-toastify";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { PipelineComponentType } from "../../types/graphql-api";
import { getComponentDisplayName } from "./PipelineIcons";
import { PIPELINE_UI } from "../../assets/configurations/constants";
import { CORPUS_BREAKPOINTS } from "../corpuses/styles/corpusDesignTokens";
import { formatSettingLabel } from "../../utils/formatters";

// Sub-module imports
import {
  GET_PIPELINE_SETTINGS,
  GET_PIPELINE_COMPONENTS,
  GET_SUPPORTED_MIME_TYPES,
  UPDATE_PIPELINE_SETTINGS,
  RESET_PIPELINE_SETTINGS,
  UPDATE_COMPONENT_SECRETS,
  DELETE_COMPONENT_SECRETS,
  PipelineSettingsQueryResult,
  PipelineComponentsQueryResult,
  SupportedMimeTypesQueryResult,
} from "./system_settings/graphql";
import { SettingsSchemaEntry } from "./system_settings/types";
import { STAGE_CONFIG } from "./system_settings/config";
import {
  Container,
  BackButton,
  PageHeader,
  PageTitle,
  PageDescription,
  LastModified,
  ActionButtons,
  LoadingContainer,
  ErrorContainer,
  ErrorMessage,
  WarningBanner,
  WarningText,
  SecretFieldGroup,
  SecretFieldRow,
  SecretFieldHeader,
  SecretStatusIndicator,
  RequiredBadge,
  FormField,
  FormLabel,
  FormHelperText,
  SettingsTwoColumnLayout,
  SettingsLeftColumn,
  SettingsRightColumn,
  MobileSettingsTabContainer,
  MobileSettingsTabList,
  MobileSettingsTab,
  MobileSettingsTabPanel,
} from "./system_settings/styles";
import { ComponentLibrary } from "./system_settings/ComponentLibrary";
import { FiletypeDefaults } from "./system_settings/FiletypeDefaults";

// ============================================================================
// Constants
// ============================================================================

const SETTINGS_TABS = ["library", "defaults"] as const;
type SettingsTab = (typeof SETTINGS_TABS)[number];

// ============================================================================
// Component
// ============================================================================

export const SystemSettings: React.FC = () => {
  const navigate = useNavigate();

  // Layout state - JS-based media query so only one layout mounts at a time
  const [isMobile, setIsMobile] = useState(
    () => window.innerWidth <= CORPUS_BREAKPOINTS.tablet
  );
  const [activeTab, setActiveTab] = useState<SettingsTab>("library");

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${CORPUS_BREAKPOINTS.tablet}px)`);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Keyboard navigation for mobile tabs (WAI-ARIA horizontal tabs pattern)
  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const currentIndex = SETTINGS_TABS.indexOf(activeTab);
      let nextIndex: number | null = null;

      switch (e.key) {
        case "ArrowLeft":
          nextIndex =
            currentIndex === 0 ? SETTINGS_TABS.length - 1 : currentIndex - 1;
          break;
        case "ArrowRight":
          nextIndex =
            currentIndex === SETTINGS_TABS.length - 1 ? 0 : currentIndex + 1;
          break;
        case "Home":
          nextIndex = 0;
          break;
        case "End":
          nextIndex = SETTINGS_TABS.length - 1;
          break;
        default:
          return;
      }

      e.preventDefault();
      const nextTab = SETTINGS_TABS[nextIndex];
      setActiveTab(nextTab);
      document.getElementById(`settings-tab-${nextTab}`)?.focus();
    },
    [activeTab]
  );

  // Modal states
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [showSecretsModal, setShowSecretsModal] = useState(false);
  const [secretsComponentPath, setSecretsComponentPath] = useState("");
  const [secretsValues, setSecretsValues] = useState<Record<string, string>>(
    {}
  );
  const [showDefaultEmbedderModal, setShowDefaultEmbedderModal] =
    useState(false);
  const [defaultEmbedderValue, setDefaultEmbedderValue] = useState("");
  const [showDefaultLlmModal, setShowDefaultLlmModal] = useState(false);
  const [defaultLlmValue, setDefaultLlmValue] = useState("");
  const [showDeleteSecretsConfirm, setShowDeleteSecretsConfirm] =
    useState(false);
  const [deleteSecretsPath, setDeleteSecretsPath] = useState("");

  // GraphQL queries.
  //
  // NOTE: ComponentLibrary reads `component.enabled` from GET_PIPELINE_COMPONENTS,
  // while FiletypeDefaults reads `enabledComponents` from GET_PIPELINE_SETTINGS.
  // Both are refetched after each mutation (see onCompleted handlers below), but
  // they are independent network calls. In the brief window between one resolving
  // and the other, the two panels may show transiently inconsistent enabled state.
  // The server enforces consistency, so this is cosmetic only.
  const {
    data: settingsData,
    loading: settingsLoading,
    error: settingsError,
    refetch: refetchSettings,
  } = useQuery<PipelineSettingsQueryResult>(GET_PIPELINE_SETTINGS, {
    fetchPolicy: "network-only",
  });

  const {
    data: componentsData,
    loading: componentsLoading,
    error: componentsError,
    refetch: refetchComponents,
  } = useQuery<PipelineComponentsQueryResult>(GET_PIPELINE_COMPONENTS, {
    fetchPolicy: "cache-and-network",
  });

  const {
    data: mimeTypesData,
    loading: mimeTypesLoading,
    error: mimeTypesError,
  } = useQuery<SupportedMimeTypesQueryResult>(GET_SUPPORTED_MIME_TYPES, {
    fetchPolicy: "cache-first",
  });

  // Mutations
  const [updateSettings, { loading: updating }] = useMutation(
    UPDATE_PIPELINE_SETTINGS,
    {
      onCompleted: (data) => {
        if (data.updatePipelineSettings?.ok) {
          toast.success("Settings updated successfully");
          refetchSettings();
          refetchComponents();
        } else {
          toast.error(
            data.updatePipelineSettings?.message || "Failed to update settings"
          );
        }
      },
      onError: (err) => {
        toast.error(`Error updating settings: ${err.message}`);
      },
    }
  );

  const [resetSettings, { loading: resetting }] = useMutation(
    RESET_PIPELINE_SETTINGS,
    {
      onCompleted: (data) => {
        if (data.resetPipelineSettings?.ok) {
          toast.success("Settings reset to defaults");
          setShowResetConfirm(false);
          refetchSettings();
          refetchComponents();
        } else {
          toast.error(
            data.resetPipelineSettings?.message || "Failed to reset settings"
          );
        }
      },
      onError: (err) => {
        toast.error(`Error resetting settings: ${err.message}`);
      },
    }
  );

  const [updateSecrets, { loading: updatingSecrets }] = useMutation(
    UPDATE_COMPONENT_SECRETS,
    {
      onCompleted: (data) => {
        if (data.updateComponentSecrets?.ok) {
          toast.success("Secrets updated successfully");
          setShowSecretsModal(false);
          setSecretsComponentPath("");
          setSecretsValues({});
          refetchSettings();
          refetchComponents();
        } else {
          toast.error(
            data.updateComponentSecrets?.message || "Failed to update secrets"
          );
        }
      },
      onError: (err) => {
        toast.error(`Error updating secrets: ${err.message}`);
      },
    }
  );

  const [deleteSecrets, { loading: deletingSecrets }] = useMutation(
    DELETE_COMPONENT_SECRETS,
    {
      onCompleted: (data) => {
        if (data.deleteComponentSecrets?.ok) {
          toast.success("Secrets deleted successfully");
          refetchSettings();
          refetchComponents();
        } else {
          toast.error(
            data.deleteComponentSecrets?.message || "Failed to delete secrets"
          );
        }
      },
      onError: (err) => {
        toast.error(`Error deleting secrets: ${err.message}`);
      },
    }
  );

  const settings = settingsData?.pipelineSettings;
  const components = componentsData?.pipelineComponents;

  const componentsByStage = useMemo(() => {
    const parsers = (components?.parsers || []).filter(
      (comp): comp is PipelineComponentType & { className: string } =>
        Boolean(comp?.className)
    );
    const embedders = (components?.embedders || []).filter(
      (comp): comp is PipelineComponentType & { className: string } =>
        Boolean(comp?.className)
    );
    const thumbnailers = (components?.thumbnailers || []).filter(
      (comp): comp is PipelineComponentType & { className: string } =>
        Boolean(comp?.className)
    );
    const llmProviders = (components?.llmProviders || []).filter(
      (comp): comp is PipelineComponentType & { className: string } =>
        Boolean(comp?.className)
    );

    return { parsers, embedders, thumbnailers, llmProviders };
  }, [components]);

  const componentByClassName = useMemo(() => {
    const map = new Map<
      string,
      PipelineComponentType & { className: string }
    >();
    for (const comp of [
      ...componentsByStage.parsers,
      ...componentsByStage.embedders,
      ...componentsByStage.thumbnailers,
      ...componentsByStage.llmProviders,
    ]) {
      map.set(comp.className, comp);
    }
    return map;
  }, [componentsByStage]);

  const getComponentSettingsSchema = useCallback(
    (className: string): SettingsSchemaEntry[] => {
      const component = componentByClassName.get(className);
      return (component?.settingsSchema || []).filter(
        (entry): entry is SettingsSchemaEntry => Boolean(entry)
      );
    },
    [componentByClassName]
  );

  const getSecretSettingsForComponent = useCallback(
    (className: string): SettingsSchemaEntry[] => {
      return getComponentSettingsSchema(className).filter(
        (entry) => entry.settingType === "secret"
      );
    },
    [getComponentSettingsSchema]
  );

  const getNonSecretSettingsForComponent = useCallback(
    (className: string): SettingsSchemaEntry[] => {
      return getComponentSettingsSchema(className).filter(
        (entry) => entry.settingType !== "secret"
      );
    },
    [getComponentSettingsSchema]
  );

  // Look up a component's display name by className from loaded components data
  const getComponentDisplayNameByClassName = useCallback(
    (className: string): string => {
      const component = componentByClassName.get(className);
      return getComponentDisplayName(className, component?.title || undefined);
    },
    [componentByClassName]
  );

  // Toggle component enabled state
  const handleToggleEnabled = useCallback(
    (className: string, enabled: boolean) => {
      if (componentsLoading || settingsLoading) {
        toast.warning("Components are still loading. Please wait.");
        return;
      }

      const currentEnabled: string[] = (
        settings?.enabledComponents || []
      ).filter((s): s is string => s != null);
      let newEnabled: string[];

      if (currentEnabled.length === 0 && enabled) {
        // Safe no-op: the checkbox's `checked` reflects `component.enabled ?? true`,
        // so enabling when already in the "all enabled" (empty-list) state is
        // unreachable via normal UI interaction. Guard kept for defensive safety.
        return;
      }

      if (currentEnabled.length === 0 && !enabled) {
        // Transitioning from "all enabled" to explicit list: build full list
        // from loaded components, then remove the one being disabled.
        // LLM providers MUST be included here — omitting them would drop every
        // provider from the freshly-built explicit list, silently disabling
        // them as a side effect of toggling an unrelated component.
        const allPaths = [
          ...componentsByStage.parsers,
          ...componentsByStage.embedders,
          ...componentsByStage.thumbnailers,
          ...componentsByStage.llmProviders,
        ].map((c) => c.className);

        if (allPaths.length === 0) {
          toast.warning("No components available.");
          return;
        }

        // Deduplicate paths in case a className appears across stages
        const uniquePaths = [...new Set(allPaths)];

        newEnabled = uniquePaths.filter((p) => p !== className);
      } else {
        newEnabled = enabled
          ? [...new Set([...currentEnabled, className])]
          : currentEnabled.filter((p: string) => p !== className);
      }

      // NOTE: When disabling the last component, newEnabled becomes [].
      // The backend interprets [] as "all enabled" (no filter), so this
      // effectively re-enables everything. This is pre-existing behavior;
      // a future improvement could add a dedicated "disable all" state.

      updateSettings({
        variables: { enabledComponents: newEnabled },
      });
    },
    [
      settings,
      componentsByStage,
      componentsLoading,
      settingsLoading,
      updateSettings,
    ]
  );

  // Assign a component to a filetype default
  const handleAssign = useCallback(
    (
      stage: "parsers" | "embedders" | "thumbnailers",
      mimeType: string,
      className: string
    ) => {
      const settingsKey = STAGE_CONFIG[stage].settingsKey;
      const currentMapping =
        (settings?.[settingsKey] as Record<string, string> | undefined) ?? {};
      const newMapping = { ...currentMapping };

      if (className) {
        newMapping[mimeType] = className;
      } else {
        delete newMapping[mimeType];
      }

      updateSettings({
        variables: { [settingsKey]: newMapping },
      });
    },
    [settings, updateSettings]
  );

  // Handle secrets modal
  const handleAddSecrets = useCallback(
    (componentPath: string) => {
      setSecretsComponentPath(componentPath);
      const secretSettings = getSecretSettingsForComponent(componentPath);
      const template = Object.fromEntries(
        secretSettings.map((entry) => [entry.name, ""])
      );
      setSecretsValues(template);
      setShowSecretsModal(true);
    },
    [getSecretSettingsForComponent]
  );

  const handleSaveSecrets = useCallback(() => {
    const componentPath = secretsComponentPath.trim();
    if (!componentPath) {
      toast.error("Please select a component before saving secrets.");
      return;
    }

    const secretSettings = getSecretSettingsForComponent(componentPath);
    if (secretSettings.length === 0) {
      toast.error("Selected component does not accept secret settings.");
      return;
    }

    // Build secrets object from only non-empty values (empty means "don't update")
    const secrets: Record<string, string> = {};
    for (const [key, value] of Object.entries(secretsValues)) {
      if (value.trim()) {
        secrets[key] = value;
      }
    }

    if (Object.keys(secrets).length === 0) {
      toast.error("Please provide at least one secret value.");
      return;
    }

    const secretsJson = JSON.stringify(secrets);
    const secretsBytes = new TextEncoder().encode(secretsJson).length;
    if (secretsBytes > PIPELINE_UI.MAX_SECRET_SIZE_BYTES) {
      toast.error(
        `Secrets payload exceeds ${PIPELINE_UI.MAX_SECRET_SIZE_BYTES} bytes.`
      );
      return;
    }

    // Check required fields that have no existing value and no new value
    const missingRequired = secretSettings.filter((entry) => {
      if (!entry.required) return false;
      const newValue = secretsValues[entry.name]?.trim();
      // Missing if no new value provided AND no existing value
      return !newValue && !entry.hasValue;
    });
    if (missingRequired.length > 0) {
      const missingLabels = missingRequired.map((entry) =>
        formatSettingLabel(entry.name, entry.description)
      );
      toast.error(`Missing required secrets: ${missingLabels.join(", ")}`);
      return;
    }

    updateSecrets({
      variables: {
        componentPath,
        secrets,
        merge: true,
      },
    });
  }, [
    getSecretSettingsForComponent,
    secretsComponentPath,
    secretsValues,
    updateSecrets,
  ]);

  const handleDeleteSecretsClick = useCallback((componentPath: string) => {
    setDeleteSecretsPath(componentPath);
    setShowDeleteSecretsConfirm(true);
  }, []);

  const handleConfirmDeleteSecrets = useCallback(() => {
    deleteSecrets({
      variables: {
        componentPath: deleteSecretsPath,
      },
    });
    setShowDeleteSecretsConfirm(false);
    setDeleteSecretsPath("");
  }, [deleteSecrets, deleteSecretsPath]);

  // Handle saving non-secret component settings
  const handleSaveComponentSettings = useCallback(
    (componentPath: string, values: Record<string, string>) => {
      // Build the component_settings update: merge with existing
      const existing = settings?.componentSettings ?? {};
      const existingForComponent =
        (existing as Record<string, Record<string, unknown>>)[componentPath] ??
        {};

      // Coerce values to proper types based on schema
      const schema = getNonSecretSettingsForComponent(componentPath);
      const coerced: Record<string, unknown> = {};
      for (const entry of schema) {
        const raw = values[entry.name];
        if (raw === undefined || raw === "") continue;
        switch (entry.pythonType) {
          case "int":
            coerced[entry.name] = parseInt(raw, 10);
            break;
          case "float":
            coerced[entry.name] = parseFloat(raw);
            break;
          case "bool":
            coerced[entry.name] = raw === "true";
            break;
          default:
            coerced[entry.name] = raw;
        }
      }

      const updatedComponentSettings = {
        ...existing,
        [componentPath]: { ...existingForComponent, ...coerced },
      };

      updateSettings({
        variables: {
          componentSettings: updatedComponentSettings,
        },
      });
    },
    [settings, getNonSecretSettingsForComponent, updateSettings]
  );

  // Handle default embedder
  const handleEditDefaultEmbedder = useCallback(() => {
    setDefaultEmbedderValue(settings?.defaultEmbedder || "");
    setShowDefaultEmbedderModal(true);
  }, [settings]);

  const handleSaveDefaultEmbedder = useCallback(() => {
    updateSettings({
      variables: {
        defaultEmbedder: defaultEmbedderValue || null,
      },
    });
    setShowDefaultEmbedderModal(false);
  }, [defaultEmbedderValue, updateSettings]);

  // Handle default LLM. The value is a pydantic-ai model spec
  // ("{provider}:{model}"), not a component class path. An empty string
  // clears the override so resolution falls back to the Django settings
  // default — so we send "" (not null) on save.
  const handleEditDefaultLlm = useCallback(() => {
    setDefaultLlmValue(settings?.defaultLlm || "");
    setShowDefaultLlmModal(true);
  }, [settings]);

  const handleSaveDefaultLlm = useCallback(() => {
    updateSettings({
      variables: {
        defaultLlm: defaultLlmValue.trim(),
      },
    });
    setShowDefaultLlmModal(false);
  }, [defaultLlmValue, updateSettings]);

  // Format date
  const formatDate = useCallback((dateStr: string | null | undefined) => {
    if (!dateStr) return "Never";
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  }, []);

  const supportedMimeTypes = mimeTypesData?.supportedMimeTypes ?? [];

  // Shared props for ComponentLibrary and FiletypeDefaults (avoids duplication
  // between desktop two-column and mobile tab layouts)
  const componentLibraryProps = useMemo(
    () => ({
      components: componentsByStage,
      updating,
      componentsLoading,
      settingsLoading,
      onToggleEnabled: handleToggleEnabled,
      onAddSecrets: handleAddSecrets,
      onDeleteSecrets: handleDeleteSecretsClick,
      onSaveConfig: handleSaveComponentSettings,
      getConfigSettings: getNonSecretSettingsForComponent,
      getSecretSettings: getSecretSettingsForComponent,
    }),
    [
      componentsByStage,
      updating,
      componentsLoading,
      settingsLoading,
      handleToggleEnabled,
      handleAddSecrets,
      handleDeleteSecretsClick,
      handleSaveComponentSettings,
      getNonSecretSettingsForComponent,
      getSecretSettingsForComponent,
    ]
  );

  const filetypeDefaultsProps = useMemo(
    () => ({
      components: componentsByStage,
      supportedMimeTypes,
      mimeTypesLoading,
      enabledComponents:
        (settings?.enabledComponents?.filter(Boolean) as string[]) ?? [],
      preferredParsers:
        (settings?.preferredParsers as Record<string, string>) || {},
      preferredEmbedders:
        (settings?.preferredEmbedders as Record<string, string>) || {},
      preferredThumbnailers:
        (settings?.preferredThumbnailers as Record<string, string>) || {},
      defaultEmbedder: settings?.defaultEmbedder || "",
      defaultLlm: settings?.defaultLlm || "",
      updating,
      onAssign: handleAssign,
      onEditDefaultEmbedder: handleEditDefaultEmbedder,
      onEditDefaultLlm: handleEditDefaultLlm,
    }),
    [
      componentsByStage,
      supportedMimeTypes,
      mimeTypesLoading,
      settings?.enabledComponents,
      settings?.preferredParsers,
      settings?.preferredEmbedders,
      settings?.preferredThumbnailers,
      settings?.defaultEmbedder,
      settings?.defaultLlm,
      updating,
      handleAssign,
      handleEditDefaultEmbedder,
      handleEditDefaultLlm,
    ]
  );

  // Loading state
  if (settingsLoading || componentsLoading) {
    return (
      <Container>
        <LoadingContainer>
          <Spinner size="lg" />
          <span>Loading pipeline settings...</span>
        </LoadingContainer>
      </Container>
    );
  }

  // Error state
  const queryError = settingsError || componentsError || mimeTypesError;
  if (queryError) {
    return (
      <Container>
        <BackButton onClick={() => navigate("/admin/settings")}>
          <ChevronLeft />
          Back to Admin Settings
        </BackButton>
        <ErrorContainer>
          <AlertTriangle />
          <h3>Error Loading Settings</h3>
          <ErrorMessage>
            {queryError.message ||
              "Unable to load pipeline settings. You may not have permission to view this page."}
          </ErrorMessage>
          <Button
            variant="primary"
            onClick={() => {
              refetchSettings();
              refetchComponents();
            }}
          >
            Try Again
          </Button>
        </ErrorContainer>
      </Container>
    );
  }

  return (
    <Container>
      <BackButton onClick={() => navigate("/admin/settings")}>
        <ChevronLeft />
        Back to Admin Settings
      </BackButton>

      <PageHeader>
        <PageTitle>
          <Settings />
          Pipeline Configuration
        </PageTitle>
        <PageDescription>
          Configure how documents are processed through the ingestion pipeline.
          Select components for each stage based on file type.
        </PageDescription>
        {settings?.modified && (
          <LastModified>
            <Info />
            Last modified: {formatDate(settings.modified)}
            {settings.modifiedBy?.username &&
              ` by ${settings.modifiedBy.username}`}
          </LastModified>
        )}
      </PageHeader>

      <WarningBanner>
        <AlertTriangle />
        <WarningText>
          <strong>Superuser Only:</strong> Changes affect all users and take
          effect immediately for new uploads. Existing documents are not
          reprocessed.
        </WarningText>
      </WarningBanner>

      {/* Conditionally render one layout to avoid double-mounting */}
      {isMobile ? (
        <MobileSettingsTabContainer>
          <MobileSettingsTabList role="tablist">
            <MobileSettingsTab
              id="settings-tab-library"
              role="tab"
              tabIndex={activeTab === "library" ? 0 : -1}
              aria-selected={activeTab === "library"}
              aria-controls="settings-panel-library"
              $active={activeTab === "library"}
              onClick={() => setActiveTab("library")}
              onKeyDown={handleTabKeyDown}
            >
              Component Library
            </MobileSettingsTab>
            <MobileSettingsTab
              id="settings-tab-defaults"
              role="tab"
              tabIndex={activeTab === "defaults" ? 0 : -1}
              aria-selected={activeTab === "defaults"}
              aria-controls="settings-panel-defaults"
              $active={activeTab === "defaults"}
              onClick={() => setActiveTab("defaults")}
              onKeyDown={handleTabKeyDown}
            >
              Filetype Defaults
            </MobileSettingsTab>
          </MobileSettingsTabList>

          <MobileSettingsTabPanel
            id={`settings-panel-${activeTab}`}
            role="tabpanel"
            aria-labelledby={`settings-tab-${activeTab}`}
            tabIndex={0}
          >
            {activeTab === "library" ? (
              <ComponentLibrary {...componentLibraryProps} />
            ) : (
              <FiletypeDefaults {...filetypeDefaultsProps} />
            )}
          </MobileSettingsTabPanel>
        </MobileSettingsTabContainer>
      ) : (
        <SettingsTwoColumnLayout>
          <SettingsLeftColumn>
            <ComponentLibrary {...componentLibraryProps} />
          </SettingsLeftColumn>
          <SettingsRightColumn>
            <FiletypeDefaults {...filetypeDefaultsProps} />
          </SettingsRightColumn>
        </SettingsTwoColumnLayout>
      )}

      {/* Reset to Defaults */}
      <ActionButtons>
        <Button
          variant="secondary"
          onClick={() => setShowResetConfirm(true)}
          disabled={resetting}
        >
          <RotateCcw style={{ width: 16, height: 16, marginRight: 8 }} />
          Reset to Defaults
        </Button>
      </ActionButtons>

      {/* Reset Confirmation Modal */}
      <Modal
        open={showResetConfirm}
        onClose={() => setShowResetConfirm(false)}
        size="sm"
      >
        <ModalHeader
          title="Reset to Defaults"
          onClose={() => setShowResetConfirm(false)}
        />
        <ModalBody>
          <WarningBanner>
            <AlertTriangle />
            <WarningText>
              This will reset all pipeline settings to their Django
              configuration defaults. This action cannot be undone.
            </WarningText>
          </WarningBanner>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setShowResetConfirm(false)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => resetSettings()}
            loading={resetting}
          >
            <RotateCcw style={{ width: 16, height: 16, marginRight: 8 }} />
            Reset Settings
          </Button>
        </ModalFooter>
      </Modal>

      {/* Secrets Modal */}
      <Modal
        open={showSecretsModal}
        onClose={() => setShowSecretsModal(false)}
        size="md"
      >
        <ModalHeader
          title={`Configure Secrets \u2014 ${getComponentDisplayNameByClassName(
            secretsComponentPath
          )}`}
          onClose={() => setShowSecretsModal(false)}
        />
        <ModalBody>
          <WarningBanner>
            <AlertTriangle />
            <WarningText>
              <strong>Security Notice:</strong> Secrets are encrypted and stored
              securely. They will never be displayed again after saving.
            </WarningText>
          </WarningBanner>
          <SecretFieldGroup>
            {getSecretSettingsForComponent(secretsComponentPath).map(
              (entry) => (
                <SecretFieldRow key={entry.name}>
                  <SecretFieldHeader>
                    <FormLabel
                      style={{ marginBottom: 0 }}
                      htmlFor={`secret-${entry.name}`}
                    >
                      {formatSettingLabel(entry.name, entry.description)}
                    </FormLabel>
                    {entry.required && (
                      <RequiredBadge>
                        <AlertTriangle />
                        Required
                      </RequiredBadge>
                    )}
                    <SecretStatusIndicator $populated={!!entry.hasValue}>
                      {entry.hasValue ? (
                        <>
                          <CircleCheck /> Set
                        </>
                      ) : (
                        <>
                          <CircleAlert /> Not set
                        </>
                      )}
                    </SecretStatusIndicator>
                  </SecretFieldHeader>
                  <Input
                    id={`secret-${entry.name}`}
                    type="password"
                    value={secretsValues[entry.name] ?? ""}
                    onChange={(e) =>
                      setSecretsValues((prev) => ({
                        ...prev,
                        [entry.name]: e.target.value,
                      }))
                    }
                    placeholder={
                      entry.hasValue
                        ? "Leave blank to keep current value"
                        : "Enter value..."
                    }
                    fullWidth
                  />
                  {entry.envVar && (
                    <FormHelperText>
                      Can also be set via env var: {entry.envVar}
                    </FormHelperText>
                  )}
                </SecretFieldRow>
              )
            )}
          </SecretFieldGroup>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setShowSecretsModal(false)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSaveSecrets}
            loading={updatingSecrets}
            disabled={
              !secretsComponentPath ||
              Object.values(secretsValues).every((v) => !v.trim())
            }
          >
            <Save style={{ width: 16, height: 16, marginRight: 8 }} />
            Save Secrets
          </Button>
        </ModalFooter>
      </Modal>

      {/* Default Embedder Modal */}
      <Modal
        open={showDefaultEmbedderModal}
        onClose={() => setShowDefaultEmbedderModal(false)}
        size="md"
      >
        <ModalHeader
          title="Edit Default Embedder"
          onClose={() => setShowDefaultEmbedderModal(false)}
        />
        <ModalBody>
          <FormField>
            <FormLabel>Default Embedder Class Path</FormLabel>
            <Input
              id="default-embedder"
              value={defaultEmbedderValue}
              onChange={(e) => setDefaultEmbedderValue(e.target.value)}
              placeholder="e.g., opencontractserver.pipeline.embedders.sent_transformer_microservice.MicroserviceEmbedder"
              fullWidth
            />
            <FormHelperText>
              Full Python class path. Leave empty to use system default.
            </FormHelperText>
          </FormField>
          {components?.embedders && components.embedders.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <FormLabel>Available Embedders:</FormLabel>
              {components.embedders
                .filter(
                  (e): e is PipelineComponentType & { className: string } =>
                    Boolean(e?.className)
                )
                .map((e) => (
                  <div
                    key={e.className}
                    style={{
                      padding: "0.75rem",
                      fontSize: "0.875rem",
                      cursor: "pointer",
                      borderRadius: "8px",
                      marginBottom: "0.5rem",
                      background:
                        defaultEmbedderValue === e.className
                          ? "#e0e7ff"
                          : OS_LEGAL_COLORS.surfaceHover,
                      border: `1px solid ${
                        defaultEmbedderValue === e.className
                          ? "#6366f1"
                          : OS_LEGAL_COLORS.border
                      }`,
                    }}
                    onClick={() => setDefaultEmbedderValue(e.className)}
                  >
                    <strong>{e.title || e.name}</strong>
                    {e.vectorSize && (
                      <span
                        style={{
                          color: OS_LEGAL_COLORS.textSecondary,
                          marginLeft: "0.5rem",
                        }}
                      >
                        ({e.vectorSize}d)
                      </span>
                    )}
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: OS_LEGAL_COLORS.textSecondary,
                        fontFamily: "monospace",
                        marginTop: "0.25rem",
                      }}
                    >
                      {e.className}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setShowDefaultEmbedderModal(false)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSaveDefaultEmbedder}
            loading={updating}
          >
            <Save style={{ width: 16, height: 16, marginRight: 8 }} />
            Save
          </Button>
        </ModalFooter>
      </Modal>

      {/* Default LLM Modal */}
      <Modal
        open={showDefaultLlmModal}
        onClose={() => setShowDefaultLlmModal(false)}
        size="md"
      >
        <ModalHeader
          title="Edit Default LLM"
          onClose={() => setShowDefaultLlmModal(false)}
        />
        <ModalBody>
          <FormField>
            <FormLabel>Default LLM Model Spec</FormLabel>
            <Input
              id="default-llm"
              value={defaultLlmValue}
              onChange={(e) => setDefaultLlmValue(e.target.value)}
              placeholder="e.g., anthropic:claude-opus-4-6"
              fullWidth
            />
            <FormHelperText>
              pydantic-ai model spec in "provider:model" form. Leave empty to
              fall back to the server default. Per-corpus and per-agent settings
              still take precedence over this value.
            </FormHelperText>
          </FormField>
          {componentsByStage.llmProviders.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <FormLabel>
                Registered Providers &amp; Suggested Models:
              </FormLabel>
              {componentsByStage.llmProviders.map((provider) => {
                const providerKey = provider.providerKey || "";
                const models = (provider.supportedModels || []).filter(
                  (m): m is string => Boolean(m)
                );
                return (
                  <div
                    key={provider.className}
                    style={{ marginTop: "0.75rem" }}
                  >
                    <div
                      style={{
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        marginBottom: "0.375rem",
                      }}
                    >
                      {provider.title || provider.name}
                      {provider.requiresApiKey && (
                        <span
                          style={{
                            marginLeft: 6,
                            fontSize: "0.75rem",
                            fontWeight: 400,
                            color: OS_LEGAL_COLORS.textSecondary,
                          }}
                        >
                          (API key required)
                        </span>
                      )}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.375rem",
                      }}
                    >
                      {models.length > 0 ? (
                        models.map((model) => {
                          const spec = providerKey
                            ? `${providerKey}:${model}`
                            : model;
                          const selected = defaultLlmValue === spec;
                          return (
                            <button
                              key={spec}
                              type="button"
                              onClick={() => setDefaultLlmValue(spec)}
                              style={{
                                padding: "0.25rem 0.625rem",
                                fontSize: "0.75rem",
                                cursor: "pointer",
                                borderRadius: "9999px",
                                background: selected
                                  ? "#e0e7ff"
                                  : OS_LEGAL_COLORS.surfaceHover,
                                border: `1px solid ${
                                  selected ? "#6366f1" : OS_LEGAL_COLORS.border
                                }`,
                                color: OS_LEGAL_COLORS.textPrimary,
                              }}
                            >
                              {model}
                            </button>
                          );
                        })
                      ) : (
                        <span
                          style={{
                            fontSize: "0.75rem",
                            color: OS_LEGAL_COLORS.textSecondary,
                          }}
                        >
                          No suggested models — enter a spec manually
                          {providerKey ? ` (prefix: ${providerKey}:)` : ""}.
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setShowDefaultLlmModal(false)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSaveDefaultLlm}
            loading={updating}
          >
            <Save style={{ width: 16, height: 16, marginRight: 8 }} />
            Save
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete Secrets Confirmation Modal */}
      <Modal
        open={showDeleteSecretsConfirm}
        onClose={() => setShowDeleteSecretsConfirm(false)}
        size="sm"
      >
        <ModalHeader
          title="Delete Component Secrets"
          onClose={() => setShowDeleteSecretsConfirm(false)}
        />
        <ModalBody>
          <WarningBanner>
            <AlertTriangle />
            <WarningText>
              Are you sure you want to delete secrets for{" "}
              <strong>
                {getComponentDisplayNameByClassName(deleteSecretsPath)}
              </strong>
              ? This action cannot be undone.
            </WarningText>
          </WarningBanner>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setShowDeleteSecretsConfirm(false)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleConfirmDeleteSecrets}
            loading={deletingSecrets}
          >
            <Trash2 style={{ width: 16, height: 16, marginRight: 8 }} />
            Delete Secrets
          </Button>
        </ModalFooter>
      </Modal>
    </Container>
  );
};

export default SystemSettings;
