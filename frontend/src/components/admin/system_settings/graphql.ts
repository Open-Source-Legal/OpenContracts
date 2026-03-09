import { gql } from "@apollo/client";
import {
  PipelineSettingsType,
  PipelineComponentsType,
  SupportedFileTypeInfo,
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

export interface SupportedFileTypesQueryResult {
  supportedFileTypes: SupportedFileTypeInfo[];
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

export const GET_SUPPORTED_FILE_TYPES = gql`
  query GetSupportedFileTypes {
    supportedFileTypes {
      mimetype
      label
      shortLabel
      hasParser
      hasEmbedder
      hasThumbnailer
      fullCoverage
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
    $enabledComponents: [String]
  ) {
    updatePipelineSettings(
      preferredParsers: $preferredParsers
      preferredEmbedders: $preferredEmbedders
      preferredThumbnailers: $preferredThumbnailers
      parserKwargs: $parserKwargs
      componentSettings: $componentSettings
      defaultEmbedder: $defaultEmbedder
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
