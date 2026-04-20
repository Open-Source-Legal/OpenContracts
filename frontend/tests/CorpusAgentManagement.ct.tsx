import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CorpusAgentManagementTestWrapper } from "./CorpusAgentManagementTestWrapper";
import { GET_CORPUS_AGENTS, GET_AVAILABLE_TOOLS } from "../src/graphql/queries";
import {
  CREATE_AGENT_CONFIGURATION,
  DELETE_AGENT_CONFIGURATION,
} from "../src/graphql/mutations";

const TEST_CORPUS_ID = "corpus-aam-1";

/* -------------------------------------------------------------------------- */
/* Mock builders                                                              */
/* -------------------------------------------------------------------------- */

const buildAgentsMock = (agents: any[]): MockedResponse => ({
  request: {
    query: GET_CORPUS_AGENTS,
    variables: { corpusId: TEST_CORPUS_ID },
  },
  result: {
    data: {
      agentConfigurations: {
        edges: agents.map((a) => ({ node: a })),
      },
    },
  },
});

const toolsMock: MockedResponse = {
  request: {
    query: GET_AVAILABLE_TOOLS,
    variables: {},
  },
  result: {
    data: {
      availableTools: [
        {
          name: "read_doc",
          description: "Read document text",
          category: "document",
          requiresCorpus: false,
          requiresApproval: false,
        },
        {
          name: "write_doc",
          description: "Write to document",
          category: "document",
          requiresCorpus: false,
          requiresApproval: true,
        },
        {
          name: "search_corpus",
          description: "Semantic search across corpus",
          category: "corpus",
          requiresCorpus: true,
          requiresApproval: false,
        },
      ],
      availableToolCategories: ["document", "corpus"],
    },
  },
};

const sampleAgent = {
  id: "agent-1",
  name: "Summarizer",
  slug: "summarizer",
  description: "Summarizes documents and updates summaries",
  systemInstructions: "You summarize documents.",
  availableTools: ["read_doc", "write_doc"],
  permissionRequiredTools: ["write_doc"],
  badgeConfig: { icon: "bot", color: "#8b5cf6", label: "AI" },
  avatarUrl: null,
  scope: "CORPUS",
  isActive: true,
  isPublic: false,
  creator: { id: "u1", username: "alice" },
  created: "2026-01-01T00:00:00Z",
  modified: "2026-01-02T00:00:00Z",
};

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test.describe("CorpusAgentManagement", () => {
  test("renders permission notice when canUpdate is false", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[]}
        corpusId={TEST_CORPUS_ID}
        canUpdate={false}
      />
    );

    await expect(
      page.getByText(
        "You do not have permission to manage agents for this corpus."
      )
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });

  test("renders empty state when there are no agents", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[buildAgentsMock([]), toolsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("No Agent Configurations")).toBeVisible({
      timeout: 20000,
    });

    // Empty state has its own Create button
    const createButtons = page.getByRole("button", {
      name: "Create Agent",
      exact: true,
    });
    await expect(createButtons.first()).toBeVisible();

    await component.unmount();
  });

  test("renders an agent row with status badge and slug", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[buildAgentsMock([sampleAgent]), toolsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Summarizer", { exact: true })).toBeVisible({
      timeout: 20000,
    });
    await expect(page.locator("code").getByText("summarizer")).toBeVisible();
    await expect(page.getByText("Active")).toBeVisible();
    await expect(page.getByLabel("Edit agent")).toBeVisible();
    await expect(page.getByLabel("Delete agent")).toBeVisible();

    await component.unmount();
  });

  test("opens create modal and submits create mutation", async ({
    mount,
    page,
  }) => {
    const createMock: MockedResponse = {
      request: {
        query: CREATE_AGENT_CONFIGURATION,
        variables: {
          name: "New Agent",
          slug: null,
          description: "Some description",
          systemInstructions: "Be helpful.",
          availableTools: null,
          permissionRequiredTools: null,
          badgeConfig: { icon: "bot", color: "#8b5cf6", label: "AI" },
          avatarUrl: null,
          scope: "CORPUS",
          corpusId: TEST_CORPUS_ID,
          isPublic: false,
        },
      },
      result: {
        data: {
          createAgentConfiguration: {
            ok: true,
            message: "Created",
            agent: {
              id: "new-agent",
              name: "New Agent",
              slug: "new-agent",
              description: "Some description",
              badgeConfig: {
                icon: "bot",
                color: "#8b5cf6",
                label: "AI",
              },
              availableTools: [],
              permissionRequiredTools: [],
              isActive: true,
              isPublic: false,
            },
          },
        },
      },
    };

    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[
          buildAgentsMock([]),
          toolsMock,
          createMock,
          // Refetch after create
          buildAgentsMock([]),
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("No Agent Configurations")).toBeVisible({
      timeout: 20000,
    });

    // Open create modal via the section header button (most reliable selector)
    await page.locator("button:has-text('Create Agent')").first().click();

    await expect(
      page.getByText("Create Agent Configuration", { exact: true })
    ).toBeVisible({ timeout: 5000 });

    // Fill the form
    await page.locator('input[placeholder="Agent name"]').fill("New Agent");

    // The description and system instructions are textareas (the first two)
    const textareas = page.locator("textarea");
    await textareas.nth(0).fill("Some description");
    await textareas.nth(1).fill("Be helpful.");

    // Submit (Create Agent button inside the modal footer)
    await page
      .locator(".oc-modal button:has-text('Create Agent')")
      .last()
      .click();

    // Toast confirms creation
    await expect(page.getByText("Agent created successfully")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("create button is disabled when required fields are missing", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[buildAgentsMock([]), toolsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("No Agent Configurations")).toBeVisible({
      timeout: 20000,
    });

    await page.locator("button:has-text('Create Agent')").first().click();
    await expect(
      page.getByText("Create Agent Configuration", { exact: true })
    ).toBeVisible({ timeout: 5000 });

    // The Create Agent submit button (modal footer) should be disabled
    const submitBtn = page
      .locator(".oc-modal button:has-text('Create Agent')")
      .last();
    await expect(submitBtn).toBeDisabled();

    await component.unmount();
  });

  test("opens edit modal pre-populated with agent's data", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[buildAgentsMock([sampleAgent]), toolsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Summarizer", { exact: true })).toBeVisible({
      timeout: 20000,
    });

    await page.getByLabel("Edit agent").click();

    await expect(
      page.getByText(`Edit Agent Configuration: ${sampleAgent.name}`, {
        exact: true,
      })
    ).toBeVisible({ timeout: 5000 });

    // Name field is pre-populated
    await expect(page.locator('input[placeholder="Agent name"]')).toHaveValue(
      "Summarizer"
    );

    // Selected tools should appear as preview pills
    await expect(
      page.locator("span", { hasText: "read_doc" }).first()
    ).toBeVisible();

    await component.unmount();
  });

  test("opens delete confirmation and triggers delete mutation", async ({
    mount,
    page,
  }) => {
    const deleteMock: MockedResponse = {
      request: {
        query: DELETE_AGENT_CONFIGURATION,
        variables: { agentId: sampleAgent.id },
      },
      result: {
        data: {
          deleteAgentConfiguration: {
            ok: true,
            message: "Deleted",
          },
        },
      },
    };

    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[
          buildAgentsMock([sampleAgent]),
          toolsMock,
          deleteMock,
          // Refetch after delete
          buildAgentsMock([]),
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Summarizer", { exact: true })).toBeVisible({
      timeout: 20000,
    });

    await page.getByLabel("Delete agent").click();

    // Confirmation modal
    await expect(page.getByText("ARE YOU SURE?")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByText(`Are you sure you want to delete the agent "Summarizer"?`)
    ).toBeVisible();

    // Confirm
    await page.getByRole("button", { name: "Yes", exact: true }).click();

    await expect(page.getByText("Agent deleted successfully")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("cancelling delete dismisses the confirmation modal", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[buildAgentsMock([sampleAgent]), toolsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("Summarizer", { exact: true })).toBeVisible({
      timeout: 20000,
    });

    await page.getByLabel("Delete agent").click();

    await expect(page.getByText("ARE YOU SURE?")).toBeVisible({
      timeout: 5000,
    });

    await page.getByRole("button", { name: "No", exact: true }).click();

    await expect(page.getByText("ARE YOU SURE?")).not.toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("toggling a tool unlocks the Permission Required Tools section", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CorpusAgentManagementTestWrapper
        mocks={[buildAgentsMock([]), toolsMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(page.getByText("No Agent Configurations")).toBeVisible({
      timeout: 20000,
    });

    await page.locator("button:has-text('Create Agent')").first().click();

    await expect(
      page.getByText("Create Agent Configuration", { exact: true })
    ).toBeVisible({ timeout: 5000 });

    // Initially, no tools are selected, so the permission-required section
    // shows an info message prompting to pick available tools first.
    await expect(
      page.getByText(
        "Select available tools first to configure permission requirements."
      )
    ).toBeVisible();

    // Click the read_doc ToolItem (monospace ToolName inside the modal)
    await page.locator(".oc-modal").getByText("read_doc").first().click();

    // The info message should be gone now that there's a selected tool
    await expect(
      page.getByText(
        "Select available tools first to configure permission requirements."
      )
    ).not.toBeVisible();

    await component.unmount();
  });
});
