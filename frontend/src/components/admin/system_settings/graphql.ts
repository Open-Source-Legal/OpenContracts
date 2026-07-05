import { gql } from "@apollo/client";
import {
  PipelineSettingsType,
  PipelineComponentsType,
  SupportedMimeTypeType,
} from "../../../types/graphql-api";

// ============================================================================
// GraphQL Query/Mutation Result Types
// ============================================================================

export interface PipelineSettingsQueryResult {
  pipelineSettings: PipelineSettingsType;
}

export interface PipelineComponentsQueryResult {
  pipelineComponents: PipelineComponentsType;
}

export interface SupportedMimeTypesQueryResult {
  supportedMimeTypes: SupportedMimeTypeType[];
}

// ============================================================================
// GraphQL Operations
// ============================================================================

export const GET_PIPELINE_SETTINGS = gql`
  query GetPipelineSettings {
    pipelineSettings {
      preferredParsers
      preferredEmbedders
      preferredThumbnailers
      parserKwargs
      componentSettings
      defaultEmbedder
      defaultFileConverter
      defaultLlm
      defaultReranker
      componentsWithSecrets
      enabledComponents
      modified
      modifiedBy {
        id
        username
      }
    }
  }
`;

export const GET_PIPELINE_COMPONENTS = gql`
  query GetPipelineComponents {
    pipelineComponents {
      parsers {
        name
        title
        description
        className
        supportedFileTypes
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
        enabled
      }
      embedders {
        name
        title
        description
        className
        vectorSize
        supportedFileTypes
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
        enabled
      }
      thumbnailers {
        name
        title
        description
        className
        supportedFileTypes
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
        enabled
      }
      llmProviders {
        name
        title
        description
        className
        providerKey
        supportedModels
        requiresApiKey
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
        enabled
      }
      fileConverters {
        name
        title
        description
        className
        supportedExtensions
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
        enabled
      }
      rerankers {
        name
        title
        description
        className
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
        enabled
      }
    }
  }
`;

export const UPDATE_PIPELINE_SETTINGS = gql`
  mutation UpdatePipelineSettings(
    $preferredParsers: GenericScalar
    $preferredEmbedders: GenericScalar
    $preferredThumbnailers: GenericScalar
    $parserKwargs: GenericScalar
    $componentSettings: GenericScalar
    $defaultEmbedder: String
    $defaultFileConverter: String
    $defaultLlm: String
    $defaultReranker: String
    $enabledComponents: [String]
  ) {
    updatePipelineSettings(
      preferredParsers: $preferredParsers
      preferredEmbedders: $preferredEmbedders
      preferredThumbnailers: $preferredThumbnailers
      parserKwargs: $parserKwargs
      componentSettings: $componentSettings
      defaultEmbedder: $defaultEmbedder
      defaultFileConverter: $defaultFileConverter
      defaultLlm: $defaultLlm
      defaultReranker: $defaultReranker
      enabledComponents: $enabledComponents
    ) {
      ok
      message
      pipelineSettings {
        preferredParsers
        preferredEmbedders
        preferredThumbnailers
        parserKwargs
        componentSettings
        defaultEmbedder
        defaultFileConverter
        defaultLlm
        defaultReranker
        componentsWithSecrets
        enabledComponents
        modified
        modifiedBy {
          id
          username
        }
      }
    }
  }
`;

export const RESET_PIPELINE_SETTINGS = gql`
  mutation ResetPipelineSettings {
    resetPipelineSettings {
      ok
      message
      pipelineSettings {
        preferredParsers
        preferredEmbedders
        preferredThumbnailers
        parserKwargs
        componentSettings
        defaultEmbedder
        defaultFileConverter
        defaultLlm
        defaultReranker
        componentsWithSecrets
        enabledComponents
        modified
        modifiedBy {
          id
          username
        }
      }
    }
  }
`;

export const UPDATE_COMPONENT_SECRETS = gql`
  mutation UpdateComponentSecrets(
    $componentPath: String!
    $secrets: GenericScalar!
    $merge: Boolean
  ) {
    updateComponentSecrets(
      componentPath: $componentPath
      secrets: $secrets
      merge: $merge
    ) {
      ok
      message
      componentsWithSecrets
    }
  }
`;

export const DELETE_COMPONENT_SECRETS = gql`
  mutation DeleteComponentSecrets($componentPath: String!) {
    deleteComponentSecrets(componentPath: $componentPath) {
      ok
      message
      componentsWithSecrets
    }
  }
`;

export const GET_SUPPORTED_MIME_TYPES = gql`
  query GetSupportedMimeTypes {
    supportedMimeTypes {
      mimetype
      fileType
      label
      fullySupported
      stageCoverage {
        parser
        embedder
        thumbnailer
      }
    }
  }
`;

export interface ConvertibleExtensionsQueryResult {
  convertibleExtensions: (string | null)[] | null;
}

/**
 * Extensions the configured pre-parse file converter turns into PDF.
 * Empty when no converter is configured. Upload UIs merge these into the
 * accepted-format set alongside supportedMimeTypes.
 */
export const GET_CONVERTIBLE_EXTENSIONS = gql`
  query GetConvertibleExtensions {
    convertibleExtensions
  }
`;
