/**
 * GraphQL operations for the LLM Configuration admin panel.
 *
 * Mirrors the shape of `frontend/src/components/admin/system_settings/graphql.ts`.
 */
import { gql } from "@apollo/client";

// --------------------------------------------------------------------------- //
// Queries
// --------------------------------------------------------------------------- //

export const GET_LLM_PROVIDERS = gql`
  query GetLLMProviders {
    llmProviders {
      key
      title
      description
      pydanticAiPrefix
      defaultModels
      supportsStructuredOutput
      supportsTools
      isConfigured
      credentialSchema {
        name
        label
        description
        isSecret
        required
        default
      }
    }
  }
`;

export const GET_LLM_CONFIG_SETTINGS = gql`
  query GetLLMConfigSettings {
    llmConfigSettings {
      modified
      modifiedById
      defaultModel {
        id
        providerKey
        modelName
        displayName
        isAvailable
      }
      providerConfigs {
        providerKey
        isConfigured
        config
        secretFieldsSet
      }
    }
  }
`;

export const GET_LLM_MODELS = gql`
  query GetLLMModels($providerKey: String, $isEnabled: Boolean) {
    llmModels(providerKey: $providerKey, isEnabled: $isEnabled) {
      id
      providerKey
      modelName
      displayName
      description
      isEnabled
      supportsVision
      supportsTools
      supportsStructuredOutput
      maxContextTokens
      defaultTemperature
      extraSettings
      isAvailable
      pydanticAiString
      provider {
        key
        title
      }
    }
  }
`;

export const GET_AVAILABLE_LLM_MODELS = gql`
  query GetAvailableLLMModels {
    availableLlmModels {
      id
      providerKey
      modelName
      displayName
      description
      isEnabled
      isAvailable
      supportsVision
      supportsTools
      supportsStructuredOutput
      maxContextTokens
      defaultTemperature
      pydanticAiString
      provider {
        key
        title
      }
    }
  }
`;

// --------------------------------------------------------------------------- //
// Mutations
// --------------------------------------------------------------------------- //

export const UPDATE_LLM_PROVIDER_CREDENTIALS = gql`
  mutation UpdateLLMProviderCredentials(
    $providerKey: String!
    $credentials: GenericScalar!
  ) {
    updateLlmProviderCredentials(
      providerKey: $providerKey
      credentials: $credentials
    ) {
      ok
      message
    }
  }
`;

export const DELETE_LLM_PROVIDER_CREDENTIALS = gql`
  mutation DeleteLLMProviderCredentials($providerKey: String!) {
    deleteLlmProviderCredentials(providerKey: $providerKey) {
      ok
      message
    }
  }
`;

export const CREATE_LLM_MODEL = gql`
  mutation CreateLLMModel(
    $providerKey: String!
    $modelName: String!
    $displayName: String!
    $description: String
    $isEnabled: Boolean
    $supportsVision: Boolean
    $supportsTools: Boolean
    $supportsStructuredOutput: Boolean
    $maxContextTokens: Int
    $defaultTemperature: Float
    $extraSettings: GenericScalar
  ) {
    createLlmModel(
      providerKey: $providerKey
      modelName: $modelName
      displayName: $displayName
      description: $description
      isEnabled: $isEnabled
      supportsVision: $supportsVision
      supportsTools: $supportsTools
      supportsStructuredOutput: $supportsStructuredOutput
      maxContextTokens: $maxContextTokens
      defaultTemperature: $defaultTemperature
      extraSettings: $extraSettings
    ) {
      ok
      message
      llmModel {
        id
      }
    }
  }
`;

export const UPDATE_LLM_MODEL = gql`
  mutation UpdateLLMModel(
    $id: ID!
    $displayName: String
    $description: String
    $isEnabled: Boolean
    $supportsVision: Boolean
    $supportsTools: Boolean
    $supportsStructuredOutput: Boolean
    $maxContextTokens: Int
    $defaultTemperature: Float
    $extraSettings: GenericScalar
  ) {
    updateLlmModel(
      id: $id
      displayName: $displayName
      description: $description
      isEnabled: $isEnabled
      supportsVision: $supportsVision
      supportsTools: $supportsTools
      supportsStructuredOutput: $supportsStructuredOutput
      maxContextTokens: $maxContextTokens
      defaultTemperature: $defaultTemperature
      extraSettings: $extraSettings
    ) {
      ok
      message
    }
  }
`;

export const DELETE_LLM_MODEL = gql`
  mutation DeleteLLMModel($id: ID!) {
    deleteLlmModel(id: $id) {
      ok
      message
    }
  }
`;

export const SET_DEFAULT_LLM_MODEL = gql`
  mutation SetDefaultLLMModel($id: ID) {
    setDefaultLlmModel(id: $id) {
      ok
      message
    }
  }
`;

// --------------------------------------------------------------------------- //
// TypeScript shapes (kept local to this admin module — they are not part of
// the global graphql-api generated types yet).
// --------------------------------------------------------------------------- //

export interface LLMCredentialField {
  name: string;
  label: string;
  description: string;
  isSecret: boolean;
  required: boolean;
  default: string | null;
}

export interface LLMProvider {
  key: string;
  title: string;
  description: string;
  pydanticAiPrefix: string;
  defaultModels: string[];
  supportsStructuredOutput: boolean;
  supportsTools: boolean;
  isConfigured: boolean;
  credentialSchema: LLMCredentialField[];
}

export interface LLMModel {
  id: string;
  providerKey: string;
  modelName: string;
  displayName: string;
  description: string;
  isEnabled: boolean;
  isAvailable: boolean;
  supportsVision: boolean;
  supportsTools: boolean;
  supportsStructuredOutput: boolean;
  maxContextTokens: number | null;
  defaultTemperature: number;
  extraSettings?: Record<string, unknown> | null;
  pydanticAiString: string;
  provider?: { key: string; title: string } | null;
}

export interface LLMProviderConfigEntry {
  providerKey: string;
  isConfigured: boolean;
  config: Record<string, unknown> | null;
  secretFieldsSet: string[];
}

export interface LLMConfigSettings {
  modified: string;
  modifiedById: number | null;
  defaultModel: Pick<
    LLMModel,
    "id" | "providerKey" | "modelName" | "displayName" | "isAvailable"
  > | null;
  providerConfigs: LLMProviderConfigEntry[];
}
