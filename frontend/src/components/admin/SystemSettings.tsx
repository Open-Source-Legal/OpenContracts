import React, { useState, useCallback, useRef, useMemo } from "react";
import { useQuery, useMutation } from "@apollo/client";
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
  Cpu,
  Info,
  Save,
  RotateCcw,
  AlertTriangle,
  Trash2,
  CircleCheck,
  CircleAlert,
} from "lucide-react";
import { toast } from "react-toastify";
import { PipelineComponentType } from "../../types/graphql-api";
import { getComponentDisplayName } from "./PipelineIcons";
import {
  PIPELINE_UI,
  SUPPORTED_MIME_TYPES,
  MIME_TO_SHORT_LABEL,
} from "../../assets/configurations/constants";
import { formatSettingLabel } from "../../utils/formatters";

// Sub-module imports
import {
  GET_PIPELINE_SETTINGS,
  GET_PIPELINE_COMPONENTS,
  UPDATE_PIPELINE_SETTINGS,
  RESET_PIPELINE_SETTINGS,
  UPDATE_COMPONENT_SECRETS,
  DELETE_COMPONENT_SECRETS,
  PipelineSettingsQueryResult,
  PipelineComponentsQueryResult,
} from "./system_settings/graphql";
import { StageType, SettingsSchemaEntry } from "./system_settings/types";
import { STAGE_CONFIG } from "./system_settings/config";
import {
  PipelineContainer,
  PipelineDescription,
  LastModified,
  Section,
  SectionHeader,
  SectionTitle,
  SectionDescription,
  DefaultEmbedderDisplay,
  DefaultEmbedderInfo,
  DefaultEmbedderPath,
  ComponentName,
  EmptyValue,
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
  EmbedderOption,
  EmbedderOptionTitle,
  EmbedderOptionMeta,
  EmbedderOptionPath,
} from "./system_settings/styles";
import { PipelineStageSection } from "./system_settings/PipelineStageSection";

// ============================================================================
// Component
// ============================================================================

export const SystemSettings: React.FC = () => {
  // Per-stage MIME type selection
  const [selectedMimeTypes, setSelectedMimeTypes] = useState<
    Record<StageType, string>
  >({
    parsers: "application/pdf",
    embedders: "application/pdf",
    thumbnailers: "application/pdf",
  });

  // Advanced settings expansion state
  const [expandedSettings, setExpandedSettings] = useState<
    Record<string, boolean>
  >({});

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
  const [showDeleteSecretsConfirm, setShowDeleteSecretsConfirm] =
    useState(false);
  const [deleteSecretsPath, setDeleteSecretsPath] = useState("");

  // Ref for tracking pending auto-expand after component selection
  const pendingAutoExpandRef = useRef<{
    stage: StageType;
    mimeType: string;
    className: string;
  } | null>(null);

  // GraphQL queries
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
    refetch: refetchComponents,
  } = useQuery<PipelineComponentsQueryResult>(GET_PIPELINE_COMPONENTS, {
    fetchPolicy: "cache-and-network",
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

          // Handle pending auto-expand for components requiring configuration
          const pending = pendingAutoExpandRef.current;
          if (pending) {
            const allSettings = getComponentSettingsSchema(pending.className);
            const hasAnySettings = allSettings.length > 0;
            const hasAnyMissing = allSettings.some(
              (s) => s.required && !s.hasValue
            );

            if (hasAnySettings && hasAnyMissing) {
              setExpandedSettings((prev) => ({
                ...prev,
                [`${pending.stage}-${pending.mimeType}`]: true,
              }));
            }
            pendingAutoExpandRef.current = null;
          }
        } else {
          toast.error(
            data.updatePipelineSettings?.message || "Failed to update settings"
          );
          pendingAutoExpandRef.current = null;
        }
      },
      onError: (err) => {
        toast.error(`Error updating settings: ${err.message}`);
        pendingAutoExpandRef.current = null;
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

    return { parsers, embedders, thumbnailers };
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
    ]) {
      map.set(comp.className, comp);
    }
    return map;
  }, [componentsByStage]);

  const normalizedSupportedFileTypes = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const comp of componentByClassName.values()) {
      const fileTypes = (comp.supportedFileTypes || [])
        .filter((ft): ft is NonNullable<typeof ft> => Boolean(ft))
        .map((ft) => String(ft).toLowerCase());
      map.set(comp.className, fileTypes);
    }
    return map;
  }, [componentByClassName]);

  // Memoize all current selections to avoid repeated lookups during render
  const currentSelections = useMemo(() => {
    if (!settings) return {};
    const selections: Record<string, Record<string, string | null>> = {};
    for (const stage of Object.keys(STAGE_CONFIG) as StageType[]) {
      const mapping = settings[STAGE_CONFIG[stage].settingsKey] as
        | Record<string, string>
        | null
        | undefined;
      selections[stage] = {};
      for (const mime of SUPPORTED_MIME_TYPES) {
        selections[stage][mime.value] = mapping?.[mime.value] ?? null;
      }
    }
    return selections;
  }, [settings]);

  // Get current selection for a stage and MIME type (uses memoized cache)
  const getCurrentSelection = useCallback(
    (stage: StageType, mimeType: string): string | null => {
      return currentSelections[stage]?.[mimeType] ?? null;
    },
    [currentSelections]
  );

  // Get components for a stage, filtered by MIME type support
  const getComponentsForStage = useCallback(
    (stage: StageType, mimeType: string): PipelineComponentType[] => {
      const stageComponents = componentsByStage[stage] || [];

      const mimeTypeLower = mimeType.toLowerCase();
      const mimeShortLower = MIME_TO_SHORT_LABEL[mimeType]?.toLowerCase();

      return stageComponents.filter((comp) => {
        const fileTypes =
          normalizedSupportedFileTypes.get(comp.className) || [];
        if (fileTypes.length === 0) {
          return true;
        }
        if (!mimeShortLower) {
          return false;
        }
        return fileTypes.some(
          (ft) => ft === mimeShortLower || ft === mimeTypeLower
        );
      });
    },
    [componentsByStage, normalizedSupportedFileTypes]
  );

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

  const getComponentDisplayNameByClassName = useCallback(
    (className: string): string => {
      const component = componentByClassName.get(className);
      return getComponentDisplayName(className, component?.title || undefined);
    },
    [componentByClassName]
  );

  // Handle component selection
  const handleSelectComponent = useCallback(
    (stage: StageType, mimeType: string, className: string) => {
      const currentMapping =
        (settings?.[STAGE_CONFIG[stage].settingsKey] as
          | Record<string, string>
          | undefined) ?? {};
      const newMapping = {
        ...currentMapping,
        [mimeType]: className,
      };

      pendingAutoExpandRef.current = { stage, mimeType, className };

      updateSettings({
        variables: {
          [STAGE_CONFIG[stage].settingsKey]: newMapping,
        },
      });
    },
    [settings, updateSettings]
  );

  // Handle MIME type change for a stage
  const handleMimeTypeChange = useCallback(
    (stage: StageType, mimeType: string) => {
      setSelectedMimeTypes((prev) => ({
        ...prev,
        [stage]: mimeType,
      }));
    },
    []
  );

  // Toggle advanced settings
  const toggleAdvancedSettings = useCallback((key: string) => {
    setExpandedSettings((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }, []);

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

    const missingRequired = secretSettings.filter((entry) => {
      if (!entry.required) return false;
      const newValue = secretsValues[entry.name]?.trim();
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
      const existing = settings?.componentSettings ?? {};
      const existingForComponent =
        (existing as Record<string, Record<string, unknown>>)[componentPath] ??
        {};

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

  // Format date
  const formatDate = useCallback((dateStr: string | null | undefined) => {
    if (!dateStr) return "Never";
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  }, []);

  // Render a pipeline stage
  const renderStage = useCallback(
    (stage: StageType, stageIndex: number) => {
      const config = STAGE_CONFIG[stage];
      const mimeType = selectedMimeTypes[stage];
      const stageComponents = getComponentsForStage(stage, mimeType);
      const currentSelection = getCurrentSelection(stage, mimeType);
      const settingsKey = `${stage}-${mimeType}`;
      const isExpanded = expandedSettings[settingsKey] || false;
      const configSettings = currentSelection
        ? getNonSecretSettingsForComponent(currentSelection)
        : [];
      const secretSettings = currentSelection
        ? getSecretSettingsForComponent(currentSelection)
        : [];

      const filteredComponents = stageComponents.filter(
        (comp): comp is PipelineComponentType & { className: string } =>
          Boolean(comp?.className)
      );

      return (
        <PipelineStageSection
          key={stage}
          stage={stage}
          stageIndex={stageIndex}
          config={config}
          mimeType={mimeType}
          components={filteredComponents}
          currentSelection={currentSelection}
          configSettings={configSettings}
          secretSettings={secretSettings}
          isExpanded={isExpanded}
          settingsKey={settingsKey}
          updating={updating}
          onMimeTypeChange={handleMimeTypeChange}
          onSelectComponent={handleSelectComponent}
          onToggleSettings={toggleAdvancedSettings}
          onAddSecrets={handleAddSecrets}
          onDeleteSecrets={handleDeleteSecretsClick}
          onSaveConfig={handleSaveComponentSettings}
        />
      );
    },
    [
      selectedMimeTypes,
      getComponentsForStage,
      getCurrentSelection,
      expandedSettings,
      getNonSecretSettingsForComponent,
      getSecretSettingsForComponent,
      handleMimeTypeChange,
      handleSelectComponent,
      toggleAdvancedSettings,
      handleAddSecrets,
      handleDeleteSecretsClick,
      handleSaveComponentSettings,
      updating,
    ]
  );

  // Loading state
  if (settingsLoading || componentsLoading) {
    return (
      <LoadingContainer>
        <Spinner size="lg" />
        <span>Loading pipeline settings...</span>
      </LoadingContainer>
    );
  }

  // Error state
  if (settingsError) {
    return (
      <ErrorContainer>
        <AlertTriangle />
        <h3>Error Loading Settings</h3>
        <ErrorMessage>
          {settingsError.message ||
            "Unable to load pipeline settings. You may not have permission to view this page."}
        </ErrorMessage>
        <Button variant="primary" onClick={() => refetchSettings()}>
          Try Again
        </Button>
      </ErrorContainer>
    );
  }

  return (
    <>
      <PipelineDescription>
        Configure how documents are processed through the ingestion pipeline.
        Select components for each stage based on file type.
      </PipelineDescription>

      {settings?.modified && (
        <LastModified>
          <Info size={14} />
          Last modified: {formatDate(settings.modified)}
          {settings.modifiedBy?.username &&
            ` by ${settings.modifiedBy.username}`}
        </LastModified>
      )}

      <WarningBanner>
        <AlertTriangle />
        <WarningText>
          <strong>Superuser Only:</strong> Changes affect all users and take
          effect immediately for new uploads. Existing documents are not
          reprocessed.
        </WarningText>
      </WarningBanner>

      {/* Pipeline Stages */}
      <PipelineContainer>
        {renderStage("parsers", 0)}
        {renderStage("thumbnailers", 1)}
        {renderStage("embedders", 2)}
      </PipelineContainer>

      {/* Default Embedder Section */}
      <Section style={{ marginTop: "1.25rem" }}>
        <SectionHeader>
          <SectionTitle>
            <Cpu />
            Default Embedder
          </SectionTitle>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleEditDefaultEmbedder}
          >
            Edit
          </Button>
        </SectionHeader>
        <SectionDescription>
          Fallback embedder when no MIME-type-specific embedder is configured.
        </SectionDescription>
        <DefaultEmbedderDisplay>
          {settings?.defaultEmbedder ? (
            <DefaultEmbedderInfo>
              <ComponentName>
                {getComponentDisplayName(settings.defaultEmbedder)}
              </ComponentName>
              <DefaultEmbedderPath>
                {settings.defaultEmbedder}
              </DefaultEmbedderPath>
            </DefaultEmbedderInfo>
          ) : (
            <EmptyValue>Using system default</EmptyValue>
          )}
        </DefaultEmbedderDisplay>
      </Section>

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
                  <EmbedderOption
                    key={e.className}
                    $selected={defaultEmbedderValue === e.className}
                    onClick={() => setDefaultEmbedderValue(e.className)}
                  >
                    <EmbedderOptionTitle>
                      {e.title || e.name}
                    </EmbedderOptionTitle>
                    {e.vectorSize && (
                      <EmbedderOptionMeta>({e.vectorSize}d)</EmbedderOptionMeta>
                    )}
                    <EmbedderOptionPath>{e.className}</EmbedderOptionPath>
                  </EmbedderOption>
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
    </>
  );
};

export default SystemSettings;
