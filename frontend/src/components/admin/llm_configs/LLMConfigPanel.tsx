/**
 * Superuser admin page for the LLM configuration system (Phase 5).
 *
 * Two tabs:
 *   - Providers — list registered provider classes; per-provider form
 *     for storing api_key + non-secret kwargs (base_url, etc.).
 *   - Models — CRUD for RegisteredLLM rows. Lineage edits create new
 *     versions automatically (the backend immutably preserves history);
 *     archive is a one-way action; "set as default extract LLM" is a
 *     dedicated control on the head row.
 *
 * Lean implementation (~1 page) — does not replicate the full
 * SystemSettings styling subsystem. All actions surface success / error
 * via react-toastify. Refetches after every mutation so the UI never
 * displays stale state.
 */

import React, { useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { Button } from "@os-legal/ui";
import { toast } from "react-toastify";
import {
  ARCHIVE_REGISTERED_LLM,
  DELETE_LLM_PROVIDER_SECRETS,
  GET_LLM_PROVIDERS,
  GET_LLM_SETTINGS,
  GET_REGISTERED_LLMS,
  LLMProvider,
  LLMProvidersResult,
  LLMSettingsResult,
  REGISTER_LLM,
  RegisteredLLM,
  RegisteredLLMsResult,
  SET_DEFAULT_EXTRACT_LLM,
  UPDATE_LLM_PROVIDER_SECRETS,
  UPDATE_REGISTERED_LLM,
} from "./graphql";

// ---------------------------------------------------------------------------
// Local styled-tags — keep deliberately small; the SystemSettings
// styling subsystem is a follow-up adopt.
// ---------------------------------------------------------------------------

const wrapperStyle: React.CSSProperties = {
  padding: "24px 32px",
  maxWidth: 1100,
  margin: "0 auto",
  fontFamily: "system-ui, sans-serif",
};
const tabBarStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  borderBottom: "1px solid #e5e7eb",
  marginBottom: 16,
};
const tabButtonStyle = (active: boolean): React.CSSProperties => ({
  padding: "10px 16px",
  borderBottom: active ? "2px solid #2563eb" : "2px solid transparent",
  background: "none",
  border: 0,
  cursor: "pointer",
  fontWeight: active ? 600 : 500,
  color: active ? "#2563eb" : "#475569",
});
const cardStyle: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  padding: 16,
  marginBottom: 12,
  background: "white",
};
const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  color: "#475569",
  marginBottom: 4,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: 0.5,
};
const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid #cbd5e1",
  fontSize: 14,
  marginBottom: 8,
};
const rowStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr",
  gap: 12,
};
const pillStyle = (color: string): React.CSSProperties => ({
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: 12,
  fontSize: 11,
  fontWeight: 600,
  background: `${color}1a`,
  color,
});

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type Tab = "providers" | "models";

export const LLMConfigPanel: React.FC = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("providers");

  return (
    <div style={wrapperStyle}>
      <Button onClick={() => navigate(-1)} style={{ marginBottom: 16 }}>
        Back
      </Button>
      <h1>LLM Configuration</h1>
      <p style={{ color: "#475569", marginBottom: 24 }}>
        Configure which LLM providers and models extract / chat agents may use.
        Pre-Phase-2 deploys with no admin config keep falling back to the legacy{" "}
        <code>OPENAI_API_KEY</code> environment variable.
      </p>

      <div style={tabBarStyle}>
        <button
          style={tabButtonStyle(tab === "providers")}
          onClick={() => setTab("providers")}
        >
          Providers
        </button>
        <button
          style={tabButtonStyle(tab === "models")}
          onClick={() => setTab("models")}
        >
          Registered Models
        </button>
      </div>

      {tab === "providers" && <ProvidersTab />}
      {tab === "models" && <ModelsTab />}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Providers tab
// ---------------------------------------------------------------------------

const ProvidersTab: React.FC = () => {
  const { data, loading, error, refetch } =
    useQuery<LLMProvidersResult>(GET_LLM_PROVIDERS);
  const [updateSecrets] = useMutation(UPDATE_LLM_PROVIDER_SECRETS);
  const [deleteSecrets] = useMutation(DELETE_LLM_PROVIDER_SECRETS);

  if (loading) return <div>Loading providers…</div>;
  if (error) return <div>Failed to load providers: {error.message}</div>;
  if (!data) return null;

  return (
    <div>
      {data.llmProviders.map((p) => (
        <ProviderCard
          key={p.classPath}
          provider={p}
          onSave={async (secrets, providerSettings) => {
            const res = await updateSecrets({
              variables: {
                providerClassPath: p.classPath,
                secrets,
                providerSettings,
                merge: true,
              },
            });
            const ok = res.data?.updateLlmProviderSecrets?.ok;
            const message = res.data?.updateLlmProviderSecrets?.message;
            if (ok) {
              toast.success(message || "Saved");
              await refetch();
            } else {
              toast.error(message || "Failed to save");
            }
          }}
          onClear={async () => {
            if (!window.confirm(`Clear all secrets for ${p.title || p.name}?`))
              return;
            const res = await deleteSecrets({
              variables: { providerClassPath: p.classPath },
            });
            const ok = res.data?.deleteLlmProviderSecrets?.ok;
            const message = res.data?.deleteLlmProviderSecrets?.message;
            if (ok) {
              toast.success(message || "Cleared");
              await refetch();
            } else {
              toast.error(message || "Failed to clear");
            }
          }}
        />
      ))}
    </div>
  );
};

interface ProviderCardProps {
  provider: LLMProvider;
  onSave: (
    secrets: Record<string, string>,
    providerSettings: Record<string, string>,
  ) => Promise<void>;
  onClear: () => Promise<void>;
}

const ProviderCard: React.FC<ProviderCardProps> = ({
  provider,
  onSave,
  onClear,
}) => {
  // Initial values: pre-fill non-secret current values; secret slots
  // start empty (we never receive the actual value).
  const initial = useMemo(() => {
    const secrets: Record<string, string> = {};
    const settings: Record<string, string> = {};
    for (const s of provider.settingsSchema || []) {
      if (s.settingType === "secret") {
        secrets[s.name] = "";
      } else if (typeof s.currentValue === "string") {
        settings[s.name] = s.currentValue;
      } else {
        settings[s.name] = "";
      }
    }
    return { secrets, settings };
  }, [provider]);

  const [secrets, setSecrets] = useState(initial.secrets);
  const [settings, setSettings] = useState(initial.settings);
  const [saving, setSaving] = useState(false);

  return (
    <div style={cardStyle}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>{provider.title || provider.name}</h3>
          <div style={{ fontSize: 12, color: "#475569" }}>
            <code>{provider.classPath}</code> · prefix:{" "}
            <code>{provider.pydanticAiPrefix}</code>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {provider.hasValidSecrets ? (
            <span style={pillStyle("#16a34a")}>Configured</span>
          ) : provider.hasSecrets ? (
            <span style={pillStyle("#f59e0b")}>Has secret · invalid</span>
          ) : (
            <span style={pillStyle("#6b7280")}>Not configured</span>
          )}
        </div>
      </div>
      {provider.description && (
        <p style={{ color: "#475569", marginTop: 8 }}>{provider.description}</p>
      )}

      <hr
        style={{ border: 0, borderTop: "1px solid #e5e7eb", margin: "12px 0" }}
      />

      {(provider.settingsSchema || []).map((field) => (
        <div key={field.name}>
          <label
            style={labelStyle}
            htmlFor={`${provider.classPath}-${field.name}`}
          >
            {field.name}
            {field.required ? " *" : ""}
            {field.settingType === "secret" ? " (secret)" : ""}
            {field.envVar ? ` · env: ${field.envVar}` : ""}
          </label>
          {field.description && (
            <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>
              {field.description}
            </div>
          )}
          {field.settingType === "secret" ? (
            <input
              id={`${provider.classPath}-${field.name}`}
              type="password"
              autoComplete="off"
              placeholder={
                field.hasValue ? "•••••• (set; type to replace)" : ""
              }
              style={inputStyle}
              value={secrets[field.name] ?? ""}
              onChange={(e) =>
                setSecrets({ ...secrets, [field.name]: e.target.value })
              }
            />
          ) : (
            <input
              id={`${provider.classPath}-${field.name}`}
              type="text"
              style={inputStyle}
              value={settings[field.name] ?? ""}
              onChange={(e) =>
                setSettings({ ...settings, [field.name]: e.target.value })
              }
            />
          )}
        </div>
      ))}

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Button
          disabled={saving}
          onClick={async () => {
            setSaving(true);
            try {
              // Drop empty secret slots so we don't blank out an existing
              // value when the user only edited non-secret fields.
              const nonEmptySecrets = Object.fromEntries(
                Object.entries(secrets).filter(([, v]) => v !== ""),
              );
              const nonEmptySettings = Object.fromEntries(
                Object.entries(settings).filter(([, v]) => v !== ""),
              );
              await onSave(nonEmptySecrets, nonEmptySettings);
              setSecrets(initial.secrets); // clear the secret inputs after save
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
        {provider.hasSecrets && (
          <Button onClick={onClear} style={{ background: "#dc2626" }}>
            Clear
          </Button>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Models tab
// ---------------------------------------------------------------------------

const ModelsTab: React.FC = () => {
  const { data, loading, error, refetch } = useQuery<RegisteredLLMsResult>(
    GET_REGISTERED_LLMS,
    { variables: { onlySelectable: false } },
  );
  const settingsResult = useQuery<LLMSettingsResult>(GET_LLM_SETTINGS);
  const providersResult = useQuery<LLMProvidersResult>(GET_LLM_PROVIDERS);

  const [register] = useMutation(REGISTER_LLM);
  const [updateRl] = useMutation(UPDATE_REGISTERED_LLM);
  const [archive] = useMutation(ARCHIVE_REGISTERED_LLM);
  const [setDefault] = useMutation(SET_DEFAULT_EXTRACT_LLM);

  const [showCreate, setShowCreate] = useState(false);

  if (loading) return <div>Loading models…</div>;
  if (error) return <div>Failed to load: {error.message}</div>;
  if (!data) return null;

  const refetchAll = async () => {
    await refetch();
    await settingsResult.refetch();
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div>
          <strong>Default extract LLM:</strong>{" "}
          {settingsResult.data?.llmSettings?.defaultExtractLlm ? (
            <code>
              {settingsResult.data.llmSettings.defaultExtractLlm.displayName}
            </code>
          ) : (
            <em>none — using legacy DEFAULT_EXTRACT_MODEL fallback</em>
          )}
        </div>
        <Button onClick={() => setShowCreate(true)}>+ Register LLM</Button>
      </div>

      {showCreate && providersResult.data && (
        <RegisterLLMForm
          providers={providersResult.data.llmProviders}
          onSubmit={async (vars) => {
            const res = await register({ variables: vars });
            if (res.data?.registerLlm?.ok) {
              toast.success(res.data.registerLlm.message || "Registered");
              setShowCreate(false);
              await refetchAll();
            } else {
              toast.error(res.data?.registerLlm?.message || "Failed");
            }
          }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      {data.registeredLlms.map((rl) => (
        <ModelRow
          key={rl.id}
          row={rl}
          onArchive={async () => {
            if (!window.confirm(`Archive ${rl.displayName}?`)) return;
            const res = await archive({ variables: { id: rl.id } });
            if (res.data?.archiveRegisteredLlm?.ok) {
              toast.success(
                res.data.archiveRegisteredLlm.message || "Archived",
              );
              await refetchAll();
            } else {
              toast.error(
                res.data?.archiveRegisteredLlm?.message || "Failed to archive",
              );
            }
          }}
          onSetDefault={async () => {
            const res = await setDefault({ variables: { id: rl.id } });
            if (res.data?.setDefaultExtractLlm?.ok) {
              toast.success(res.data.setDefaultExtractLlm.message || "Set");
              await refetchAll();
            } else {
              toast.error(
                res.data?.setDefaultExtractLlm?.message ||
                  "Failed to set default",
              );
            }
          }}
          onUpdate={async (changes) => {
            const res = await updateRl({
              variables: { id: rl.id, ...changes },
            });
            if (res.data?.updateRegisteredLlm?.ok) {
              toast.success(res.data.updateRegisteredLlm.message || "Updated");
              await refetchAll();
            } else {
              toast.error(
                res.data?.updateRegisteredLlm?.message || "Failed to update",
              );
            }
          }}
        />
      ))}
    </div>
  );
};

interface ModelRowProps {
  row: RegisteredLLM;
  onArchive: () => Promise<void>;
  onSetDefault: () => Promise<void>;
  onUpdate: (changes: Partial<RegisteredLLM>) => Promise<void>;
}

const ModelRow: React.FC<ModelRowProps> = ({
  row,
  onArchive,
  onSetDefault,
  onUpdate,
}) => {
  return (
    <div
      style={{
        ...cardStyle,
        opacity: row.isArchived || !row.isHead ? 0.6 : 1,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div>
          <h3 style={{ margin: 0 }}>{row.displayName}</h3>
          <div style={{ fontSize: 12, color: "#475569" }}>
            <code>{row.pydanticAiModelString || row.modelId}</code>
            {row.provider?.title ? ` · ${row.provider.title}` : ""}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {row.isDefaultForExtracts && (
            <span style={pillStyle("#2563eb")}>Default</span>
          )}
          {row.isArchived && <span style={pillStyle("#6b7280")}>Archived</span>}
          {!row.isHead && <span style={pillStyle("#6b7280")}>Superseded</span>}
          {!row.isEnabled && <span style={pillStyle("#f59e0b")}>Disabled</span>}
          {row.isResolvable ? (
            <span style={pillStyle("#16a34a")}>Resolvable</span>
          ) : (
            <span
              style={pillStyle("#dc2626")}
              title={row.unavailableReason || ""}
            >
              Unavailable
            </span>
          )}
        </div>
      </div>
      {!row.isResolvable && row.unavailableReason && (
        <div style={{ color: "#dc2626", fontSize: 12, marginTop: 8 }}>
          {row.unavailableReason}
        </div>
      )}
      {row.isHead && !row.isArchived && (
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          {!row.isDefaultForExtracts && row.isResolvable && (
            <Button onClick={onSetDefault}>Set as default extract LLM</Button>
          )}
          <Button onClick={() => onUpdate({ isEnabled: !row.isEnabled })}>
            {row.isEnabled ? "Disable" : "Enable"}
          </Button>
          {!row.isDefaultForExtracts && (
            <Button onClick={onArchive} style={{ background: "#dc2626" }}>
              Archive
            </Button>
          )}
        </div>
      )}
    </div>
  );
};

interface RegisterLLMFormProps {
  providers: LLMProvider[];
  onSubmit: (vars: {
    providerClassPath: string;
    modelId: string;
    displayName: string;
  }) => Promise<void>;
  onCancel: () => void;
}

const RegisterLLMForm: React.FC<RegisterLLMFormProps> = ({
  providers,
  onSubmit,
  onCancel,
}) => {
  const [providerClassPath, setProviderClassPath] = useState(
    providers[0]?.classPath || "",
  );
  const [modelId, setModelId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const selected = providers.find((p) => p.classPath === providerClassPath);

  return (
    <div style={cardStyle}>
      <h3 style={{ marginTop: 0 }}>Register a new LLM</h3>
      <div style={rowStyle}>
        <div>
          <label style={labelStyle}>Provider</label>
          <select
            style={inputStyle}
            value={providerClassPath}
            onChange={(e) => setProviderClassPath(e.target.value)}
          >
            {providers.map((p) => (
              <option key={p.classPath} value={p.classPath}>
                {p.title || p.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Model ID</label>
          <input
            style={inputStyle}
            placeholder={selected?.defaultModels?.[0] || "gpt-4o-mini"}
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            list={`models-${providerClassPath}`}
          />
          <datalist id={`models-${providerClassPath}`}>
            {(selected?.defaultModels || []).map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </div>
      </div>
      <label style={labelStyle}>Display name</label>
      <input
        style={inputStyle}
        placeholder="e.g. GPT-4o mini (Prod)"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <Button
          disabled={
            !providerClassPath || !modelId.trim() || !displayName.trim()
          }
          onClick={() => onSubmit({ providerClassPath, modelId, displayName })}
        >
          Register
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
};
