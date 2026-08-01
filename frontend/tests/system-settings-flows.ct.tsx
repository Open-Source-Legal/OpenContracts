// Playwright Component Test covering additional SystemSettings flows not
// exercised in admin-components.ct.tsx: assignment via filetype dropdown,
// default-embedder modal, non-secret config save, mobile tab keyboard
// navigation, and mutation error paths.
import React from "react";
import type { Page } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { SystemSettingsWrapper } from "./AdminComponentsTestWrapper";
import {
  GET_PIPELINE_SETTINGS,
  GET_PIPELINE_COMPONENTS,
  GET_SUPPORTED_MIME_TYPES,
  UPDATE_PIPELINE_SETTINGS,
} from "../src/components/admin/system_settings/graphql";

// ---------------------------------------------------------------------------
// Shared mock fixtures. The component schema for the LlamaParser pipeline
// parser includes both a secret (api_key) and non-secret settings
// (num_workers, verbose) to exercise the AdvancedSettingsPanel config path.
// ---------------------------------------------------------------------------
const mockSettingsBase = {
  preferredParsers: {},
  preferredEmbedders: {},
  preferredThumbnailers: {},
  preferredEnrichers: {},
  componentSettings: {},
  defaultEmbedder: null,
  defaultFileConverter: null,
  defaultLlm: null,
  defaultReranker: null,
  toolsWithSecrets: [],
  enabledComponents: [
    "opencontractserver.pipeline.parsers.docling.DoclingParser",
    "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
    "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
    "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
  ],
  modified: "2024-01-15T10:30:00Z",
  modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
};

const mockComponents = {
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
          name: "num_workers",
          settingType: "config",
          pythonType: "int",
          required: true,
          description: "Number of workers",
          default: "4",
          envVar: "LLAMA_PARSE_WORKERS",
          hasValue: false,
          currentValue: null,
        },
        {
          name: "verbose",
          settingType: "config",
          pythonType: "bool",
          required: false,
          description: "Verbose logging",
          default: "false",
          envVar: null,
          hasValue: false,
          currentValue: null,
        },
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
      settingsSchema: [],
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
  llmProviders: [
    {
      name: "anthropic",
      title: "Anthropic",
      description: "Anthropic's Claude family (Opus, Sonnet, Haiku)",
      className:
        "opencontractserver.pipeline.llm_providers.anthropic_provider.AnthropicProvider",
      providerKey: "anthropic",
      supportedModels: ["claude-opus-4-6", "claude-haiku-4-5"],
      requiresApiKey: true,
      enabled: true,
      settingsSchema: [],
    },
  ],
  fileConverters: [
    {
      name: "gotenberg",
      title: "Gotenberg PDF Converter",
      description: "Converts office/legacy formats to PDF via Gotenberg",
      className:
        "opencontractserver.pipeline.file_converters.gotenberg_converter.GotenbergFileConverter",
      supportedExtensions: [
        "doc",
        "rtf",
        "odt",
        "ppt",
        "pptx",
        "xls",
        "xlsx",
        "html",
        "png",
        "tiff",
      ],
      requiresApiKey: false,
      enabled: true,
      settingsSchema: [],
    },
  ],
  rerankers: [
    {
      name: "cross_encoder",
      title: "Cross-Encoder Reranker",
      description: "Second-stage reranking via a cross-encoder model",
      className:
        "opencontractserver.pipeline.rerankers.cross_encoder_reranker.CrossEncoderReranker",
      enabled: true,
      settingsSchema: [],
    },
  ],
  enrichers: [
    {
      name: "pdf_outline",
      title: "PDF Outline Enricher",
      description: "Turns embedded PDF bookmarks into section annotations",
      className:
        "opencontractserver.pipeline.enrichers.pdf_outline_enricher.PdfOutlineEnricher",
      supportedFileTypes: ["PDF"],
      enabled: true,
      settingsSchema: [],
    },
    {
      name: "metadata_enricher",
      title: "Metadata Enricher",
      description: "Extracts document metadata",
      className:
        "opencontractserver.pipeline.enrichers.metadata.MetadataEnricher",
      supportedFileTypes: ["PDF"],
      enabled: true,
      settingsSchema: [],
    },
  ],
};

const mockMimeTypes = [
  {
    mimetype: "application/pdf",
    fileType: "pdf",
    label: "PDF",
    fullySupported: true,
    stageCoverage: { parser: true, embedder: true, thumbnailer: true },
  },
];

const standardSettingsMock = {
  request: { query: GET_PIPELINE_SETTINGS },
  result: { data: { pipelineSettings: mockSettingsBase } },
};

const standardComponentsMock = {
  request: { query: GET_PIPELINE_COMPONENTS },
  result: { data: { pipelineComponents: mockComponents } },
};

const mimeTypesMock = {
  request: { query: GET_SUPPORTED_MIME_TYPES },
  result: { data: { supportedMimeTypes: mockMimeTypes } },
};

const waitForLoad = async (page: Page) => {
  await expect(
    page.locator("h1:has-text('Pipeline Configuration')")
  ).toBeVisible({ timeout: 5000 });
};

test.describe("SystemSettings — filetype default assignment", () => {
  test("selecting a parser in the dropdown fires UPDATE_PIPELINE_SETTINGS", async ({
    mount,
    page,
  }) => {
    // Expected variables passed to updateSettings when assigning the Docling
    // parser to the PDF MIME type.
    const updateMock = {
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
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              preferredParsers: {
                "application/pdf":
                  "opencontractserver.pipeline.parsers.docling.DoclingParser",
              },
            },
          },
        },
      },
    };

    // Refetch mocks after mutation completes.
    const refetchSettings = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            preferredParsers: {
              "application/pdf":
                "opencontractserver.pipeline.parsers.docling.DoclingParser",
            },
          },
        },
      },
    };
    const refetchComponents = {
      request: { query: GET_PIPELINE_COMPONENTS },
      result: { data: { pipelineComponents: mockComponents } },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          updateMock,
          refetchSettings,
          refetchComponents,
        ]}
      />
    );
    await waitForLoad(page);

    const parserSelect = page.locator(
      'select[aria-label="Parser for PDF files"]'
    );
    await expect(parserSelect).toHaveValue("");

    await parserSelect.selectOption(
      "opencontractserver.pipeline.parsers.docling.DoclingParser"
    );

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("selecting the empty option removes an existing assignment", async ({
    mount,
    page,
  }) => {
    // Settings have PDF -> Docling assigned; clearing the dropdown should
    // send just the changed MIME type with a null value, which the server
    // treats as a delete marker (removes the key, preserves any siblings).
    const settingsWithPdf = {
      ...mockSettingsBase,
      preferredParsers: {
        "application/pdf":
          "opencontractserver.pipeline.parsers.docling.DoclingParser",
      },
    };

    const clearMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredParsers: { "application/pdf": null } },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Cleared",
            pipelineSettings: mockSettingsBase,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithPdf } },
          },
          standardComponentsMock,
          mimeTypesMock,
          clearMock,
          standardSettingsMock,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const parserSelect = page.locator(
      'select[aria-label="Parser for PDF files"]'
    );
    await expect(parserSelect).toHaveValue(
      "opencontractserver.pipeline.parsers.docling.DoclingParser"
    );

    await parserSelect.selectOption("");

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("SystemSettings — file converter on/off", () => {
  // The install-wide pre-parse file converter is toggled entirely from this
  // GUI: picking a converter enables conversion, picking "None" (empty class
  // path) disables it. Both save through UPDATE_PIPELINE_SETTINGS with a single
  // `defaultFileConverter` variable — so a MockedProvider whose mock only
  // matches the expected variable value asserts the GUI sends the right thing.
  const GOTENBERG =
    "opencontractserver.pipeline.file_converters.gotenberg_converter.GotenbergFileConverter";

  test("enabling picks Gotenberg and fires UPDATE with the class path", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { defaultFileConverter: GOTENBERG },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              defaultFileConverter: GOTENBERG,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            defaultFileConverter: GOTENBERG,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // The row starts disabled (no converter configured in mockSettingsBase).
    await expect(
      page.locator("text=Disabled (no pre-parse conversion)")
    ).toBeVisible();

    await docScreenshot(
      page,
      "admin--pipeline-settings--file-converter-disabled",
      { element: page.locator('[data-testid="file-converter-row"]') }
    );

    await page.locator('[data-testid="edit-default-file-converter"]').click();
    await expect(page.locator("text=Edit File Converter")).toBeVisible();

    // Pick the Gotenberg converter card; the class-path input mirrors it.
    await page
      .locator(".oc-modal-body")
      .locator("text=Gotenberg PDF Converter")
      .first()
      .click();
    await expect(page.locator("#default-file-converter")).toHaveValue(
      GOTENBERG
    );

    await docScreenshot(
      page,
      "admin--pipeline-settings--file-converter-picker",
      {
        element: page.locator(".oc-modal"),
      }
    );

    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    // Success toast only appears if the mutation matched (variable == GOTENBERG).
    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("disabling picks 'None' and fires UPDATE with an empty string", async ({
    mount,
    page,
  }) => {
    // Start from the enabled state so the row shows the configured converter.
    const enabledSettingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            defaultFileConverter: GOTENBERG,
          },
        },
      },
    };
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { defaultFileConverter: "" },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              defaultFileConverter: null,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            defaultFileConverter: null,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          enabledSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // The row starts enabled (shows the configured class path).
    await expect(page.locator(`text=${GOTENBERG}`).first()).toBeVisible();

    await docScreenshot(
      page,
      "admin--pipeline-settings--file-converter-enabled",
      { element: page.locator('[data-testid="file-converter-row"]') }
    );

    await page.locator('[data-testid="edit-default-file-converter"]').click();
    await expect(page.locator("text=Edit File Converter")).toBeVisible();

    // Pick "None (conversion disabled)"; the class-path input clears.
    await page
      .locator(".oc-modal-body")
      .locator("text=None (conversion disabled)")
      .first()
      .click();
    await expect(page.locator("#default-file-converter")).toHaveValue("");

    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    // Success toast only appears if the mutation matched (variable == "").
    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("SystemSettings — default embedder modal", () => {
  test("opens the modal, lists embedders, and saves the selection", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: {
          defaultEmbedder:
            "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
        },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              defaultEmbedder:
                "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
            },
          },
        },
      },
    };

    const refetchSettings = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            defaultEmbedder:
              "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetchSettings,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // Click the Edit button next to the Default Embedder section.
    await page.locator("button:has-text('Edit')").first().click();

    // Modal shows "Edit Default Embedder" title.
    await expect(page.locator("text=Edit Default Embedder")).toBeVisible();

    // Available embedders list should appear (from the mock data).
    await expect(page.locator("text=Available Embedders:")).toBeVisible();

    // Click the OpenAI embedder card to populate the field.
    const openaiCard = page
      .locator(".oc-modal-body")
      .locator("text=OpenAI Ada Embedder")
      .first();
    await openaiCard.click();

    await expect(page.locator("#default-embedder")).toHaveValue(
      "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder"
    );

    // Save the selection.
    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("typing a custom class path directly into the input also works", async ({
    mount,
    page,
  }) => {
    const customPath = "opencontractserver.custom.CustomEmbedder";
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { defaultEmbedder: customPath },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              defaultEmbedder: customPath,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            defaultEmbedder: customPath,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    await page.locator("button:has-text('Edit')").first().click();
    await expect(page.locator("text=Edit Default Embedder")).toBeVisible();

    const input = page.locator("#default-embedder");
    await input.fill(customPath);

    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("SystemSettings — advanced config (non-secret) save", () => {
  test("shows Save Configuration after editing a config field and persists it", async ({
    mount,
    page,
  }) => {
    const expectedComponentSettings = {
      "opencontractserver.pipeline.parsers.llamaparse.LlamaParser": {
        num_workers: 8,
      },
    };

    const saveConfigMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { componentSettings: expectedComponentSettings },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              componentSettings: expectedComponentSettings,
            },
          },
        },
      },
    };

    const refetchSettings = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...mockSettingsBase,
            componentSettings: expectedComponentSettings,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveConfigMock,
          refetchSettings,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // Expand the LlamaParser advanced settings (it's first in the library).
    await page.locator("button:has-text('Advanced Settings')").first().click();

    // num_workers is a required int field — its label is visible.
    await expect(page.locator("text=Configuration").first()).toBeVisible();

    // Fill the num_workers input. Input id convention:
    // `config-library-<className>-<fieldName>`.
    const workersInput = page.locator(
      "#config-library-opencontractserver\\.pipeline\\.parsers\\.llamaparse\\.LlamaParser-num_workers"
    );
    await workersInput.fill("8");

    // Once dirty, the Save Configuration button appears.
    const saveBtn = page.locator("button:has-text('Save Configuration')");
    await expect(saveBtn).toBeVisible();
    await saveBtn.click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("changing a bool select dropdown marks the form dirty", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[standardSettingsMock, standardComponentsMock, mimeTypesMock]}
      />
    );
    await waitForLoad(page);

    await page.locator("button:has-text('Advanced Settings')").first().click();

    // The verbose config field renders as a <select> because pythonType="bool".
    const verboseSelect = page.locator(
      "select#config-library-opencontractserver\\.pipeline\\.parsers\\.llamaparse\\.LlamaParser-verbose"
    );
    await expect(verboseSelect).toBeVisible();
    await verboseSelect.selectOption("true");

    // Save Configuration appears now that isDirty is true.
    await expect(
      page.locator("button:has-text('Save Configuration')")
    ).toBeVisible();

    await component.unmount();
  });
});

test.describe("SystemSettings — mobile tab keyboard navigation", () => {
  const viewportMocks = [
    standardSettingsMock,
    standardComponentsMock,
    mimeTypesMock,
  ];

  test("ArrowRight moves focus/selection to the Filetype Defaults tab", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 600, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={viewportMocks} />
    );
    await waitForLoad(page);

    const libraryTab = page.locator("#settings-tab-library");
    const defaultsTab = page.locator("#settings-tab-defaults");

    await libraryTab.focus();
    await expect(libraryTab).toHaveAttribute("aria-selected", "true");

    await page.keyboard.press("ArrowRight");

    await expect(defaultsTab).toHaveAttribute("aria-selected", "true");
    await expect(libraryTab).toHaveAttribute("aria-selected", "false");

    await component.unmount();
  });

  test("ArrowLeft wraps around back to the last tab", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 600, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={viewportMocks} />
    );
    await waitForLoad(page);

    const libraryTab = page.locator("#settings-tab-library");
    const defaultsTab = page.locator("#settings-tab-defaults");

    await libraryTab.focus();
    await page.keyboard.press("ArrowLeft");

    // Pressing ArrowLeft on the first tab wraps to the last.
    await expect(defaultsTab).toHaveAttribute("aria-selected", "true");
    await expect(libraryTab).toHaveAttribute("aria-selected", "false");

    await component.unmount();
  });

  test("Home and End jump to the first and last tabs", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 600, height: 800 });

    const component = await mount(
      <SystemSettingsWrapper mocks={viewportMocks} />
    );
    await waitForLoad(page);

    const libraryTab = page.locator("#settings-tab-library");
    const defaultsTab = page.locator("#settings-tab-defaults");

    await libraryTab.focus();
    await page.keyboard.press("End");
    await expect(defaultsTab).toHaveAttribute("aria-selected", "true");

    await page.keyboard.press("Home");
    await expect(libraryTab).toHaveAttribute("aria-selected", "true");

    await component.unmount();
  });
});

test.describe("SystemSettings — mutation error branches", () => {
  test("network error on update shows 'Error updating settings' toast", async ({
    mount,
    page,
  }) => {
    const failingUpdate = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: {
          preferredParsers: {
            "application/pdf":
              "opencontractserver.pipeline.parsers.docling.DoclingParser",
          },
        },
      },
      error: new Error("backend unavailable"),
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          failingUpdate,
        ]}
      />
    );
    await waitForLoad(page);

    const parserSelect = page.locator(
      'select[aria-label="Parser for PDF files"]'
    );
    await parserSelect.selectOption(
      "opencontractserver.pipeline.parsers.docling.DoclingParser"
    );

    // The toast message is prefixed "Error updating settings: " and suffixed
    // with Apollo's NetworkError message, which varies between Apollo versions
    // (it may appear as "Error message not found." in 3.x). We assert the
    // prefix to prove the onError branch fired without coupling to Apollo
    // internals.
    await expect(page.locator("text=/Error updating settings:/")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("ok=false on update surfaces the server-provided message", async ({
    mount,
    page,
  }) => {
    const failingUpdate = {
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
            ok: false,
            message: "Parser not allowed for this file type",
            pipelineSettings: mockSettingsBase,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          failingUpdate,
        ]}
      />
    );
    await waitForLoad(page);

    const parserSelect = page.locator(
      'select[aria-label="Parser for PDF files"]'
    );
    await parserSelect.selectOption(
      "opencontractserver.pipeline.parsers.docling.DoclingParser"
    );

    await expect(
      page.locator("text=Parser not allowed for this file type")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("SystemSettings — enable/disable transitions", () => {
  test("unchecking a component when all-enabled builds explicit enabled list", async ({
    mount,
    page,
  }) => {
    // Settings start with empty enabledComponents ("all enabled" mode).
    const allEnabledSettings = {
      ...mockSettingsBase,
      enabledComponents: [],
    };

    // The toggle should flip the UI into explicit-list mode where every other
    // className is still enabled and the chosen one is removed. The order
    // mirrors how SystemSettings builds the list: parsers, embedders,
    // thumbnailers, then llmProviders.
    //
    // The Anthropic LLM provider AND the Gotenberg file converter MUST appear
    // here: both are non-filetype stages in the Component Library, so
    // rebuilding the enabled list from "all enabled" has to include them —
    // otherwise toggling an unrelated component would silently disable every
    // provider / converter. This asserts that regression guard.
    const allPaths = [
      "opencontractserver.pipeline.parsers.docling.DoclingParser",
      "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
      "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
      "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
      "opencontractserver.pipeline.llm_providers.anthropic_provider.AnthropicProvider",
      "opencontractserver.pipeline.file_converters.gotenberg_converter.GotenbergFileConverter",
    ];
    const expectedEnabled = allPaths.filter(
      (p) => p !== "opencontractserver.pipeline.parsers.docling.DoclingParser"
    );

    const updateMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { enabledComponents: expectedEnabled },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...allEnabledSettings,
              enabledComponents: expectedEnabled,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...allEnabledSettings,
            enabledComponents: expectedEnabled,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: allEnabledSettings } },
          },
          standardComponentsMock,
          mimeTypesMock,
          updateMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // Click the disable checkbox for Docling Parser. We use click() rather
    // than uncheck() because the checkbox's checked state is driven by
    // `component.enabled` from GET_PIPELINE_COMPONENTS — the refetch response
    // in this test keeps `enabled: true` (it only updates enabledComponents
    // in the settings payload), so Playwright's auto state-change assertion
    // would fail even though the onChange handler fires correctly.
    const disableDocling = page
      .locator('[data-testid="component-library"]')
      .locator('input[aria-label="Disable Docling Parser"]');
    await expect(disableDocling).toBeChecked();
    await disableDocling.click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("SystemSettings — LLM providers", () => {
  test("registered LLM providers render in the Component Library", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[standardSettingsMock, standardComponentsMock, mimeTypesMock]}
      />
    );
    await waitForLoad(page);

    const library = page.locator('[data-testid="component-library"]');

    // Narrow to the LLM Providers filter so the assertions are unambiguous.
    await library
      .locator('[data-testid="library-filter-llmProviders"]')
      .click();

    // Provider title, an "API key" indicator, and suggested-model chips show.
    await expect(library.locator("text=Anthropic").first()).toBeVisible();
    await expect(library.locator("text=API key").first()).toBeVisible();
    await expect(library.locator("text=claude-opus-4-6").first()).toBeVisible();
    await expect(
      library.locator('input[aria-label="Disable Anthropic"]')
    ).toBeChecked();

    // Capture the Component Library filtered to registered LLM providers.
    await docScreenshot(page, "settings--llm-picker--provider-library");

    await component.unmount();
  });

  test("Default LLM picker saves the selected model spec", async ({
    mount,
    page,
  }) => {
    const spec = "anthropic:claude-opus-4-6";
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { defaultLlm: spec },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: { ...mockSettingsBase, defaultLlm: spec },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: { ...mockSettingsBase, defaultLlm: spec },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // Target the Default LLM row's Edit button by its data-testid so the
    // selector stays stable if other Edit buttons are added above it.
    await page.locator('[data-testid="edit-default-llm"]').click();

    await expect(page.locator("text=Edit Default LLM")).toBeVisible();

    // Clicking a suggested-model chip fills the spec input with
    // "{providerKey}:{model}".
    await page
      .locator(".oc-modal-body")
      .locator("button:has-text('claude-opus-4-6')")
      .first()
      .click();
    await expect(page.locator("#default-llm")).toHaveValue(spec);

    // Capture the Default LLM picker modal with a model spec selected.
    await docScreenshot(page, "settings--llm-picker--model-selected");

    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("SystemSettings — default reranker", () => {
  // The install-wide post-retrieval reranker is toggled entirely from this GUI:
  // picking a reranker enables second-stage reranking, picking "None" (empty
  // class path) disables it. Both save through UPDATE_PIPELINE_SETTINGS with a
  // single `defaultReranker` variable.
  const RERANKER =
    "opencontractserver.pipeline.rerankers.cross_encoder_reranker.CrossEncoderReranker";

  test("enabling picks a reranker and fires UPDATE with the class path", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { defaultReranker: RERANKER },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...mockSettingsBase,
              defaultReranker: RERANKER,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: { ...mockSettingsBase, defaultReranker: RERANKER },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // The row starts disabled (no reranker configured in mockSettingsBase).
    await expect(page.locator("text=Disabled (no reranking)")).toBeVisible();

    await page.locator('[data-testid="edit-default-reranker"]').click();
    await expect(page.locator("text=Edit Default Reranker")).toBeVisible();

    // Pick the Cross-Encoder reranker card; the class-path input mirrors it.
    await page
      .locator(".oc-modal-body")
      .locator("text=Cross-Encoder Reranker")
      .first()
      .click();
    await expect(page.locator("#default-reranker")).toHaveValue(RERANKER);

    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    // Success toast only appears if the mutation matched (variable == RERANKER).
    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("disabling picks 'None' and fires UPDATE with an empty string", async ({
    mount,
    page,
  }) => {
    // Start from the enabled state so the row shows the configured reranker.
    const enabledSettingsMock = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: { ...mockSettingsBase, defaultReranker: RERANKER },
        },
      },
    };
    const saveMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { defaultReranker: "" },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: { ...mockSettingsBase, defaultReranker: null },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: { ...mockSettingsBase, defaultReranker: null },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          enabledSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // The row starts enabled (shows the configured class path).
    await expect(page.locator(`text=${RERANKER}`).first()).toBeVisible();

    await page.locator('[data-testid="edit-default-reranker"]').click();
    await expect(page.locator("text=Edit Default Reranker")).toBeVisible();

    // Pick "None (reranking disabled)"; the class-path input clears.
    await page
      .locator(".oc-modal-body")
      .locator("text=None (reranking disabled)")
      .first()
      .click();
    await expect(page.locator("#default-reranker")).toHaveValue("");

    await page
      .locator('.oc-modal-footer button:has-text("Save")')
      .first()
      .click();

    // Success toast only appears if the mutation matched (variable == "").
    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("typing a class path and dismissing the modal do not save", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          standardSettingsMock,
          standardComponentsMock,
          mimeTypesMock,
          standardComponentsMock,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    // Typing directly into the class-path input mirrors the field (no card
    // selection needed).
    await page.locator('[data-testid="edit-default-reranker"]').click();
    await expect(page.locator("text=Edit Default Reranker")).toBeVisible();
    await page.locator("#default-reranker").fill("some.custom.Reranker");
    await expect(page.locator("#default-reranker")).toHaveValue(
      "some.custom.Reranker"
    );

    // The header's close (X) button dismisses without saving.
    await page.locator(".oc-modal-header button[aria-label='Close']").click();
    await expect(page.locator("text=Edit Default Reranker")).toBeHidden();

    // Cancel also dismisses without saving.
    await page.locator('[data-testid="edit-default-reranker"]').click();
    await page.locator('.oc-modal-footer button:has-text("Cancel")').click();
    await expect(page.locator("text=Edit Default Reranker")).toBeHidden();

    // Escape dismisses the modal too (Modal's own onClose, distinct from the
    // header's close button).
    await page.locator('[data-testid="edit-default-reranker"]').click();
    await expect(page.locator("text=Edit Default Reranker")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("text=Edit Default Reranker")).toBeHidden();

    // Row remains disabled — nothing was saved.
    await expect(page.locator("text=Disabled (no reranking)")).toBeVisible();

    await component.unmount();
  });
});

test.describe("SystemSettings — enrichment chain editor", () => {
  // preferred_enrichers is a per-MIME ORDERED LIST (issue #2118), unlike the
  // single-class-path Parser/Thumbnailer stages above — so it gets its own
  // add/remove/reorder test suite rather than reusing the dropdown pattern.
  const PDF_OUTLINE =
    "opencontractserver.pipeline.enrichers.pdf_outline_enricher.PdfOutlineEnricher";
  const METADATA =
    "opencontractserver.pipeline.enrichers.metadata.MetadataEnricher";

  // "All enabled" (empty enabledComponents) so both mock enrichers are
  // selectable in the "Add enricher" dropdown regardless of the restrictive
  // list mockSettingsBase otherwise carries for the parser/embedder tests.
  const enricherSettingsBase = { ...mockSettingsBase, enabledComponents: [] };

  test("renders existing configured enrichers in order", async ({
    mount,
    page,
  }) => {
    const settingsWithChain = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE, METADATA] },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithChain } },
          },
          standardComponentsMock,
          mimeTypesMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await expect(editor).toBeVisible();
    const items = editor.locator("li");
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toContainText("PDF Outline Enricher");
    await expect(items.nth(1)).toContainText("Metadata Enricher");

    await docScreenshot(page, "admin--pipeline-settings--enrichment-chain", {
      element: editor,
    });

    await component.unmount();
  });

  test("empty state shows 'No enrichers configured'", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: enricherSettingsBase } },
          },
          standardComponentsMock,
          mimeTypesMock,
        ]}
      />
    );
    await waitForLoad(page);

    await expect(
      page
        .locator('[data-testid="enricher-chain-editor"]')
        .locator("text=No enrichers configured")
    ).toBeVisible();

    await component.unmount();
  });

  test("adding an enricher appends it and fires the mutation with the full list", async ({
    mount,
    page,
  }) => {
    const settingsWithOne = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE] },
    };
    const expectedChain = { "application/pdf": [PDF_OUTLINE, METADATA] };

    const addMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredEnrichers: expectedChain },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithOne,
              preferredEnrichers: expectedChain,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...settingsWithOne,
            preferredEnrichers: expectedChain,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithOne } },
          },
          standardComponentsMock,
          mimeTypesMock,
          addMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await editor
      .locator('select[aria-label="Add enricher for PDF files"]')
      .selectOption(METADATA);
    await editor.locator('button:has-text("Add")').click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("removing an enricher fires the mutation with the item excluded", async ({
    mount,
    page,
  }) => {
    const settingsWithTwo = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE, METADATA] },
    };
    const expectedChain = { "application/pdf": [METADATA] };

    const removeMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredEnrichers: expectedChain },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithTwo,
              preferredEnrichers: expectedChain,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...settingsWithTwo,
            preferredEnrichers: expectedChain,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithTwo } },
          },
          standardComponentsMock,
          mimeTypesMock,
          removeMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await editor.locator('button[aria-label="Remove PDF enricher 1"]').click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("moving an enricher down fires the mutation with the reordered list", async ({
    mount,
    page,
  }) => {
    const settingsWithTwo = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE, METADATA] },
    };
    const expectedChain = { "application/pdf": [METADATA, PDF_OUTLINE] };

    const reorderMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredEnrichers: expectedChain },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithTwo,
              preferredEnrichers: expectedChain,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...settingsWithTwo,
            preferredEnrichers: expectedChain,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithTwo } },
          },
          standardComponentsMock,
          mimeTypesMock,
          reorderMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await editor
      .locator('button[aria-label="Move PDF enricher 1 down"]')
      .click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("moving an enricher up fires the mutation with the reordered list", async ({
    mount,
    page,
  }) => {
    const settingsWithTwo = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE, METADATA] },
    };
    const expectedChain = { "application/pdf": [METADATA, PDF_OUTLINE] };

    const reorderMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredEnrichers: expectedChain },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithTwo,
              preferredEnrichers: expectedChain,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...settingsWithTwo,
            preferredEnrichers: expectedChain,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithTwo } },
          },
          standardComponentsMock,
          mimeTypesMock,
          reorderMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await editor.locator('button[aria-label="Move PDF enricher 2 up"]').click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("removing the only enricher for a MIME type clears its entry instead of leaving an empty list", async ({
    mount,
    page,
  }) => {
    const settingsWithOne = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE] },
    };
    // handleAssignEnrichers sends `null` for the MIME type entirely when the
    // resulting chain is empty (a delete marker the server merges away),
    // rather than persisting `{ "application/pdf": [] }`.
    const sentVariables = { "application/pdf": null };
    const resultingChain = {};

    const removeMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredEnrichers: sentVariables },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithOne,
              preferredEnrichers: resultingChain,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...settingsWithOne,
            preferredEnrichers: resultingChain,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithOne } },
          },
          standardComponentsMock,
          mimeTypesMock,
          removeMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await editor.locator('button[aria-label="Remove PDF enricher 1"]').click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("adding an enricher when preferredEnrichers is null falls back to an empty mapping", async ({
    mount,
    page,
  }) => {
    // settings.preferredEnrichers can come back null from the API (rather
    // than {}); handleAssignEnrichers must fall back to an empty mapping
    // instead of throwing on `{...null}`.
    const settingsWithNullEnrichers = {
      ...enricherSettingsBase,
      preferredEnrichers: null,
    };
    const expectedChain = { "application/pdf": [PDF_OUTLINE] };

    const addMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: { preferredEnrichers: expectedChain },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithNullEnrichers,
              preferredEnrichers: expectedChain,
            },
          },
        },
      },
    };
    const refetch = {
      request: { query: GET_PIPELINE_SETTINGS },
      result: {
        data: {
          pipelineSettings: {
            ...settingsWithNullEnrichers,
            preferredEnrichers: expectedChain,
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithNullEnrichers } },
          },
          standardComponentsMock,
          mimeTypesMock,
          addMock,
          refetch,
          standardComponentsMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    await editor
      .locator('select[aria-label="Add enricher for PDF files"]')
      .selectOption(PDF_OUTLINE);
    await editor.locator('button:has-text("Add")').click();

    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("falls back to a derived display name when an enricher has no title", async ({
    mount,
    page,
  }) => {
    const componentsWithBlankTitles = {
      ...mockComponents,
      enrichers: mockComponents.enrichers.map((e) => ({ ...e, title: "" })),
    };
    const settingsWithOne = {
      ...enricherSettingsBase,
      preferredEnrichers: { "application/pdf": [PDF_OUTLINE] },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithOne } },
          },
          {
            request: { query: GET_PIPELINE_COMPONENTS },
            result: {
              data: { pipelineComponents: componentsWithBlankTitles },
            },
          },
          mimeTypesMock,
        ]}
      />
    );
    await waitForLoad(page);

    const editor = page.locator('[data-testid="enricher-chain-editor"]');
    // Configured item: derived from the className, not the (blank) title.
    await expect(editor.locator("li").first()).toContainText(
      "PDF Outline Enricher"
    );
    // Available-to-add option: same derivation applied in the dropdown.
    await expect(
      editor.locator('select[aria-label="Add enricher for PDF files"] option')
    ).toContainText(["-- Select enricher --", "Metadata Enricher"]);

    await component.unmount();
  });
});

test.describe("SystemSettings — reverting a component setting (issue #2121)", () => {
  test("clearing a previously-populated field removes the key instead of sending an empty string", async ({
    mount,
    page,
  }) => {
    const LLAMA_PARSER =
      "opencontractserver.pipeline.parsers.llamaparse.LlamaParser";

    // Start with num_workers already saved as "8" so clearing it is an
    // EXPLICIT clear of a previously-populated value, not a no-op.
    const settingsWithConfig = {
      ...mockSettingsBase,
      componentSettings: {
        [LLAMA_PARSER]: { num_workers: 8 },
      },
    };
    const componentsWithCurrentValue = {
      ...mockComponents,
      parsers: mockComponents.parsers.map((p) =>
        p.className === LLAMA_PARSER
          ? {
              ...p,
              settingsSchema: p.settingsSchema.map((s) =>
                s.name === "num_workers"
                  ? { ...s, hasValue: true, currentValue: 8 }
                  : s
              ),
            }
          : p
      ),
    };

    // The key must be ABSENT from the submitted componentSettings for
    // LLAMA_PARSER — not present with an empty string.
    const clearMock = {
      request: {
        query: UPDATE_PIPELINE_SETTINGS,
        variables: {
          componentSettings: { [LLAMA_PARSER]: {} },
        },
      },
      result: {
        data: {
          updatePipelineSettings: {
            ok: true,
            message: "Updated",
            pipelineSettings: {
              ...settingsWithConfig,
              componentSettings: { [LLAMA_PARSER]: {} },
            },
          },
        },
      },
    };

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: { data: { pipelineSettings: settingsWithConfig } },
          },
          {
            request: { query: GET_PIPELINE_COMPONENTS },
            result: {
              data: { pipelineComponents: componentsWithCurrentValue },
            },
          },
          mimeTypesMock,
          clearMock,
          {
            request: { query: GET_PIPELINE_SETTINGS },
            result: {
              data: {
                pipelineSettings: {
                  ...settingsWithConfig,
                  componentSettings: { [LLAMA_PARSER]: {} },
                },
              },
            },
          },
          {
            request: { query: GET_PIPELINE_COMPONENTS },
            result: {
              data: { pipelineComponents: componentsWithCurrentValue },
            },
          },
        ]}
      />
    );
    await waitForLoad(page);

    await page.locator("button:has-text('Advanced Settings')").first().click();

    const workersInput = page.locator(
      "#config-library-opencontractserver\\.pipeline\\.parsers\\.llamaparse\\.LlamaParser-num_workers"
    );
    await expect(workersInput).toHaveValue("8");

    await workersInput.fill("");

    const saveBtn = page.locator("button:has-text('Save Configuration')");
    await expect(saveBtn).toBeVisible();
    await saveBtn.click();

    // The mock only matches (and the toast only fires) if the mutation was
    // called with num_workers ABSENT — not "" — from componentSettings.
    await expect(
      page.locator("text=Settings updated successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});
