import React, { useCallback, useState } from "react";
import { useMutation } from "@apollo/client";
import { Button, Input } from "@os-legal/ui";
import {
  Globe,
  Save,
  Trash2,
  CircleCheck,
  CircleAlert,
  AlertTriangle,
} from "lucide-react";
import { toast } from "react-toastify";
import {
  WEB_SEARCH_TOOL_KEY,
  WEB_SEARCH_PROVIDERS,
} from "../../../assets/configurations/constants";
import { UPDATE_TOOL_SECRETS, DELETE_TOOL_SECRETS } from "./graphql";
import {
  Section,
  SectionHeader,
  SectionTitle,
  FormField,
  FormLabel,
  FormHelperText,
  SecretStatusIndicator,
  WarningBanner,
  WarningText,
  ActionButtons,
  StyledSelect,
} from "./styles";

// ============================================================================
// Types
// ============================================================================

interface ToolSecretsPanelProps {
  /** Tool keys with encrypted secrets configured (e.g. "tool:web_search"). */
  toolsWithSecrets: string[];
  /** Currently-persisted non-secret settings for the web search tool
   * (`PipelineSettings.componentSettings["tool:web_search"]`, e.g.
   * `{ provider: "tavily" }`). Seeds the initial Provider selection so
   * reopening an already-configured tool doesn't silently reset its
   * provider to the hardcoded default on the next save. */
  currentSettings?: Record<string, unknown>;
  /** Invoked after a successful save/delete so the parent can refetch
   * GET_PIPELINE_SETTINGS and refresh the "Configured" indicator. */
  onSecretsChanged: () => void;
}

// ============================================================================
// Component
// ============================================================================

/**
 * Admin GUI for agent tool secrets (issue #2117). Today there is exactly one
 * such tool — the web search tool (`opencontractserver.llms.tools.web_search_tools.WebSearchTool`,
 * settings key `tool:web_search`) — so this is a standalone panel rather than
 * a generic multi-tool modal; a modal would be unnecessary complexity for a
 * single configurable tool.
 */
export const ToolSecretsPanel: React.FC<ToolSecretsPanelProps> = ({
  toolsWithSecrets,
  currentSettings,
  onSecretsChanged,
}) => {
  const isConfigured = toolsWithSecrets.includes(WEB_SEARCH_TOOL_KEY);

  const [provider, setProvider] = useState<string>(
    () =>
      (currentSettings?.provider as string | undefined) ||
      WEB_SEARCH_PROVIDERS[0].value
  );
  const [apiKey, setApiKey] = useState("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const [updateToolSecrets, { loading: saving }] = useMutation(
    UPDATE_TOOL_SECRETS,
    {
      onCompleted: (data) => {
        if (data.updateToolSecrets?.ok) {
          toast.success("Web search tool configured successfully");
          setApiKey("");
          onSecretsChanged();
        } else {
          toast.error(
            data.updateToolSecrets?.message || "Failed to update tool secrets"
          );
        }
      },
      onError: (err) => {
        toast.error(`Error updating tool secrets: ${err.message}`);
      },
    }
  );

  const [deleteToolSecrets, { loading: deleting }] = useMutation(
    DELETE_TOOL_SECRETS,
    {
      onCompleted: (data) => {
        if (data.deleteToolSecrets?.ok) {
          toast.success("Web search tool configuration removed");
          setShowDeleteConfirm(false);
          onSecretsChanged();
        } else {
          toast.error(
            data.deleteToolSecrets?.message || "Failed to delete tool secrets"
          );
        }
      },
      onError: (err) => {
        toast.error(`Error deleting tool secrets: ${err.message}`);
      },
    }
  );

  const handleSave = useCallback(() => {
    const trimmedKey = apiKey.trim();
    if (!isConfigured && !trimmedKey) {
      toast.error(
        "Please provide an API key to configure the web search tool."
      );
      return;
    }
    updateToolSecrets({
      variables: {
        toolKey: WEB_SEARCH_TOOL_KEY,
        secrets: trimmedKey ? { api_key: trimmedKey } : null,
        settings: { provider },
        merge: true,
      },
    });
  }, [apiKey, isConfigured, provider, updateToolSecrets]);

  const handleDeleteClick = useCallback(() => {
    setShowDeleteConfirm(true);
  }, []);

  const handleConfirmDelete = useCallback(() => {
    deleteToolSecrets({ variables: { toolKey: WEB_SEARCH_TOOL_KEY } });
  }, [deleteToolSecrets]);

  const handleCancelDelete = useCallback(() => {
    setShowDeleteConfirm(false);
  }, []);

  return (
    <Section data-testid="tool-secrets-panel">
      <SectionHeader>
        <SectionTitle>
          <Globe />
          Agent Tools
        </SectionTitle>
      </SectionHeader>

      <FormField>
        <FormLabel
          style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
        >
          Web Search Tool
          <SecretStatusIndicator $populated={isConfigured}>
            {isConfigured ? (
              <>
                <CircleCheck /> Configured
              </>
            ) : (
              <>
                <CircleAlert /> Not configured
              </>
            )}
          </SecretStatusIndicator>
        </FormLabel>
        <FormHelperText>
          Powers the agent's web search tool. Requires an API key from one of
          the supported providers below.
        </FormHelperText>
      </FormField>

      <FormField>
        <FormLabel htmlFor="tool-secrets-provider">Provider</FormLabel>
        {/* Hardcoded to the two providers OpenContracts currently supports
            server-side — there is no generic tool-settings-schema query
            today to derive this dynamically. Mirrors
            opencontractserver.constants.web_search.SUPPORTED_PROVIDERS;
            update WEB_SEARCH_PROVIDERS in constants.ts if that changes. */}
        <StyledSelect
          id="tool-secrets-provider"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          {WEB_SEARCH_PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </StyledSelect>
      </FormField>

      <FormField>
        <FormLabel htmlFor="tool-secrets-api-key">API Key</FormLabel>
        <Input
          id="tool-secrets-api-key"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={
            isConfigured
              ? "Leave blank to keep current value"
              : "Enter API key..."
          }
          fullWidth
        />
      </FormField>

      {showDeleteConfirm && (
        <WarningBanner>
          <AlertTriangle />
          <WarningText>
            Are you sure you want to remove the web search tool configuration?
            This action cannot be undone.
          </WarningText>
        </WarningBanner>
      )}

      <ActionButtons>
        <Button variant="primary" onClick={handleSave} loading={saving}>
          <Save style={{ width: 16, height: 16, marginRight: 8 }} />
          Save
        </Button>
        {isConfigured &&
          (showDeleteConfirm ? (
            <>
              <Button variant="secondary" onClick={handleCancelDelete}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirmDelete}
                loading={deleting}
              >
                <Trash2 style={{ width: 16, height: 16, marginRight: 8 }} />
                Confirm Delete
              </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={handleDeleteClick}>
              <Trash2 style={{ width: 16, height: 16, marginRight: 8 }} />
              Remove Configuration
            </Button>
          ))}
      </ActionButtons>
    </Section>
  );
};

export default ToolSecretsPanel;
