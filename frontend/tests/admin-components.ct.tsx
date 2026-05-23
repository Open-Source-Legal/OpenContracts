// Playwright Component Test for Admin Components (Settings Panel, Agent Management)
import React from "react";
import { test, expect } from "./utils/coverage";
import { gql } from "@apollo/client";
import {
  GlobalSettingsPanelWrapper,
  GlobalAgentManagementWrapper,
  CorpusAgentManagementWrapper,
  SystemSettingsWrapper,
} from "./AdminComponentsTestWrapper";
import {
  GET_PIPELINE_SETTINGS,
  GET_PIPELINE_COMPONENTS,
  GET_SUPPORTED_MIME_TYPES,
  UPDATE_PIPELINE_SETTINGS,
  RESET_PIPELINE_SETTINGS,
  UPDATE_COMPONENT_SECRETS,
  DELETE_COMPONENT_SECRETS,
} from "../src/components/admin/system_settings/graphql";
import { docScreenshot, releaseScreenshot } from "./utils/docScreenshot";

// GraphQL queries/mutations used by GlobalAgentManagement
// Mirror of the production GET_GLOBAL_AGENTS in
// `src/components/admin/global_agent_management.graphql.ts`. Apollo's
// MockedProvider matches mocks by the `print()`ed query body, so any drift
// (extra/missing fields, different aliases) means the mock silently fails
// to match and the component never sees its data. Keep this in sync — and
// never speculatively widen the selection set "for safety".
const GET_GLOBAL_AGENTS = gql`
  query GetGlobalAgents {
    agentConfigurations(scope: GLOBAL) {
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
            slug
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
  creator: { id: "VXNlclR5cGU6MQ==", slug: "admin", username: "admin" },
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
  creator: { id: "VXNlclR5cGU6MQ==", slug: "admin", username: "admin" },
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

    await docScreenshot(page, "admin--settings-panel--desktop", {
      fullPage: true,
    });

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

  test("should render responsively at tablet width", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    const component = await mount(<GlobalSettingsPanelWrapper />);

    await expect(page.locator("text=Admin Settings")).toBeVisible();
    await expect(page.locator("text=Badge Management")).toBeVisible();

    await docScreenshot(page, "admin--settings-panel--tablet", {
      fullPage: true,
    });

    await component.unmount();
  });

  test("should render responsively at mobile width with single-column stacking", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    const component = await mount(<GlobalSettingsPanelWrapper />);

    await expect(page.locator("text=Admin Settings")).toBeVisible();
    await expect(page.locator("text=Badge Management")).toBeVisible();

    // Verify single-column layout: two adjacent cards should share the same
    // x position and the second should be below the first.
    const firstCard = page.locator('[data-testid="settings-card-badges"]');
    const secondCard = page.locator(
      '[data-testid="settings-card-global-agents"]'
    );
    await expect(firstCard).toBeVisible();
    await expect(secondCard).toBeVisible();

    const firstBox = await firstCard.boundingBox();
    const secondBox = await secondCard.boundingBox();
    expect(firstBox).not.toBeNull();
    expect(secondBox).not.toBeNull();

    // Same x position means single column
    expect(firstBox!.x).toBeCloseTo(secondBox!.x, 0);
    // Second card is below the first
    expect(secondBox!.y).toBeGreaterThan(firstBox!.y + firstBox!.height / 2);

    await docScreenshot(page, "admin--settings-panel--mobile", {
      fullPage: true,
    });

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

    await docScreenshot(page, "admin--global-agents--table-view");

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

    // Edit and delete buttons should be present (Lucide icons render as SVGs)
    const actionButtons = page.locator("button:has(svg)");
    await expect(actionButtons.first()).toBeVisible();
    expect(await actionButtons.count()).toBeGreaterThanOrEqual(2);

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

    await docScreenshot(page, "admin--corpus-agents--table-view");

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
        .locator(".oc-modal-header__title")
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
  enabledComponents: [
    "opencontractserver.pipeline.parsers.docling.DoclingParser",
    "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
    "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
    "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
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
      supportedFileTypes: ["PDF"],
      enabled: true,
      settingsSchema: [],
    },
    {
      name: "llamaparse",
      title: "LlamaParser",
      description: "LlamaIndex cloud-based parser",
      className: "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
      supportedFileTypes: ["PDF"],
      enabled: true,
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
      enabled: true,
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
      supportedFileTypes: ["PDF"],
      enabled: true,
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

// fullySupported requires parser + embedder only; thumbnailer is optional.
// TXT and DOCX have thumbnailer: false but are still fullySupported: true
// because the pipeline only requires parser + embedder for upload acceptance.
const mockSupportedMimeTypes = [
  {
    mimetype: "application/pdf",
    fileType: "pdf",
    label: "PDF",
    fullySupported: true,
    stageCoverage: { parser: true, embedder: true, thumbnailer: true },
  },
  {
    mimetype: "text/plain",
    fileType: "txt",
    label: "Plain Text",
    fullySupported: true,
    stageCoverage: { parser: true, embedder: true, thumbnailer: false },
  },
  {
    mimetype:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    fileType: "docx",
    label: "Word Document",
    fullySupported: true,
    stageCoverage: { parser: true, embedder: true, thumbnailer: false },
  },
];

const mimeTypesMock = {
  request: { query: GET_SUPPORTED_MIME_TYPES },
  result: { data: { supportedMimeTypes: mockSupportedMimeTypes } },
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Should show loading state
    await expect(
      page.locator("text=Loading pipeline settings...")
    ).toBeVisible();

    await component.unmount();
  });

  test("should display settings page with both sections", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check both sections are visible
    await expect(page.locator("text=Pipeline Components")).toBeVisible();
    await expect(page.locator("text=Filetype Defaults")).toBeVisible();

    // Check component names are visible in ComponentLibrary section
    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib.locator("text=Docling Parser")).toBeVisible({
      timeout: 10000,
    });
    await expect(lib.locator("text=LlamaParser")).toBeVisible();
    await expect(lib.locator("text=OpenAI Ada Embedder")).toBeVisible();
    await expect(lib.locator("text=PDF Thumbnailer")).toBeVisible();

    await docScreenshot(page, "admin--pipeline-settings--overview");

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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
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

  test("should display component library with items and checkboxes", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // All 4 components should be visible in the component library
    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib.locator("text=Docling Parser")).toBeVisible({
      timeout: 10000,
    });
    await expect(lib.locator("text=LlamaParser")).toBeVisible();
    await expect(lib.locator("text=OpenAI Ada Embedder")).toBeVisible();
    await expect(lib.locator("text=PDF Thumbnailer")).toBeVisible();

    // Checkboxes should exist and be checked
    const checkboxes = lib.locator(
      'input[type="checkbox"][aria-label*="Disable"]'
    );
    await expect(checkboxes).toHaveCount(4);
    for (let i = 0; i < 4; i++) {
      await expect(checkboxes.nth(i)).toBeChecked();
    }

    await component.unmount();
  });

  test("should display components with secrets", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const lib = page.locator('[data-testid="component-library"]');
    const advancedSettingsButton = lib
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Click first Advanced Settings button (LlamaParser has secrets settings)
    await page.locator("button:has-text('Advanced Settings')").first().click();

    // Should show Secret Keys section
    await expect(page.locator("text=Secret Keys")).toBeVisible();

    await component.unmount();
  });

  test("should open secrets modal", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Expand first Advanced Settings (LlamaParser)
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

    await docScreenshot(page, "admin--pipeline-settings--secrets-modal");

    await component.unmount();
  });

  test("should open delete secrets confirmation modal", async ({
    mount,
    page,
  }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const lib = page.locator('[data-testid="component-library"]');
    const advancedSettingsButton = lib
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Expand first Advanced Settings (LlamaParser has secrets)
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
      <SystemSettingsWrapper
        mocks={[errorMock, componentsMock, mimeTypesMock]}
      />
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
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

  test("should display component library with filter chips", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check filter chips
    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib.locator("text=All").first()).toBeVisible();
    await expect(lib.locator("text=Parsers").first()).toBeVisible();
    await expect(lib.locator("text=Embedders").first()).toBeVisible();
    await expect(lib.locator("text=Thumbnailers").first()).toBeVisible();

    // All components should be visible in the component library
    await expect(lib.locator("text=Docling Parser")).toBeVisible({
      timeout: 10000,
    });
    await expect(lib.locator("text=LlamaParser")).toBeVisible();
    await expect(lib.locator("text=OpenAI Ada Embedder")).toBeVisible();
    await expect(lib.locator("text=PDF Thumbnailer")).toBeVisible();

    await docScreenshot(page, "admin--pipeline-settings--component-library");

    await component.unmount();
  });

  test("should filter component library by stage", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const lib = page.locator('[data-testid="component-library"]');

    // Click "Parsers" filter chip
    await lib.locator("[aria-pressed]", { hasText: "Parsers" }).click();

    // Only parsers should be visible in the component library
    await expect(lib.locator("text=Docling Parser")).toBeVisible({
      timeout: 10000,
    });
    await expect(lib.locator("text=LlamaParser")).toBeVisible();
    // Embedder and Thumbnailer should be hidden in the component library
    await expect(lib.locator("text=OpenAI Ada Embedder")).not.toBeVisible();
    await expect(lib.locator("text=PDF Thumbnailer")).not.toBeVisible();

    await docScreenshot(page, "admin--pipeline-settings--stage-filter");

    await component.unmount();
  });

  test("should search components by name", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    const lib = page.locator('[data-testid="component-library"]');

    // Type in the search input
    const searchInput = lib.locator(
      'input[placeholder="Search components..."]'
    );
    await searchInput.fill("Docling");

    // Only Docling Parser should be visible in the component library
    await expect(lib.locator("text=Docling Parser")).toBeVisible({
      timeout: 10000,
    });
    await expect(lib.locator("text=LlamaParser")).not.toBeVisible();
    await expect(lib.locator("text=OpenAI Ada Embedder")).not.toBeVisible();
    await expect(lib.locator("text=PDF Thumbnailer")).not.toBeVisible();

    await component.unmount();
  });

  test("should display enable/disable checkboxes for components", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check checkboxes exist (at least 4 for our components)
    const checkboxes = page.locator('input[type="checkbox"]');
    const count = await checkboxes.count();
    expect(count).toBeGreaterThanOrEqual(4);

    // All should be checked since all are in enabledComponents
    for (let i = 0; i < count; i++) {
      await expect(checkboxes.nth(i)).toBeChecked();
    }

    await component.unmount();
  });

  test("should display filetype defaults with dropdowns", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check Filetype Defaults section
    await expect(page.locator("text=Filetype Defaults")).toBeVisible();

    // Check MIME type labels (from supportedMimeTypes mock data)
    await expect(page.locator("text=PDF").first()).toBeVisible();
    await expect(page.locator("text=Plain Text").first()).toBeVisible();
    await expect(page.locator("text=Word Document").first()).toBeVisible();

    // Check select dropdowns exist (3 MIME types x 3 stages = 9 minimum)
    const selects = page.locator("select").filter({ visible: true });
    const selectCount = await selects.count();
    expect(selectCount).toBeGreaterThanOrEqual(9);

    await docScreenshot(page, "admin--pipeline-settings--filetype-defaults");

    await component.unmount();
  });

  test("should show assigned component in filetype dropdown", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check that the PDF parser dropdown has the Docling Parser selected
    const pdfParserSelect = page.locator(
      'select[aria-label="Parser for PDF files"]'
    );
    await expect(pdfParserSelect).toHaveValue(
      "opencontractserver.pipeline.parsers.docling.DoclingParser"
    );

    await component.unmount();
  });

  test("should display default embedder section in filetype defaults", async ({
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
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check Default Embedder section
    await expect(page.locator("text=Default Embedder")).toBeVisible();
    await expect(page.locator("button:has-text('Edit')")).toBeVisible();
    await expect(page.locator("text=Using system default")).toBeVisible();

    await component.unmount();
  });

  test("should display stage badges on components", async ({ mount, page }) => {
    const settingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // Check stage badges are visible (from STAGE_CONFIG titles)
    await expect(page.locator("text=Parser").first()).toBeVisible();
    await expect(page.locator("text=Embedder").first()).toBeVisible();
    await expect(page.locator("text=Thumbnailer").first()).toBeVisible();

    await docScreenshot(page, "admin--pipeline-settings--stage-badges");

    await component.unmount();
  });

  test("should filter filetype default dropdowns by MIME type support", async ({
    mount,
    page,
  }) => {
    // Mock components with different MIME type support
    const multiMimeComponents = {
      parsers: [
        {
          name: "docling",
          title: "Docling Parser",
          description: "ML-based document parser (PDF only)",
          className:
            "opencontractserver.pipeline.parsers.docling.DoclingParser",
          supportedFileTypes: ["PDF"],
          enabled: true,
          settingsSchema: [],
        },
        {
          name: "text_parser",
          title: "Text Parser",
          description: "Plain text parser",
          className:
            "opencontractserver.pipeline.parsers.text_parser.TextParser",
          supportedFileTypes: ["TXT"],
          enabled: true,
          settingsSchema: [],
        },
        {
          name: "universal_parser",
          title: "Universal Parser",
          description: "Handles all document types",
          className:
            "opencontractserver.pipeline.parsers.universal.UniversalParser",
          supportedFileTypes: ["PDF", "TXT", "DOCX"],
          enabled: true,
          settingsSchema: [],
        },
        {
          name: "docx_parser",
          title: "Word Document Parser",
          description: "Microsoft Word parser",
          className:
            "opencontractserver.pipeline.parsers.docx_parser.DocxParser",
          supportedFileTypes: ["DOCX"],
          enabled: true,
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
          supportedFileTypes: null,
          enabled: true,
          settingsSchema: [],
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
          enabled: true,
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
            preferredParsers: {},
            enabledComponents: [
              "opencontractserver.pipeline.parsers.docling.DoclingParser",
              "opencontractserver.pipeline.parsers.text_parser.TextParser",
              "opencontractserver.pipeline.parsers.universal.UniversalParser",
              "opencontractserver.pipeline.parsers.docx_parser.DocxParser",
              "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
              "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
            ],
          },
        },
      },
    };

    const componentsMock = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: multiMimeComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock, componentsMock, mimeTypesMock]}
      />
    );

    // Wait for page to load
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({
      timeout: 5000,
    });

    // PDF parser select should have: Unassigned + Docling + Universal + (OpenAI if embedder) = 3 parser options
    const pdfParserSelect = page.locator(
      'select[aria-label="Parser for PDF files"]'
    );
    const pdfParserOptions = pdfParserSelect.locator("option");
    // Unassigned + Docling Parser + Universal Parser = 3
    await expect(pdfParserOptions).toHaveCount(3);

    // TXT parser select should have: Unassigned + Text Parser + Universal Parser = 3
    const txtParserSelect = page.locator(
      'select[aria-label="Parser for Plain Text files"]'
    );
    const txtParserOptions = txtParserSelect.locator("option");
    await expect(txtParserOptions).toHaveCount(3);

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
              enabledComponents: [],
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
            enabledComponents: [],
            modified: "2024-01-15T11:00:00Z",
            modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock,
          componentsMock,
          mimeTypesMock,
          resetMock,
          refetchMock,
        ]}
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
      result: { data: { pipelineSettings: mockPipelineSettings } },
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
          mimeTypesMock,
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

    // Expand first Advanced Settings (LlamaParser)
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
      result: { data: { pipelineSettings: mockPipelineSettings } },
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
          mimeTypesMock,
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

    const lib = page.locator('[data-testid="component-library"]');
    const advancedSettingsButton = lib
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

// ============================================================================
// SystemSettings Two-Column Layout Tests
// ============================================================================

test.describe("SystemSettings Two-Column Layout", () => {
  const standardMocks = [
    {
      request: { query: GET_PIPELINE_SETTINGS },
      result: { data: { pipelineSettings: mockPipelineSettings } },
    },
    {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockPipelineComponents } },
    },
    mimeTypesMock,
  ];

  const waitForLoad = async (page: any) => {
    await expect(
      page.locator("h1:has-text('Pipeline Configuration')")
    ).toBeVisible({ timeout: 5000 });
  };

  test("should render both sections side-by-side on desktop viewport", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 1200, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={standardMocks} />
    );
    await waitForLoad(page);

    // Both sections should be visible simultaneously in the two-column layout
    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib).toBeVisible({ timeout: 10000 });
    await expect(lib.locator("text=Docling Parser")).toBeVisible({
      timeout: 10000,
    });

    await expect(page.locator("text=Filetype Defaults")).toBeVisible();
    await expect(page.locator("text=PDF").first()).toBeVisible();

    // Mobile tab bar should NOT be visible on desktop
    await expect(page.locator('div[role="tablist"]')).not.toBeVisible();

    await docScreenshot(page, "admin--pipeline-settings--two-column-desktop");

    await component.unmount();
  });

  test("should show mobile tab bar at narrow viewport", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 600, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={standardMocks} />
    );
    await waitForLoad(page);

    // Tab bar should be visible
    const tablist = page.locator('div[role="tablist"]');
    await expect(tablist).toBeVisible();

    // Both tab buttons should exist
    const libraryTab = tablist.locator('button:has-text("Component Library")');
    const defaultsTab = tablist.locator('button:has-text("Filetype Defaults")');
    await expect(libraryTab).toBeVisible();
    await expect(defaultsTab).toBeVisible();

    // Component Library tab should be active by default
    await expect(libraryTab).toHaveAttribute("aria-selected", "true");
    await expect(defaultsTab).toHaveAttribute("aria-selected", "false");

    // Component Library content should be visible
    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "admin--pipeline-settings--mobile-tabs");

    await component.unmount();
  });

  test("should switch tabs on mobile viewport", async ({ mount, page }) => {
    await page.setViewportSize({ width: 600, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={standardMocks} />
    );
    await waitForLoad(page);

    const tablist = page.locator('div[role="tablist"]');
    const libraryTab = tablist.locator('button:has-text("Component Library")');
    const defaultsTab = tablist.locator('button:has-text("Filetype Defaults")');

    // Click Filetype Defaults tab
    await defaultsTab.click();

    // Filetype Defaults tab should now be active
    await expect(defaultsTab).toHaveAttribute("aria-selected", "true");
    await expect(libraryTab).toHaveAttribute("aria-selected", "false");

    // Filetype Defaults content should be visible
    // Scope to the tabpanel to avoid matching hidden desktop layout elements
    const tabpanel = page.locator('div[role="tabpanel"]');
    await expect(tabpanel.locator("text=Filetype Defaults")).toBeVisible();
    await expect(tabpanel.locator("text=PDF").first()).toBeVisible();

    await docScreenshot(page, "admin--pipeline-settings--mobile-filetype-tab");

    // Switch back to Component Library
    await libraryTab.click();
    await expect(libraryTab).toHaveAttribute("aria-selected", "true");

    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("should have correct ARIA attributes on mobile tabs", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 600, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={standardMocks} />
    );
    await waitForLoad(page);

    // Verify tablist role
    const tablist = page.locator('div[role="tablist"]');
    await expect(tablist).toBeVisible();

    // Verify tab roles
    const tabs = tablist.locator('button[role="tab"]');
    await expect(tabs).toHaveCount(2);

    // Verify tabpanel role
    const tabpanel = page.locator('div[role="tabpanel"]');
    await expect(tabpanel).toBeVisible();

    await component.unmount();
  });

  test("should hide mobile tabs on desktop viewport", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 1200, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={standardMocks} />
    );
    await waitForLoad(page);

    // Mobile tab container should be hidden
    await expect(page.locator('div[role="tablist"]')).not.toBeVisible();

    // Both sections should be visible in two-column layout
    const lib = page.locator('[data-testid="component-library"]');
    await expect(lib).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=Filetype Defaults")).toBeVisible();

    await component.unmount();
  });
});
