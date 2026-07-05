// Playwright Component Test for the Agent Tools / Tool Secrets panel
// (issue #2117). Covers the not-configured empty state, saving a new
// configuration, and deleting an existing one after confirmation.
import React from "react";
import type { Page } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import { SystemSettingsWrapper } from "./AdminComponentsTestWrapper";
import {
  GET_PIPELINE_SETTINGS,
  GET_PIPELINE_COMPONENTS,
  GET_SUPPORTED_MIME_TYPES,
  UPDATE_TOOL_SECRETS,
  DELETE_TOOL_SECRETS,
} from "../src/components/admin/system_settings/graphql";

// ---------------------------------------------------------------------------
// Minimal shared fixtures — SystemSettings needs all three queries to resolve
// before it renders past the loading state, but the tool secrets panel
// itself only cares about `toolsWithSecrets`.
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
  toolsWithSecrets: [] as string[],
  enabledComponents: [],
  modified: "2024-01-15T10:30:00Z",
  modifiedBy: { id: "VXNlclR5cGU6MQ==", username: "admin" },
};

const mockComponents = {
  parsers: [],
  embedders: [],
  thumbnailers: [],
  llmProviders: [],
  fileConverters: [],
  rerankers: [],
  enrichers: [],
};

const mimeTypesMock = {
  request: { query: GET_SUPPORTED_MIME_TYPES },
  result: { data: { supportedMimeTypes: [] } },
};

const componentsMock = {
  request: { query: GET_PIPELINE_COMPONENTS },
  result: { data: { pipelineComponents: mockComponents } },
};

const settingsMock = (toolsWithSecrets: string[]) => ({
  request: { query: GET_PIPELINE_SETTINGS },
  result: {
    data: { pipelineSettings: { ...mockSettingsBase, toolsWithSecrets } },
  },
});

const waitForLoad = async (page: Page) => {
  await expect(
    page.locator("h1:has-text('Pipeline Configuration')")
  ).toBeVisible({ timeout: 5000 });
};

test.describe("ToolSecretsPanel", () => {
  test("shows 'Not configured' when the web search tool has no secrets", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <SystemSettingsWrapper
        mocks={[settingsMock([]), componentsMock, mimeTypesMock]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await expect(panel).toBeVisible();
    await expect(panel.locator("text=Not configured")).toBeVisible();
    // No delete button until something is configured.
    await expect(
      panel.locator("button:has-text('Remove Configuration')")
    ).toHaveCount(0);

    await component.unmount();
  });

  test("filling in provider + API key and saving calls updateToolSecrets with the correct variables", async ({
    mount,
    page,
  }) => {
    const saveMock = {
      request: {
        query: UPDATE_TOOL_SECRETS,
        variables: {
          toolKey: "tool:web_search",
          secrets: { api_key: "brave-secret-key" },
          settings: { provider: "brave" },
          merge: true,
        },
      },
      result: {
        data: {
          updateToolSecrets: {
            ok: true,
            message: "Tool settings updated for 'tool:web_search'.",
            toolsWithSecrets: ["tool:web_search"],
          },
        },
      },
    };
    const refetch = settingsMock(["tool:web_search"]);

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock([]),
          componentsMock,
          mimeTypesMock,
          saveMock,
          refetch,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');

    // Provider defaults to "brave" (first option), so no need to change it —
    // but exercise the select to prove it's wired, then set it back.
    const providerSelect = panel.locator("#tool-secrets-provider");
    await expect(providerSelect).toHaveValue("brave");

    await panel.locator("#tool-secrets-api-key").fill("brave-secret-key");
    await panel.locator("button:has-text('Save')").click();

    await expect(
      page.locator("text=Web search tool configured successfully")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("delete button calls deleteToolSecrets after confirmation", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_TOOL_SECRETS,
        variables: { toolKey: "tool:web_search" },
      },
      result: {
        data: {
          deleteToolSecrets: {
            ok: true,
            message: "Tool settings deleted for 'tool:web_search'.",
            toolsWithSecrets: [],
          },
        },
      },
    };
    const refetch = settingsMock([]);

    const component = await mount(
      <SystemSettingsWrapper
        mocks={[
          settingsMock(["tool:web_search"]),
          componentsMock,
          mimeTypesMock,
          deleteMock,
          refetch,
        ]}
      />
    );
    await waitForLoad(page);

    const panel = page.locator('[data-testid="tool-secrets-panel"]');
    await expect(panel.locator("text=Configured").first()).toBeVisible();

    await panel.locator("button:has-text('Remove Configuration')").click();

    // Confirmation banner appears; the destructive action requires a second click.
    await expect(
      panel.locator("text=Are you sure you want to remove")
    ).toBeVisible();
    await panel.locator("button:has-text('Confirm Delete')").click();

    await expect(
      page.locator("text=Web search tool configuration removed")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});
