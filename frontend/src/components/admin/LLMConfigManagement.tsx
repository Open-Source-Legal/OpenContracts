/**
 * Admin page for the LLM Configuration system.
 *
 * Three sections in one page (matches the SystemSettings two-column / mobile-tab
 * pattern but kept inline because the LLM surface is smaller):
 *
 *   1. Providers — credential cards keyed by registered provider class.
 *   2. Models    — admin-curated rows (CRUD + enable toggle).
 *   3. Default   — single "system default model" picker.
 */
import React, { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@apollo/client";
import { toast } from "react-toastify";
import {
  Button,
  Input,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Spinner,
} from "@os-legal/ui";
import {
  AlertTriangle,
  ChevronLeft,
  CircleAlert,
  CircleCheck,
  Cpu,
  KeyRound,
  Plus,
  Save,
  Settings,
  Trash2,
} from "lucide-react";

import {
  CREATE_LLM_MODEL,
  DELETE_LLM_MODEL,
  DELETE_LLM_PROVIDER_CREDENTIALS,
  GET_LLM_CONFIG_SETTINGS,
  GET_LLM_MODELS,
  GET_LLM_PROVIDERS,
  LLMConfigSettings,
  LLMModel,
  LLMProvider,
  SET_DEFAULT_LLM_MODEL,
  UPDATE_LLM_MODEL,
  UPDATE_LLM_PROVIDER_CREDENTIALS,
} from "./llm_config/graphql";
import {
  Container,
  BackButton,
  PageHeader,
  PageTitle,
  PageDescription,
  LoadingContainer,
  ErrorContainer,
  ErrorMessage,
  WarningBanner,
  WarningText,
  FormField,
  FormLabel,
  FormHelperText,
  SecretFieldGroup,
  SecretFieldRow,
  SecretFieldHeader,
  SecretStatusIndicator,
  RequiredBadge,
} from "./system_settings/styles";

// --------------------------------------------------------------------------- //

interface ProvidersQuery {
  llmProviders: LLMProvider[];
}

interface SettingsQuery {
  llmConfigSettings: LLMConfigSettings;
}

interface ModelsQuery {
  llmModels: LLMModel[];
}

const EMPTY_MODEL_FORM = {
  modelName: "",
  displayName: "",
  description: "",
  isEnabled: true,
  supportsVision: false,
  supportsTools: true,
  supportsStructuredOutput: true,
  maxContextTokens: "",
  defaultTemperature: "0.3",
};

type ModelForm = typeof EMPTY_MODEL_FORM;

// --------------------------------------------------------------------------- //

export const LLMConfigManagement: React.FC = () => {
  const navigate = useNavigate();

  const {
    data: providersData,
    loading: providersLoading,
    error: providersError,
    refetch: refetchProviders,
  } = useQuery<ProvidersQuery>(GET_LLM_PROVIDERS, {
    fetchPolicy: "cache-and-network",
  });

  const {
    data: settingsData,
    loading: settingsLoading,
    error: settingsError,
    refetch: refetchSettings,
  } = useQuery<SettingsQuery>(GET_LLM_CONFIG_SETTINGS, {
    fetchPolicy: "network-only",
  });

  const {
    data: modelsData,
    loading: modelsLoading,
    error: modelsError,
    refetch: refetchModels,
  } = useQuery<ModelsQuery>(GET_LLM_MODELS, {
    fetchPolicy: "cache-and-network",
  });

  const refetchAll = useCallback(() => {
    refetchProviders();
    refetchSettings();
    refetchModels();
  }, [refetchProviders, refetchSettings, refetchModels]);

  // Mutations -------------------------------------------------------------- //

  const [updateCredentials, { loading: savingCreds }] = useMutation(
    UPDATE_LLM_PROVIDER_CREDENTIALS,
    {
      onCompleted: (data) => {
        if (data.updateLlmProviderCredentials?.ok) {
          toast.success("Credentials saved");
          setActiveProvider(null);
          setCredentialValues({});
          refetchAll();
        } else {
          toast.error(
            data.updateLlmProviderCredentials?.message ||
              "Failed to save credentials"
          );
        }
      },
      onError: (err) => toast.error(`Error: ${err.message}`),
    }
  );

  const [deleteCredentials] = useMutation(DELETE_LLM_PROVIDER_CREDENTIALS, {
    onCompleted: (data) => {
      if (data.deleteLlmProviderCredentials?.ok) {
        toast.success("Credentials cleared");
        refetchAll();
      } else {
        toast.error(
          data.deleteLlmProviderCredentials?.message ||
            "Failed to clear credentials"
        );
      }
    },
  });

  const [createModel, { loading: creatingModel }] = useMutation(
    CREATE_LLM_MODEL,
    {
      onCompleted: (data) => {
        if (data.createLlmModel?.ok) {
          toast.success("Model added");
          setEditingProviderKey(null);
          setModelForm(EMPTY_MODEL_FORM);
          refetchModels();
        } else {
          toast.error(data.createLlmModel?.message || "Failed to add model");
        }
      },
    }
  );

  const [updateModel] = useMutation(UPDATE_LLM_MODEL, {
    onCompleted: (data) => {
      if (data.updateLlmModel?.ok) {
        refetchModels();
        refetchSettings();
      } else {
        toast.error(data.updateLlmModel?.message || "Failed to update model");
      }
    },
  });

  const [deleteModel] = useMutation(DELETE_LLM_MODEL, {
    onCompleted: (data) => {
      if (data.deleteLlmModel?.ok) {
        toast.success("Model deleted");
        refetchModels();
        refetchSettings();
      } else {
        toast.error(data.deleteLlmModel?.message || "Failed to delete model");
      }
    },
  });

  const [setDefaultModel] = useMutation(SET_DEFAULT_LLM_MODEL, {
    onCompleted: () => refetchSettings(),
  });

  // UI state --------------------------------------------------------------- //

  const [activeProvider, setActiveProvider] = useState<string | null>(null);
  const [credentialValues, setCredentialValues] = useState<
    Record<string, string>
  >({});
  const [editingProviderKey, setEditingProviderKey] = useState<string | null>(
    null
  );
  const [modelForm, setModelForm] = useState<ModelForm>(EMPTY_MODEL_FORM);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const providers = providersData?.llmProviders ?? [];
  const settings = settingsData?.llmConfigSettings;
  const models = modelsData?.llmModels ?? [];

  const modelsByProvider = useMemo(() => {
    const map = new Map<string, LLMModel[]>();
    for (const model of models) {
      const list = map.get(model.providerKey) ?? [];
      list.push(model);
      map.set(model.providerKey, list);
    }
    return map;
  }, [models]);

  const activeProviderDef = activeProvider
    ? providers.find((p) => p.key === activeProvider) ?? null
    : null;

  // Handlers --------------------------------------------------------------- //

  const handleConfigureClick = useCallback((provider: LLMProvider) => {
    setActiveProvider(provider.key);
    const template: Record<string, string> = {};
    for (const field of provider.credentialSchema) {
      template[field.name] = field.default ?? "";
    }
    setCredentialValues(template);
  }, []);

  const handleSaveCredentials = useCallback(() => {
    if (!activeProviderDef) return;
    const filtered: Record<string, string> = {};
    for (const field of activeProviderDef.credentialSchema) {
      const value = credentialValues[field.name];
      if (value === undefined) continue;
      // Empty string for a secret means "leave existing alone";
      // empty string for a non-secret means "clear".
      if (field.isSecret && value === "") continue;
      filtered[field.name] = value;
    }
    updateCredentials({
      variables: {
        providerKey: activeProviderDef.key,
        credentials: filtered,
      },
    });
  }, [activeProviderDef, credentialValues, updateCredentials]);

  const handleClearProvider = useCallback(
    (providerKey: string) => {
      deleteCredentials({ variables: { providerKey } });
    },
    [deleteCredentials]
  );

  const handleAddModelClick = useCallback(
    (provider: LLMProvider) => {
      setEditingProviderKey(provider.key);
      setModelForm({
        ...EMPTY_MODEL_FORM,
        modelName: provider.defaultModels[0] ?? "",
      });
    },
    []
  );

  const handleSaveNewModel = useCallback(() => {
    if (!editingProviderKey) return;
    if (!modelForm.modelName.trim() || !modelForm.displayName.trim()) {
      toast.error("Model name and display name are required");
      return;
    }
    createModel({
      variables: {
        providerKey: editingProviderKey,
        modelName: modelForm.modelName.trim(),
        displayName: modelForm.displayName.trim(),
        description: modelForm.description || undefined,
        isEnabled: modelForm.isEnabled,
        supportsVision: modelForm.supportsVision,
        supportsTools: modelForm.supportsTools,
        supportsStructuredOutput: modelForm.supportsStructuredOutput,
        maxContextTokens: modelForm.maxContextTokens
          ? parseInt(modelForm.maxContextTokens, 10)
          : undefined,
        defaultTemperature: parseFloat(modelForm.defaultTemperature || "0.3"),
      },
    });
  }, [createModel, editingProviderKey, modelForm]);

  const handleToggleEnabled = useCallback(
    (model: LLMModel, isEnabled: boolean) => {
      updateModel({ variables: { id: model.id, isEnabled } });
    },
    [updateModel]
  );

  const handleDeleteModel = useCallback(() => {
    if (!confirmDeleteId) return;
    deleteModel({ variables: { id: confirmDeleteId } });
    setConfirmDeleteId(null);
  }, [confirmDeleteId, deleteModel]);

  const handleSetDefault = useCallback(
    (modelId: string | null) => {
      setDefaultModel({ variables: { id: modelId } });
    },
    [setDefaultModel]
  );

  // Render guards ---------------------------------------------------------- //

  if (providersLoading || settingsLoading || modelsLoading) {
    return (
      <Container>
        <LoadingContainer>
          <Spinner size="lg" />
          <span>Loading LLM configuration…</span>
        </LoadingContainer>
      </Container>
    );
  }

  const queryError = providersError || settingsError || modelsError;
  if (queryError) {
    return (
      <Container>
        <BackButton onClick={() => navigate("/admin/settings")}>
          <ChevronLeft />
          Back to Admin Settings
        </BackButton>
        <ErrorContainer>
          <AlertTriangle />
          <h3>Error Loading LLM Configuration</h3>
          <ErrorMessage>
            {queryError.message ||
              "Unable to load LLM configuration. You may not have permission to view this page."}
          </ErrorMessage>
          <Button variant="primary" onClick={refetchAll}>
            Try Again
          </Button>
        </ErrorContainer>
      </Container>
    );
  }

  // Render ---------------------------------------------------------------- //

  return (
    <Container>
      <BackButton onClick={() => navigate("/admin/settings")}>
        <ChevronLeft />
        Back to Admin Settings
      </BackButton>

      <PageHeader>
        <PageTitle>
          <Cpu />
          LLM Configuration
        </PageTitle>
        <PageDescription>
          Register provider credentials, curate which models are available, and
          choose a system default. Columns whose chosen model becomes
          unavailable will fail extraction with a clear message.
        </PageDescription>
      </PageHeader>

      <WarningBanner>
        <AlertTriangle />
        <WarningText>
          <strong>Superuser Only:</strong> API keys are encrypted at rest with
          Fernet (Django <code>SECRET_KEY</code>-derived). Rotating{" "}
          <code>SECRET_KEY</code> renders stored keys unrecoverable.
        </WarningText>
      </WarningBanner>

      {/* ------------- Providers ---------------------------------------- */}
      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <KeyRound /> Providers
        </h2>
        <p>
          One card per provider class registered in code. Configuring a provider
          means supplying credentials so its models can be invoked.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(20rem, 1fr))",
            gap: "1rem",
          }}
        >
          {providers.map((provider) => (
            <div
              key={provider.key}
              data-testid={`llm-provider-card-${provider.key}`}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 8,
                padding: "1rem",
                background: provider.isConfigured ? "#f0fdf4" : "#fff",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{provider.title}</strong>
                <SecretStatusIndicator $populated={provider.isConfigured}>
                  {provider.isConfigured ? (
                    <>
                      <CircleCheck /> Configured
                    </>
                  ) : (
                    <>
                      <CircleAlert /> Not configured
                    </>
                  )}
                </SecretStatusIndicator>
              </div>
              <p
                style={{
                  fontSize: "0.875rem",
                  color: "#4b5563",
                  marginTop: "0.5rem",
                }}
              >
                {provider.description}
              </p>
              <div
                style={{
                  display: "flex",
                  gap: "0.5rem",
                  marginTop: "1rem",
                  flexWrap: "wrap",
                }}
              >
                <Button
                  variant="primary"
                  onClick={() => handleConfigureClick(provider)}
                >
                  Configure credentials
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleAddModelClick(provider)}
                >
                  <Plus
                    style={{ width: 14, height: 14, marginRight: 4 }}
                  />
                  Add model
                </Button>
                {provider.isConfigured && (
                  <Button
                    variant="secondary"
                    onClick={() => handleClearProvider(provider.key)}
                  >
                    Clear
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ------------- Models ------------------------------------------- */}
      <section style={{ marginTop: "2rem" }}>
        <h2 style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <Settings /> Registered models
        </h2>
        <p>
          Admin-curated rows. Disable to hide from column editors without
          deleting; columns referencing a disabled or unavailable model fail
          fast with a descriptive message.
        </p>

        {providers.map((provider) => {
          const providerModels = modelsByProvider.get(provider.key) ?? [];
          if (providerModels.length === 0) return null;
          return (
            <div key={provider.key} style={{ marginBottom: "1.5rem" }}>
              <h3>{provider.title}</h3>
              <div style={{ display: "grid", gap: "0.5rem" }}>
                {providerModels.map((model) => (
                  <div
                    key={model.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "1rem",
                      padding: "0.75rem 1rem",
                      border: "1px solid #e5e7eb",
                      borderRadius: 6,
                      opacity: model.isAvailable ? 1 : 0.55,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={model.isEnabled}
                      onChange={(e) =>
                        handleToggleEnabled(model, e.target.checked)
                      }
                      aria-label={`Enable ${model.displayName}`}
                    />
                    <div style={{ flex: 1 }}>
                      <div>
                        <strong>{model.displayName}</strong>
                        <code
                          style={{
                            marginLeft: "0.5rem",
                            fontSize: "0.75rem",
                            color: "#6b7280",
                          }}
                        >
                          {model.pydanticAiString}
                        </code>
                      </div>
                      {!model.isAvailable && (
                        <span
                          style={{ fontSize: "0.75rem", color: "#b45309" }}
                        >
                          Not currently usable —
                          {" "}
                          {model.isEnabled
                            ? "provider has no credentials"
                            : "model disabled"}
                        </span>
                      )}
                    </div>
                    <Button
                      variant="secondary"
                      onClick={() => setConfirmDeleteId(model.id)}
                      aria-label={`Delete ${model.displayName}`}
                    >
                      <Trash2 style={{ width: 14, height: 14 }} />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          );
        })}

        {models.length === 0 && (
          <p style={{ color: "#6b7280" }}>
            No models registered yet. Use "Add model" on a provider card above.
          </p>
        )}
      </section>

      {/* ------------- Default ------------------------------------------ */}
      <section style={{ marginTop: "2rem" }}>
        <h2>System default model</h2>
        <p>
          Used whenever a column has no preferred model set. Only available
          models can be chosen as the default.
        </p>
        <FormField>
          <FormLabel>Default model</FormLabel>
          <select
            value={settings?.defaultModel?.id ?? ""}
            onChange={(e) =>
              handleSetDefault(e.target.value ? e.target.value : null)
            }
            data-testid="llm-default-model-select"
            style={{
              padding: "0.5rem",
              border: "1px solid #d1d5db",
              borderRadius: 6,
              minWidth: 280,
            }}
          >
            <option value="">— No default —</option>
            {models
              .filter((m) => m.isAvailable)
              .map((m) => (
                <option key={m.id} value={m.id}>
                  {m.displayName} ({m.pydanticAiString})
                </option>
              ))}
          </select>
          <FormHelperText>
            If a column has no preferred model and no default is set,
            extractions for that column fail with a configuration error.
          </FormHelperText>
        </FormField>
      </section>

      {/* ------------- Modals ------------------------------------------- */}

      {/* Credentials modal */}
      <Modal
        open={Boolean(activeProvider)}
        onClose={() => {
          setActiveProvider(null);
          setCredentialValues({});
        }}
        size="md"
      >
        <ModalHeader
          title={`Configure — ${activeProviderDef?.title ?? ""}`}
          onClose={() => {
            setActiveProvider(null);
            setCredentialValues({});
          }}
        />
        <ModalBody>
          <WarningBanner>
            <AlertTriangle />
            <WarningText>
              Secret values are encrypted at rest and never displayed again.
            </WarningText>
          </WarningBanner>
          <SecretFieldGroup>
            {activeProviderDef?.credentialSchema.map((field) => (
              <SecretFieldRow key={field.name}>
                <SecretFieldHeader>
                  <FormLabel
                    htmlFor={`cred-${field.name}`}
                    style={{ marginBottom: 0 }}
                  >
                    {field.label}
                  </FormLabel>
                  {field.required && (
                    <RequiredBadge>
                      <AlertTriangle />
                      Required
                    </RequiredBadge>
                  )}
                </SecretFieldHeader>
                <Input
                  id={`cred-${field.name}`}
                  type={field.isSecret ? "password" : "text"}
                  value={credentialValues[field.name] ?? ""}
                  onChange={(e) =>
                    setCredentialValues((prev) => ({
                      ...prev,
                      [field.name]: e.target.value,
                    }))
                  }
                  placeholder={
                    field.isSecret
                      ? "Leave blank to keep existing value"
                      : field.default ?? ""
                  }
                  fullWidth
                />
                {field.description && (
                  <FormHelperText>{field.description}</FormHelperText>
                )}
              </SecretFieldRow>
            ))}
          </SecretFieldGroup>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => {
              setActiveProvider(null);
              setCredentialValues({});
            }}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSaveCredentials}
            loading={savingCreds}
          >
            <Save style={{ width: 16, height: 16, marginRight: 8 }} />
            Save credentials
          </Button>
        </ModalFooter>
      </Modal>

      {/* Add model modal */}
      <Modal
        open={Boolean(editingProviderKey)}
        onClose={() => setEditingProviderKey(null)}
        size="md"
      >
        <ModalHeader
          title={`Add model — ${
            providers.find((p) => p.key === editingProviderKey)?.title ?? ""
          }`}
          onClose={() => setEditingProviderKey(null)}
        />
        <ModalBody>
          <FormField>
            <FormLabel>Model name (provider identifier)</FormLabel>
            <Input
              value={modelForm.modelName}
              onChange={(e) =>
                setModelForm((p) => ({ ...p, modelName: e.target.value }))
              }
              placeholder="e.g. gpt-4o-mini"
              fullWidth
            />
            <FormHelperText>
              The exact identifier the provider uses. The pydantic-ai prefix is
              prepended automatically.
            </FormHelperText>
          </FormField>
          <FormField>
            <FormLabel>Display name</FormLabel>
            <Input
              value={modelForm.displayName}
              onChange={(e) =>
                setModelForm((p) => ({ ...p, displayName: e.target.value }))
              }
              placeholder="e.g. GPT-4o mini"
              fullWidth
            />
          </FormField>
          <FormField>
            <FormLabel>Description (optional)</FormLabel>
            <Input
              value={modelForm.description}
              onChange={(e) =>
                setModelForm((p) => ({ ...p, description: e.target.value }))
              }
              fullWidth
            />
          </FormField>
          <FormField>
            <FormLabel>Default temperature</FormLabel>
            <Input
              type="number"
              step={0.05}
              value={modelForm.defaultTemperature}
              onChange={(e) =>
                setModelForm((p) => ({
                  ...p,
                  defaultTemperature: e.target.value,
                }))
              }
            />
          </FormField>
          <FormField>
            <FormLabel>Max context tokens (optional)</FormLabel>
            <Input
              type="number"
              value={modelForm.maxContextTokens}
              onChange={(e) =>
                setModelForm((p) => ({
                  ...p,
                  maxContextTokens: e.target.value,
                }))
              }
              placeholder="e.g. 128000"
            />
          </FormField>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
            <label>
              <input
                type="checkbox"
                checked={modelForm.supportsTools}
                onChange={(e) =>
                  setModelForm((p) => ({
                    ...p,
                    supportsTools: e.target.checked,
                  }))
                }
              />{" "}
              Tools
            </label>
            <label>
              <input
                type="checkbox"
                checked={modelForm.supportsStructuredOutput}
                onChange={(e) =>
                  setModelForm((p) => ({
                    ...p,
                    supportsStructuredOutput: e.target.checked,
                  }))
                }
              />{" "}
              Structured output
            </label>
            <label>
              <input
                type="checkbox"
                checked={modelForm.supportsVision}
                onChange={(e) =>
                  setModelForm((p) => ({
                    ...p,
                    supportsVision: e.target.checked,
                  }))
                }
              />{" "}
              Vision
            </label>
            <label>
              <input
                type="checkbox"
                checked={modelForm.isEnabled}
                onChange={(e) =>
                  setModelForm((p) => ({ ...p, isEnabled: e.target.checked }))
                }
              />{" "}
              Enabled
            </label>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setEditingProviderKey(null)}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSaveNewModel}
            loading={creatingModel}
          >
            <Plus style={{ width: 16, height: 16, marginRight: 8 }} />
            Add model
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete confirmation */}
      <Modal
        open={Boolean(confirmDeleteId)}
        onClose={() => setConfirmDeleteId(null)}
        size="sm"
      >
        <ModalHeader
          title="Delete model"
          onClose={() => setConfirmDeleteId(null)}
        />
        <ModalBody>
          <WarningBanner>
            <AlertTriangle />
            <WarningText>
              Columns currently referencing this model will fall back to the
              system default. This cannot be undone.
            </WarningText>
          </WarningBanner>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setConfirmDeleteId(null)}
          >
            Cancel
          </Button>
          <Button variant="primary" onClick={handleDeleteModel}>
            <Trash2 style={{ width: 16, height: 16, marginRight: 8 }} />
            Delete
          </Button>
        </ModalFooter>
      </Modal>
    </Container>
  );
};

export default LLMConfigManagement;
