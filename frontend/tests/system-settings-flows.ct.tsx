// Playwright Component Test covering additional SystemSettings flows not
// exercised in admin-components.ct.tsx: assignment via filetype dropdown,
// default-embedder modal, non-secret config save, mobile tab keyboard
// navigation, and mutation error paths.
import React from "react";
import type { Page } from "@playwright/test";
import { test, expect } from "./utils/coverage";
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
  parserKwargs: {},
  componentSettings: {},
  defaultEmbedder: null,
  componentsWithSecrets: [],
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
    // remove the entry and call updateSettings with an empty object.
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
        variables: { preferredParsers: {} },
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
    // className is still enabled and the chosen one is removed.
    const allPaths = [
      "opencontractserver.pipeline.parsers.docling.DoclingParser",
      "opencontractserver.pipeline.parsers.llamaparse.LlamaParser",
      "opencontractserver.pipeline.embedders.openai.OpenAIEmbedder",
      "opencontractserver.pipeline.thumbnailers.pdf.PDFThumbnailer",
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
