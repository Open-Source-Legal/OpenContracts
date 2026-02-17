// Playwright Component Test for Admin Components (Settings Panel, Agent Management)
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { gql } from "@apollo/client";
import {
  GlobalSettingsPanelWrapper,
  GlobalAgentManagementWrapper,
  CorpusAgentManagementWrapper,
  SystemSettingsWrapper,
} from "./AdminComponentsTestWrapper";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

// GraphQL queries/mutations used by GlobalAgentManagement
const GET_GLOBAL_AGENTS = gql`
  query GetGlobalAgents {
    agentConfigurations(scope: "GLOBAL") {
      edges {
        node {
          id
          name
          slug
          description
          systemInstructions
          availableTools
          permissionRequiredTools
          badgeConfig
          avatarUrl
          scope
          isActive
          isPublic
          creator {
            id
            username
          }
          created
          modified
        }
      }
    }
  }
`;

const GET_CORPUS_AGENTS = gql`
  query GetCorpusAgents($corpusId: String!) {
    agentConfigurations(corpusId: $corpusId) {
      edges {
        node {
          id
          name
          slug
          description
          systemInstructions
          availableTools
          permissionRequiredTools
          badgeConfig
          avatarUrl
          scope
          isActive
          isPublic
          creator {
            id
            username
          }
          created
          modified
        }
      }
    }
  }
`;

// Mock data
const mockGlobalAgent = {
  id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZTox",
  name: "Research Assistant",
  slug: "research-assistant",
  description: "AI assistant for research and document analysis",
  systemInstructions: "You are a helpful research assistant...",
  availableTools: ["similarity_search", "load_document_text"],
  permissionRequiredTools: [],
  badgeConfig: { icon: "robot", color: "#6366f1", label: "AI" },
  avatarUrl: null,
  scope: "GLOBAL",
  isActive: true,
  isPublic: true,
  creator: { id: "VXNlclR5cGU6MQ==", username: "admin" },
  created: "2024-01-15T10:30:00Z",
  modified: "2024-01-15T10:30:00Z",
};

const mockCorpusAgent = {
  id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZToy",
  name: "Legal Analyst",
  slug: "legal-analyst",
  description: "AI assistant specialized for legal document review",
  systemInstructions: "You are a legal analyst...",
  availableTools: ["similarity_search", "search_exact_text"],
  permissionRequiredTools: ["create_annotation"],
  badgeConfig: { icon: "gavel", color: "#8b5cf6", label: "Legal" },
  avatarUrl: null,
  scope: "CORPUS",
  isActive: true,
  isPublic: false,
  creator: { id: "VXNlclR5cGU6MQ==", username: "admin" },
  created: "2024-01-15T10:30:00Z",
  modified: "2024-01-15T10:30:00Z",
};

test.describe("GlobalSettingsPanel Component", () => {
  test("should render the settings panel with all settings cards", async ({
    mount,
    page,
  }) => {
    const component = await mount(<GlobalSettingsPanelWrapper />);

    // Check page title
    await expect(page.locator("text=Admin Settings")).toBeVisible();

    // Check all settings cards are present
    await expect(page.locator("text=Badge Management")).toBeVisible();
    await expect(page.locator("text=Global Agents")).toBeVisible();
    await expect(page.locator("text=System Settings")).toBeVisible();
    await expect(page.locator("text=User Management")).toBeVisible();

    await component.unmount();
  });

  test("should show Coming Soon badge for unavailable features", async ({
    mount,
    page,
  }) => {
    const component = await mount(<GlobalSettingsPanelWrapper />);

    // Coming Soon badge should be visible (only User Management has it)
    const comingSoonBadges = page.locator("text=Coming Soon");
    await expect(comingSoonBadges).toHaveCount(1);

    await component.unmount();
  });

  test("should display descriptions for each settings card", async ({
    mount,
    page,
  }) => {
    const component = await mount(<GlobalSettingsPanelWrapper />);

    // Check descriptions are present
    await expect(
      page.locator("text=Create and manage badges that can be awarded")
    ).toBeVisible();
    await expect(
      page.locator("text=Configure global AI agents available")
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("GlobalAgentManagement Component", () => {
  test("should display list of global agents", async ({ mount, page }) => {
    const getGlobalAgentsMock = {
      request: {
        query: GET_GLOBAL_AGENTS,
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [{ node: mockGlobalAgent }],
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[getGlobalAgentsMock]} />
    );

    // Wait for agents to load
    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    // Check slug is displayed
    await expect(page.locator("text=research-assistant")).toBeVisible();

    // Check status badge
    await expect(page.locator("text=Active")).toBeVisible();

    await component.unmount();
  });

  test("should show empty state when no agents exist", async ({
    mount,
    page,
  }) => {
    const emptyAgentsMock = {
      request: {
        query: GET_GLOBAL_AGENTS,
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[emptyAgentsMock]} />
    );

    // Check for empty state message
    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.locator("text=Create your first global agent")
    ).toBeVisible();

    await component.unmount();
  });

  test("should open create agent modal", async ({ mount, page }) => {
    const emptyAgentsMock = {
      request: {
        query: GET_GLOBAL_AGENTS,
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[emptyAgentsMock]} />
    );

    // Wait for content to load
    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });

    // Click create agent button
    await page.locator('button:has-text("Create Agent")').first().click();

    // Modal should open
    await expect(page.locator("text=Create Global Agent")).toBeVisible();

    // Form fields should be present
    await expect(page.locator("label:has-text('Name')")).toBeVisible();
    await expect(page.locator("label:has-text('Description')")).toBeVisible();
    await expect(
      page.locator("label:has-text('System Instructions')")
    ).toBeVisible();

    await docScreenshot(page, "admin--agent-config--create-modal");
    await releaseScreenshot(page, "v3.0.0.b3", "agent-config");

    await component.unmount();
  });

  test("should display tools as badges", async ({ mount, page }) => {
    const getGlobalAgentsMock = {
      request: {
        query: GET_GLOBAL_AGENTS,
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [{ node: mockGlobalAgent }],
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[getGlobalAgentsMock]} />
    );

    // Wait for agents to load
    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    // Tools should be displayed as badges
    await expect(page.locator("text=similarity_search")).toBeVisible();
    await expect(page.locator("text=load_document_text")).toBeVisible();

    await component.unmount();
  });

  test("should have edit and delete buttons", async ({ mount, page }) => {
    const getGlobalAgentsMock = {
      request: {
        query: GET_GLOBAL_AGENTS,
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [{ node: mockGlobalAgent }],
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[getGlobalAgentsMock]} />
    );

    // Wait for agents to load
    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    // Edit and delete buttons should be present
    await expect(page.locator("button i.edit.icon")).toBeVisible();
    await expect(page.locator("button i.trash.icon")).toBeVisible();

    await component.unmount();
  });
});

test.describe("CorpusAgentManagement Component", () => {
  test("should display list of corpus agents", async ({ mount, page }) => {
    const getCorpusAgentsMock = {
      request: {
        query: GET_CORPUS_AGENTS,
        variables: { corpusId: "Q29ycHVzVHlwZTox" },
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [{ node: mockCorpusAgent }],
          },
        },
      },
    };

    const component = await mount(
      <CorpusAgentManagementWrapper
        corpusId="Q29ycHVzVHlwZTox"
        canUpdate={true}
        mocks={[getCorpusAgentsMock]}
      />
    );

    // Wait for agents to load
    await expect(page.locator("text=Legal Analyst")).toBeVisible({
      timeout: 5000,
    });

    // Check slug is displayed
    await expect(page.locator("text=legal-analyst")).toBeVisible();

    await component.unmount();
  });

  test("should show empty state when no corpus agents exist", async ({
    mount,
    page,
  }) => {
    const emptyAgentsMock = {
      request: {
        query: GET_CORPUS_AGENTS,
        variables: { corpusId: "Q29ycHVzVHlwZTox" },
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <CorpusAgentManagementWrapper
        corpusId="Q29ycHVzVHlwZTox"
        canUpdate={true}
        mocks={[emptyAgentsMock]}
      />
    );

    // Check for empty state
    await expect(page.locator("text=No Agent Configurations")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.locator("text=Create an agent configuration to enable AI-powered")
    ).toBeVisible();

    await component.unmount();
  });

  test("should show permission message when canUpdate is false", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementWrapper
        corpusId="Q29ycHVzVHlwZTox"
        canUpdate={false}
        mocks={[]}
      />
    );

    // Should show permission denied message
    await expect(
      page.locator(
        "text=You do not have permission to manage agents for this corpus"
      )
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("should open create modal with corpus-specific title", async ({
    mount,
    page,
  }) => {
    const emptyAgentsMock = {
      request: {
        query: GET_CORPUS_AGENTS,
        variables: { corpusId: "Q29ycHVzVHlwZTox" },
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <CorpusAgentManagementWrapper
        corpusId="Q29ycHVzVHlwZTox"
        canUpdate={true}
        mocks={[emptyAgentsMock]}
      />
    );

    // Wait for content to load
    await expect(page.locator("text=No Agent Configurations")).toBeVisible({
      timeout: 5000,
    });

    // Click create agent button
    await page.locator('button:has-text("Create Agent")').first().click();

    // Modal should open with corpus-specific title
    await expect(
      page
        .locator(".header")
        .getByText("Create Agent Configuration", { exact: true })
    ).toBeVisible();

    await component.unmount();
  });

  test("should display helper text", async ({ mount, page }) => {
    const emptyAgentsMock = {
      request: {
        query: GET_CORPUS_AGENTS,
        variables: { corpusId: "Q29ycHVzVHlwZTox" },
      },
      result: {
        data: {
          agentConfigurations: {
            edges: [],
          },
        },
      },
    };

    const component = await mount(
      <CorpusAgentManagementWrapper
        corpusId="Q29ycHVzVHlwZTox"
        canUpdate={true}
        mocks={[emptyAgentsMock]}
      />
    );

    // Check helper text is displayed
    await expect(
      page.locator("text=Create agent configurations for this corpus")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

// GraphQL queries for SystemSettings
const GET_PIPELINE_SETTINGS = gql`
  query GetPipelineSettings {
    pipelineSettings {
      preferredParsers
      preferredEmbedders
      preferredThumbnailers
      parserKwargs
      componentSettings
      defaultEmbedder
      componentsWithSecrets
      modified
      modifiedBy {
        id
        username
      }
    }
  }
`;

const GET_PIPELINE_COMPONENTS = gql`
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
      }
    }
  }
`;

// Mutations for SystemSettings
const UPDATE_PIPELINE_SETTINGS = gql`
  mutation UpdatePipelineSettings(
    $preferredParsers: GenericScalar
    $preferredEmbedders: GenericScalar
    $preferredThumbnailers: GenericScalar
    $parserKwargs: GenericScalar
    $componentSettings: GenericScalar
    $defaultEmbedder: String
  ) {
    updatePipelineSettings(
      preferredParsers: $preferredParsers
      preferredEmbedders: $preferredEmbedders
      preferredThumbnailers: $preferredThumbnailers
      parserKwargs: $parserKwargs
      componentSettings: $componentSettings
      defaultEmbedder: $defaultEmbedder
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
        modified
        modifiedBy {
          id
          username
        }
      }
    }
  }
`;

const RESET_PIPELINE_SETTINGS = gql`
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
        modified
        modifiedBy {
          id
          username
        }
      }
    }
  }
`;

const UPDATE_COMPONENT_SECRETS = gql`
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

const DELETE_COMPONENT_SECRETS = gql`
  mutation DeleteComponentSecrets($componentPath: String!) {
    deleteComponentSecrets(componentPath: $componentPath) {
      ok
      message
      componentsWithSecrets
    }
  }
`;

// Mock data for SystemSettings
const mockPipelineSettings = {
  preferredParsers: {
    "application/pdf":
      "opencontractserver.pipeline.parsers.docling.DoclingParser",
  },
  preferredEmbedders: {},
  preferredThumbnailers: {},
  parserKwargs: {},
  componentSettings: {},
  defaultEmbedder: null,
  componentsWithSecrets: [
    "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
  ],
  modified: "2024-01-15T10:30:00Z",
  modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
};

const mockPipelineComponents = {
  parsers: [
    {
      name: "docling",
      title: "Docling Parser",
      description: "ML-based document parser",
      className: "opencontractserver.pipeline.parsers.docling.DoclingParser",
      supportedFileTypes: ["application/pdf"],
      settingsSchema: [],
    },
    {
      name: "llamaparse",
      title: "LlamaParser",
      description: "LlamaIndex cloud-based parser",
      className: "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
      supportedFileTypes: ["application/pdf"],
      settingsSchema: [
        {
          name: "api_key",
          settingType: "secret",
          pythonType: "str",
          required: true,
          description: "LlamaCloud API Key",
          default: "",
          envVar: "LLAMA_CLOUD_API_KEY",
          hasValue: false,
          currentValue: null,
        },
      ],
    },
  ],
  embedders: [
    {
      name: "openai",
      title: "OpenAI Ada Embedder",
      description: "OpenAI text-embedding-ada-002",
      className: "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
      vectorSize: 1536,
      supportedFileTypes: null,
      settingsSchema: [
        {
          name: "api_key",
          settingType: "secret",
          pythonType: "str",
          required: true,
          description: "OpenAI API Key",
          default: "",
          envVar: "OPENAI_API_KEY",
          hasValue: false,
          currentValue: null,
        },
      ],
    },
  ],
  thumbnailers: [
    {
      name: "pdf",
      title: "PDF Thumbnailer",
      description: "Generate thumbnails for PDF documents",
      className: "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
      supportedFileTypes: ["application/pdf"],
      settingsSchema: [],
    },
  ],
};

const mockPipelineComponentsWithConfiguredSecrets = {
  ...mockPipelineComponents,
  embedders: mockPipelineComponents.embedders.map((embedder) => {
    if (
      embedder.className ===
      "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder"
    ) {
      return {
        ...embedder,
        settingsSchema: embedder.settingsSchema.map((entry) => ({
          ...entry,
          hasValue: true,
        })),
      };
    }
    return embedder;
  }),
};

test.describe("SystemSettings Component", () => {
  test("should display loading state initially", async ({ mount, page }) => {
    // Use a mock that delays response to see loading state
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
      delay: 1000,
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
      delay: 1000,
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Should show loading state
    await expect(
      page.locator("text=Loading pipeline settings...")
    ).toBeVisible();

    await component.unmount();
  });

  test("should display settings page with all sections", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check pipeline stages are present (new visual flow design)
    // Stage headers are h2 elements
    await expect(page.locator("h2", { hasText: "Parser" })).toBeVisible();
    await expect(page.locator("h2", { hasText: "Thumbnailer" })).toBeVisible();
    await expect(
      page.locator("h2", { hasText: "Embedder" }).first()
    ).toBeVisible();

    // Check bottom sections
    await expect(
      page.locator("h2", { hasText: "Default Embedder" })
    ).toBeVisible();

    await component.unmount();
  });

  test("should display superuser warning banner", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check warning banner
    await expect(page.locator("text=Superuser Only")).toBeVisible();

    await component.unmount();
  });

  test("should display configured parser mappings with component cards", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check MIME type selector buttons are displayed
    await expect(page.locator("button:has-text('PDF')").first()).toBeVisible();

    // Check component card is displayed with title (uses full title from mock data)
    await expect(page.locator("text=Docling Parser")).toBeVisible();

    await component.unmount();
  });

  test("should display components with secrets", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            preferredEmbedders: {
              "application/pdf":
                "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
            },
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: {
        data: {
          pipelineComponents: mockPipelineComponentsWithConfiguredSecrets,
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const advancedSettingsButton = page
      .locator("button:has-text('Advanced Settings')")
      .last();
    await advancedSettingsButton.click();

    await expect(page.locator("text=Secret Keys")).toBeVisible();
    await expect(
      page.locator("button:has-text('Update Secrets')")
    ).toBeVisible();
    await expect(page.locator("button:has-text('Delete All')")).toBeVisible();

    await component.unmount();
  });

  test("should display last modified info", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check last modified info
    await expect(page.locator("text=Last modified")).toBeVisible();
    await expect(page.locator("text=by admin")).toBeVisible();

    await component.unmount();
  });

  test("should toggle advanced settings when component is selected", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Advanced Settings toggle should be visible for selected component
    await expect(
      page.locator("button:has-text('Advanced Settings')").first()
    ).toBeVisible();

    // Click to expand
    await page.locator("button:has-text('Advanced Settings')").first().click();

    // Should show component path in expanded settings
    await expect(page.locator("text=Component Path")).toBeVisible();

    await component.unmount();
  });

  test("should open secrets modal", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            preferredParsers: {
              "application/pdf":
                "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
            },
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const advancedSettingsButton = page
      .locator("button:has-text('Advanced Settings')")
      .first();
    await advancedSettingsButton.click();

    // Click Configure Secrets button
    await page.locator('button:has-text("Configure Secrets")').click();

    // Modal should open
    await expect(
      page.locator(".oc-modal-header__title:has-text('Configure Secrets')")
    ).toBeVisible();

    // Security notice should be visible
    await expect(page.locator("text=Security Notice")).toBeVisible();

    await component.unmount();
  });

  test("should open delete secrets confirmation modal", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            preferredEmbedders: {
              "application/pdf":
                "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
            },
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: {
        data: {
          pipelineComponents: mockPipelineComponentsWithConfiguredSecrets,
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const advancedSettingsButton = page
      .locator("button:has-text('Advanced Settings')")
      .last();
    await advancedSettingsButton.click();

    // Click delete button on secrets section
    await page.locator('button:has-text("Delete All")').click();

    // Confirmation modal should open
    await expect(page.locator("text=Delete Component Secrets")).toBeVisible();
    await expect(
      page.locator("text=This action cannot be undone")
    ).toBeVisible();

    await component.unmount();
  });

  test("should open reset confirmation modal", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Click Reset to Defaults button
    await page.locator('button:has-text("Reset to Defaults")').click();

    // Confirmation modal should open
    await expect(
      page.locator(".oc-modal-header__title:has-text('Reset to Defaults')")
    ).toBeVisible();
    await expect(
      page.locator("text=This will reset all pipeline settings")
    ).toBeVisible();

    await component.unmount();
  });

  test("should display empty state for unconfigured secrets", async ({
    mount,
    page,
  }) => {
    const emptySettings = {
      ...mockPipelineSettings,
      preferredParsers: {
        "application/pdf":
          "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
      },
      preferredEmbedders: {},
      preferredThumbnailers: {},
      componentsWithSecrets: [],
    };

    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: emptySettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const advancedSettingsButton = page
      .locator("button:has-text('Advanced Settings')")
      .first();
    await advancedSettingsButton.click();

    // Secret keys should be present but unconfigured
    await expect(page.locator("text=Secret Keys")).toBeVisible();
    await expect(page.locator("text=Not set")).toBeVisible();

    // Using system default is shown when no default embedder configured
    await expect(page.locator("text=Using system default")).toBeVisible();

    await component.unmount();
  });

  test("should display error state on query failure", async ({
    mount,
    page,
  }) => {
    const errorMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      error: new Error("Permission denied"),
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[errorMock, componentsMock]} />
    );

    // Wait for error state
    await expect(page.locator("text=Error Loading Settings")).toBeVisible({
      timeout: 5000,
    });

    // Should show try again button
    await expect(page.locator('button:has-text("Try Again")')).toBeVisible();

    await component.unmount();
  });

  test("should have back navigation button", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check back button
    await expect(page.locator("text=Back to Admin Settings")).toBeVisible();

    await component.unmount();
  });

  test("should display visual pipeline flow stages", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check pipeline intake and output points
    await expect(page.locator("text=Document Upload")).toBeVisible();
    await expect(page.locator("text=Ready for Search")).toBeVisible();
    await expect(page.locator("text=Pipeline complete")).toBeVisible();

    await component.unmount();
  });

  test("should allow switching MIME types", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // MIME type buttons should be visible (PDF is selected by default)
    const pdfButton = page.locator("button:has-text('PDF')").first();
    await expect(pdfButton).toBeVisible();

    // TXT and DOCX buttons should also be visible
    await expect(page.locator("button:has-text('TXT')").first()).toBeVisible();
    await expect(page.locator("button:has-text('DOCX')").first()).toBeVisible();

    await component.unmount();
  });

  test("should filter components by MIME type - TXT and DOCX support", async ({
    mount,
    page,
  }) => {
    // Mock components with different MIME type support using short forms (PDF, TXT, DOCX)
    // This tests the fix for the MIME_TO_SHORT_LABEL mapping
    const multiMimeComponents = {
      parsers: [
        {
          name: "docling",
          title: "Docling Parser",
          description: "ML-based document parser (PDF only)",
          className:
            "opencontractserver.pipeline.parsers.docling.DoclingParser",
          supportedFileTypes: ["PDF"], // Only PDF
          settingsSchema: [],
        },
        {
          name: "text_parser",
          title: "Text Parser",
          description: "Plain text parser",
          className:
            "opencontractserver.pipeline.parsers.text_parser.TextParser",
          supportedFileTypes: ["TXT"], // Only TXT - tests "text/plain" → "TXT" mapping
          settingsSchema: [],
        },
        {
          name: "universal_parser",
          title: "Universal Parser",
          description: "Handles all document types",
          className:
            "opencontractserver.pipeline.parsers.universal.UniversalParser",
          supportedFileTypes: ["PDF", "TXT", "DOCX"], // All types
          settingsSchema: [],
        },
        {
          name: "docx_parser",
          title: "Word Document Parser",
          description: "Microsoft Word parser",
          className:
            "opencontractserver.pipeline.parsers.docx_parser.DocxParser",
          supportedFileTypes: ["DOCX"], // Only DOCX - tests long MIME → "DOCX" mapping
          settingsSchema: [],
        },
      ],
      embedders: [
        {
          name: "openai",
          title: "OpenAI Ada Embedder",
          description: "OpenAI text-embedding-ada-002",
          className:
            "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
          vectorSize: 1536,
          supportedFileTypes: null, // Supports all
          settingsSchema: [
            {
              name: "api_key",
              settingType: "secret",
              pythonType: "str",
              required: true,
              description: "OpenAI API Key",
              default: "",
              envVar: "OPENAI_API_KEY",
              hasValue: false,
              currentValue: null,
            },
          ],
        },
      ],
      thumbnailers: [
        {
          name: "pdf_thumb",
          title: "PDF Thumbnailer",
          description: "Generate thumbnails for PDF documents",
          className:
            "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
          supportedFileTypes: ["PDF"],
          settingsSchema: [],
        },
        {
          name: "text_thumb",
          title: "Text Thumbnailer",
          description: "Generate thumbnails for text documents",
          className:
            "opencontractserver.pipeline.thumbnailers.text.TextThumbnailer",
          supportedFileTypes: ["TXT"],
          settingsSchema: [],
        },
      ],
    };

    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            preferredParsers: {}, // No selections yet
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: multiMimeComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper mocks={[settingsMock, componentsMock]} />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // === Test PDF selection (default) ===
    // Should show Docling Parser and Universal Parser (both support PDF)
    await expect(page.locator("text=Docling Parser")).toBeVisible();
    await expect(page.locator("text=Universal Parser")).toBeVisible();
    // Should NOT show Text Parser or Word Document Parser (don't support PDF)
    await expect(page.locator("text=Text Parser")).not.toBeVisible();
    await expect(page.locator("text=Word Document Parser")).not.toBeVisible();

    // === Test TXT selection ===
    // Click TXT button in the Parser stage
    const txtButton = page.locator("button:has-text('TXT')").first();
    await txtButton.click();

    // Should show Text Parser and Universal Parser (both support TXT)
    await expect(page.locator("text=Text Parser")).toBeVisible();
    await expect(page.locator("text=Universal Parser")).toBeVisible();
    // Should NOT show Docling Parser or Word Document Parser
    await expect(page.locator("text=Docling Parser")).not.toBeVisible();
    await expect(page.locator("text=Word Document Parser")).not.toBeVisible();

    // === Test DOCX selection ===
    // Click DOCX button in the Parser stage
    const docxButton = page.locator("button:has-text('DOCX')").first();
    await docxButton.click();

    // Should show Word Document Parser and Universal Parser (both support DOCX)
    await expect(page.locator("text=Word Document Parser")).toBeVisible();
    await expect(page.locator("text=Universal Parser")).toBeVisible();
    // Should NOT show Docling Parser or Text Parser
    await expect(page.locator("text=Docling Parser")).not.toBeVisible();
    await expect(page.locator("text=Text Parser")).not.toBeVisible();

    await component.unmount();
  });

  test("should call UPDATE_PIPELINE_SETTINGS when selecting a component", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    // Mock the mutation response - match exact variables since variableMatcher seems unreliable
    const updateSettingsMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: {
          preferredParsers: {
            "application/pdf":
              "opencontractserver.pipeline.parsers.docling.DoclingParser",
          },
        },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Settings updated successfully",
            pipelineSettings: {
              ...mockPipelineSettings,
              preferredParsers: {
                "application/pdf":
                  "opencontractserver.pipeline.parsers.docling.DoclingParser",
              },
            },
          },
        },
      },
    };

    // Refetch mock after mutation
    const refetchMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, updateSettingsMock, refetchMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Click on the Docling Parser card to select it
    const doclingCard = page.locator("text=Docling Parser").first();
    await expect(doclingCard).toBeVisible();
    await doclingCard.click();

    // Should show success toast (the mutation mock returns ok: true)
    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("should call RESET_PIPELINE_SETTINGS when clicking reset button", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const resetMock = {
      request: { query: RESET_PIPELINE_SETTINGS },
      result: {
        data: {
          resetPipelineSettings: {
            ok: true,
            message: "Settings reset to defaults",
            pipelineSettings: {
              preferredParsers: {},
              preferredEmbedders: {},
              preferredThumbnailers: {},
              parserKwargs: {},
              componentSettings: {},
              defaultEmbedder: null,
              componentsWithSecrets: [],
              modified: "2024-01-15T11:00:00Z",
              modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
            },
          },
        },
      },
    };

    // Refetch mock after reset
    const refetchMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            preferredParsers: {},
            preferredEmbedders: {},
            preferredThumbnailers: {},
            parserKwargs: {},
            componentSettings: {},
            defaultEmbedder: null,
            componentsWithSecrets: [],
            modified: "2024-01-15T11:00:00Z",
            modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, resetMock, refetchMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Click reset button to open confirmation modal
    const resetButton = page.locator("button:has-text('Reset to Defaults')");
    await expect(resetButton).toBeVisible();
    await resetButton.click();

    // Confirmation modal should appear
    await expect(page.locator("text=Reset to Defaults").nth(1)).toBeVisible();
    await expect(
      page.locator("text=This will reset all pipeline settings")
    ).toBeVisible();

    // Click confirm reset button in modal
    const confirmButton = page.locator("button:has-text('Reset Settings')");
    await expect(confirmButton).toBeVisible();
    await confirmButton.click();

    // Should show success toast
    await expect(page.locator("text=Settings reset to defaults")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("should call UPDATE_COMPONENT_SECRETS when saving secrets", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            preferredParsers: {
              "application/pdf":
                "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
            },
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const updateSecretsMock = {
      request: {
        query: UPDATE_COMPONENT_SECRETS,
        variables: {
          componentPath:
            "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
          secrets: { api_key: "test-api-key" },
          merge: true,
        },
      },
      result: {
        data: {
          updateComponentSecrets: {
            ok: true,
            message: "Secrets saved successfully",
            componentsWithSecrets: [
              "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
              "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
            ],
          },
        },
      },
    };

    // Refetch mock after saving secrets
    const refetchMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            componentsWithSecrets: [
              "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
              "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
            ],
            preferredParsers: {
              "application/pdf":
                "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
            },
          },
        },
      },
    };

    const componentsRefetchMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: {
        data: {
          pipelineComponents: mockPipelineComponents,
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock,
          componentsMock,
          updateSecretsMock,
          refetchMock,
          componentsRefetchMock,
        ]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const advancedSettingsButton = page
      .locator("button:has-text('Advanced Settings')")
      .first();
    await advancedSettingsButton.click();

    // Click Configure Secrets button
    const configureSecretsButton = page.locator(
      "button:has-text('Configure Secrets')"
    );
    await expect(configureSecretsButton).toBeVisible();
    await configureSecretsButton.click();

    // Modal should appear
    await expect(
      page.locator(".oc-modal-header__title:has-text('Configure Secrets')")
    ).toBeVisible();

    // Fill in the form
    const apiKeyInput = page.locator("#secret-api_key");
    await apiKeyInput.fill("test-api-key");

    // Click save button
    const saveButton = page.locator("button:has-text('Save Secrets')");
    await expect(saveButton).toBeEnabled();
    await saveButton.click();

    // Should show success toast
    await expect(page.locator("text=Secrets updated successfully")).toBeVisible(
      {
        timeout: 5000,
      }
    );

    await component.unmount();
  });

  test("should call DELETE_COMPONENT_SECRETS when deleting secrets", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            preferredEmbedders: {
              "application/pdf":
                "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
            },
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: {
        data: {
          pipelineComponents: mockPipelineComponentsWithConfiguredSecrets,
        },
      },
    };

    const deleteSecretsMock = {
      request: {
        query: DELETE_COMPONENT_SECRETS,
        variables: {
          componentPath:
            "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
        },
      },
      result: {
        data: {
          deleteComponentSecrets: {
            ok: true,
            message: "Secrets deleted successfully",
            componentsWithSecrets: [],
          },
        },
      },
    };

    // Refetch mock after deleting secrets
    const refetchMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockPipelineSettings,
            componentsWithSecrets: [],
            preferredEmbedders: {
              "application/pdf":
                "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
            },
          },
        },
      },
    };

    const componentsRefetchMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: {
        data: { pipelineComponents: mockPipelineComponents },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock,
          componentsMock,
          deleteSecretsMock,
          refetchMock,
          componentsRefetchMock,
        ]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const advancedSettingsButton = page
      .locator("button:has-text('Advanced Settings')")
      .last();
    await advancedSettingsButton.click();

    // Click the delete button in the secrets section
    const deleteButton = page.locator('button:has-text("Delete All")');
    await expect(deleteButton).toBeVisible();
    await deleteButton.click();

    // Confirmation modal should appear
    await expect(page.locator("text=Delete Component Secrets")).toBeVisible();
    await expect(
      page.locator("text=Are you sure you want to delete secrets")
    ).toBeVisible();

    // Click confirm delete button
    const confirmButton = page.locator("button:has-text('Delete Secrets')");
    await expect(confirmButton).toBeVisible();
    await confirmButton.click();

    // Should show success toast
    await expect(page.locator("text=Secrets deleted successfully")).toBeVisible(
      {
        timeout: 5000,
      }
    );

    await component.unmount();
  });
});
