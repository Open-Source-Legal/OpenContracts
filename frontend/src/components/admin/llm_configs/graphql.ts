import { gql } from "@apollo/client";

// ---------------------------------------------------------------------------
// Type stubs (kept local — adding to graphql-api.ts is a follow-up cleanup).
// ---------------------------------------------------------------------------

export interface LLMSettingSchemaEntry {
  name: string;
  settingType: "required" | "optional" | "secret" | string;
  pythonType?: string | null;
  required: boolean;
  description?: string | null;
  default?: unknown;
  envVar?: string | null;
  hasValue?: boolean | null;
  currentValue?: unknown;
}

export interface LLMProvider {
  name: string;
  classPath: string;
  title?: string | null;
  description?: string | null;
  pydanticAiPrefix: string;
  defaultModels?: string[] | null;
  supportsStructuredOutput: boolean;
  supportsTools: boolean;
  hasSecrets: boolean;
  hasValidSecrets: boolean;
  settingsSchema?: LLMSettingSchemaEntry[] | null;
}

export interface RegisteredLLM {
  id: string;
  providerClassPath: string;
  modelId: string;
  displayName: string;
  pydanticAiModelString?: string | null;
  isEnabled: boolean;
  isArchived: boolean;
  isHead: boolean;
  isResolvable: boolean;
  unavailableReason?: string | null;
  isDefaultForExtracts: boolean;
  contextWindow?: number | null;
  supportsStructuredOutput: boolean;
  supportsTools: boolean;
  notes?: string | null;
  previousVersionId?: string | null;
  provider?: Pick<LLMProvider, "title" | "pydanticAiPrefix"> | null;
}

export interface LLMSettings {
  providerSettings?: Record<string, Record<string, unknown>> | null;
  providersWithSecrets: string[];
  defaultExtractLlm?: RegisteredLLM | null;
  modified?: string | null;
  modifiedBy?: { id: string; username: string } | null;
}

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export const GET_LLM_PROVIDERS = gql`
  query GetLLMProviders {
    llmProviders {
      name
      classPath
      title
      description
      pydanticAiPrefix
      defaultModels
      supportsStructuredOutput
      supportsTools
      hasSecrets
      hasValidSecrets
      settingsSchema {
        name
        settingType
        pythonType
        required
        description
        default
        envVar
        hasValue
        currentValue
      }
    }
  }
`;

export const GET_REGISTERED_LLMS = gql`
  query GetRegisteredLLMs($onlySelectable: Boolean) {
    registeredLlms(onlySelectable: $onlySelectable) {
      id
      providerClassPath
      modelId
      displayName
      pydanticAiModelString
      isEnabled
      isArchived
      isHead
      isResolvable
      unavailableReason
      isDefaultForExtracts
      contextWindow
      supportsStructuredOutput
      supportsTools
      notes
      previousVersionId
      provider {
        title
        pydanticAiPrefix
      }
    }
  }
`;

export const GET_LLM_SETTINGS = gql`
  query GetLLMSettings {
    llmSettings {
      providerSettings
      providersWithSecrets
      modified
      modifiedBy {
        id
        username
      }
      defaultExtractLlm {
        id
        modelId
        displayName
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export const REGISTER_LLM = gql`
  mutation RegisterLLM(
    $providerClassPath: String!
    $modelId: String!
    $displayName: String!
    $isEnabled: Boolean
    $contextWindow: Int
    $supportsStructuredOutput: Boolean
    $supportsTools: Boolean
    $notes: String
  ) {
    registerLlm(
      providerClassPath: $providerClassPath
      modelId: $modelId
      displayName: $displayName
      isEnabled: $isEnabled
      contextWindow: $contextWindow
      supportsStructuredOutput: $supportsStructuredOutput
      supportsTools: $supportsTools
      notes: $notes
    ) {
      ok
      message
      registeredLlm {
        id
        displayName
        isResolvable
      }
    }
  }
`;

export const UPDATE_REGISTERED_LLM = gql`
  mutation UpdateRegisteredLLM(
    $id: ID!
    $displayName: String
    $isEnabled: Boolean
    $contextWindow: Int
    $supportsStructuredOutput: Boolean
    $supportsTools: Boolean
    $notes: String
  ) {
    updateRegisteredLlm(
      id: $id
      displayName: $displayName
      isEnabled: $isEnabled
      contextWindow: $contextWindow
      supportsStructuredOutput: $supportsStructuredOutput
      supportsTools: $supportsTools
      notes: $notes
    ) {
      ok
      message
      registeredLlm {
        id
        displayName
        isHead
      }
    }
  }
`;

export const ARCHIVE_REGISTERED_LLM = gql`
  mutation ArchiveRegisteredLLM($id: ID!) {
    archiveRegisteredLlm(id: $id) {
      ok
      message
      registeredLlm {
        id
        isArchived
        isHead
      }
    }
  }
`;

export const UPDATE_LLM_PROVIDER_SECRETS = gql`
  mutation UpdateLLMProviderSecrets(
    $providerClassPath: String!
    $secrets: GenericScalar!
    $providerSettings: GenericScalar
    $merge: Boolean
  ) {
    updateLlmProviderSecrets(
      providerClassPath: $providerClassPath
      secrets: $secrets
      providerSettings: $providerSettings
      merge: $merge
    ) {
      ok
      message
      llmSettings {
        providersWithSecrets
        providerSettings
      }
    }
  }
`;

export const DELETE_LLM_PROVIDER_SECRETS = gql`
  mutation DeleteLLMProviderSecrets($providerClassPath: String!) {
    deleteLlmProviderSecrets(providerClassPath: $providerClassPath) {
      ok
      message
      llmSettings {
        providersWithSecrets
      }
    }
  }
`;

export const SET_DEFAULT_EXTRACT_LLM = gql`
  mutation SetDefaultExtractLLM($id: ID) {
    setDefaultExtractLlm(id: $id) {
      ok
      message
      llmSettings {
        defaultExtractLlm {
          id
          modelId
          displayName
        }
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Result envelopes
// ---------------------------------------------------------------------------

export interface LLMProvidersResult {
  llmProviders: LLMProvider[];
}
export interface RegisteredLLMsResult {
  registeredLlms: RegisteredLLM[];
}
export interface LLMSettingsResult {
  llmSettings: LLMSettings | null;
}
