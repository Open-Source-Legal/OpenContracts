import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedResponse } from "@apollo/client/testing";
import { CreateCorpusActionModalTestWrapper } from "./CreateCorpusActionModalTestWrapper";
import {
  GET_FIELDSETS,
  GET_ANALYZERS,
  GET_AGENT_CONFIGURATIONS,
  GET_AVAILABLE_MODERATION_TOOLS,
  GET_AVAILABLE_DOCUMENT_TOOLS,
} from "../src/graphql/queries";
import {
  CREATE_CORPUS_ACTION,
  UPDATE_CORPUS_ACTION,
} from "../src/graphql/mutations";
import { DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS } from "../src/assets/configurations/constants";
import { docScreenshot } from "./utils/docScreenshot";

const TEST_CORPUS_ID = "corpus-123";

/* -------------------------------------------------------------------------- */
/* GraphQL Mocks                                                               */
/* -------------------------------------------------------------------------- */

const fieldsetsMock: MockedResponse = {
  request: {
    query: GET_FIELDSETS,
    variables: {},
  },
  result: {
    data: {
      fieldsets: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        edges: [
          {
            node: {
              id: "fs-1",
              name: "Contract Fields",
              description: "Fields for contracts",
              creator: { id: "u1", username: "alice" },
              inUse: true,
              columns: { edges: [] },
            },
          },
          {
            node: {
              id: "fs-2",
              name: "Invoice Fields",
              description: "Fields for invoices",
              creator: { id: "u1", username: "alice" },
              inUse: true,
              columns: { edges: [] },
            },
          },
        ],
      },
    },
  },
};

const analyzersMock: MockedResponse = {
  request: {
    query: GET_ANALYZERS,
    variables: {},
  },
  result: {
    data: {
      analyzers: {
        pageInfo: {
          hasNextPage: false,
          hasPreviousPage: false,
          startCursor: null,
          endCursor: null,
        },
        edges: [
          {
            node: {
              id: "an-1",
              analyzerId: "test-analyzer",
              description: "A test analyzer",
              hostGremlin: { id: "g1" },
              disabled: false,
              isPublic: true,
              manifest: {},
              inputSchema: {},
            },
          },
        ],
      },
    },
  },
};

const agentConfigsMock: MockedResponse = {
  request: {
    query: GET_AGENT_CONFIGURATIONS,
    variables: {
      isActive: true,
      name_Contains: undefined,
      first: 50,
    },
  },
  result: {
    data: {
      agentConfigurations: {
        edges: [
          {
            node: {
              id: "agent-1",
              name: "Document Summarizer",
              slug: "doc-summarizer",
              description: "Summarizes documents",
              systemInstructions: "You summarize documents.",
              availableTools: ["read_doc", "write_summary"],
              scope: "CORPUS",
              isActive: true,
              corpus: { id: TEST_CORPUS_ID, title: "Test Corpus" },
            },
          },
          {
            node: {
              id: "agent-2",
              name: "Global Helper",
              slug: "global-helper",
              description: "Helps generally",
              systemInstructions: "You help.",
              availableTools: [],
              scope: "GLOBAL",
              isActive: true,
              corpus: null,
            },
          },
        ],
      },
    },
  },
};

const documentToolsMock: MockedResponse = {
  request: {
    query: GET_AVAILABLE_DOCUMENT_TOOLS,
    variables: {},
  },
  result: {
    data: {
      availableTools: [
        {
          name: "read_document_text",
          description: "Read full document text",
          category: "document",
          requiresApproval: false,
        },
        {
          name: "update_document_summary",
          description: "Update document summary",
          category: "document",
          requiresApproval: true,
        },
      ],
    },
  },
};

const moderationToolsMock: MockedResponse = {
  request: {
    query: GET_AVAILABLE_MODERATION_TOOLS,
    variables: {},
  },
  result: {
    data: {
      availableTools: [
        {
          name: "lock_thread",
          description: "Lock a thread",
          category: "moderation",
          requiresApproval: false,
        },
        {
          name: "delete_message",
          description: "Soft delete a message",
          category: "moderation",
          requiresApproval: true,
        },
      ],
    },
  },
};

/* Generic mock list for create-mode initial render (default trigger=add_document) */
const baseCreateModeMocks: MockedResponse[] = [
  fieldsetsMock,
  analyzersMock,
  agentConfigsMock,
  documentToolsMock,
];

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

test.describe("CreateCorpusActionModal", () => {
  test("renders create modal with default fieldset action", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Default action type is fieldset
    await expect(page.getByText("Fieldset Configuration")).toBeVisible();

    await docScreenshot(page, "corpus--create-action-modal--fieldset-default");

    await component.unmount();
  });

  test("modal is hidden when open=false", async ({ mount, page }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
        open={false}
      />
    );

    // Title should not render
    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).not.toBeVisible();

    await component.unmount();
  });

  test("cancel button calls onClose and resets form", async ({
    mount,
    page,
  }) => {
    let closed = false;
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
        onClose={() => {
          closed = true;
        }}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Type a name to verify reset behavior side-effect (no mutation needed)
    const nameInput = page.locator('input[placeholder="Enter action name"]');
    await nameInput.fill("Throwaway");

    await page.getByRole("button", { name: "Cancel", exact: true }).click();

    // Wait for the close callback to fire
    await expect.poll(() => closed, { timeout: 5000 }).toBe(true);

    await component.unmount();
  });

  test("disabled and run-on-all-corpuses checkboxes toggle", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Initially Disabled checkbox
    const disabledLabel = page.locator("label", {
      hasText: "Initially Disabled",
    });
    const disabledInput = disabledLabel.locator('input[type="checkbox"]');
    await expect(disabledInput).not.toBeChecked();
    await disabledInput.click();
    await expect(disabledInput).toBeChecked();

    // Run on All Corpuses checkbox
    const runOnAllLabel = page.locator("label", {
      hasText: "Run on All Corpuses",
    });
    const runOnAllInput = runOnAllLabel.locator('input[type="checkbox"]');
    await expect(runOnAllInput).not.toBeChecked();
    await runOnAllInput.click();
    await expect(runOnAllInput).toBeChecked();

    await component.unmount();
  });

  test("renders edit modal with existing fieldset action", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
        actionToEdit={{
          id: "act-1",
          name: "My Existing Action",
          trigger: "ADD_DOCUMENT",
          disabled: false,
          runOnAllCorpuses: false,
          fieldset: { id: "fs-1", name: "Contract Fields" },
        }}
      />
    );

    await expect(
      page.getByText("Edit Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Form should be pre-populated with the existing action's name
    const nameInput = page.locator('input[placeholder="Enter action name"]');
    await expect(nameInput).toHaveValue("My Existing Action");

    // Update button text
    await expect(
      page.getByRole("button", { name: "Update Action", exact: true })
    ).toBeVisible();

    await component.unmount();
  });

  test("renders agent action with task instructions in edit mode", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
        actionToEdit={{
          id: "act-2",
          name: "Agent Action",
          trigger: "ADD_DOCUMENT",
          disabled: true,
          runOnAllCorpuses: true,
          agentConfig: {
            id: "agent-1",
            name: "Document Summarizer",
            description: "Summarizes documents",
          },
          taskInstructions: "Summarize this document concisely.",
          preAuthorizedTools: ["read_doc"],
        }}
      />
    );

    await expect(
      page.getByText("Edit Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Disabled & runOnAllCorpuses checkboxes were pre-populated
    const disabledLabel = page.locator("label", {
      hasText: "Initially Disabled",
    });
    await expect(disabledLabel.locator('input[type="checkbox"]')).toBeChecked();

    const runAllLabel = page.locator("label", {
      hasText: "Run on All Corpuses",
    });
    await expect(runAllLabel.locator('input[type="checkbox"]')).toBeChecked();

    // Agent Configuration section should be visible since actionType=agent
    await expect(page.getByText("Agent Configuration")).toBeVisible();

    await component.unmount();
  });

  test("submitting create with empty name shows toast error (no mutation)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Click Create Action without filling anything in
    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    // Toast should surface (react-toastify renders the message)
    await expect(
      page.getByText("Please enter a name for the action")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("create with fieldset action: validation prompts to select fieldset", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("My Fieldset Action");

    // Click Create Action without selecting fieldset
    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect(page.getByText("Please select a fieldset")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("successful create mutation (fieldset path) closes modal and calls onSuccess", async ({
    mount,
    page,
  }) => {
    let onSuccessCalled = false;
    let onCloseCalled = false;

    const successCreateMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_ACTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          name: "My Fieldset Action",
          trigger: "add_document",
          fieldsetId: "fs-1",
          analyzerId: undefined,
          agentConfigId: undefined,
          taskInstructions: undefined,
          preAuthorizedTools: undefined,
          createAgentInline: undefined,
          inlineAgentName: undefined,
          inlineAgentDescription: undefined,
          inlineAgentInstructions: undefined,
          inlineAgentTools: undefined,
          disabled: false,
          runOnAllCorpuses: false,
        },
      },
      result: {
        data: {
          createCorpusAction: {
            ok: true,
            message: "Created",
            obj: {
              id: "new-act",
              name: "My Fieldset Action",
              trigger: "ADD_DOCUMENT",
              disabled: false,
              runOnAllCorpuses: false,
              fieldset: { id: "fs-1", name: "Contract Fields" },
              analyzer: null,
              agentConfig: null,
              taskInstructions: null,
              preAuthorizedTools: null,
            },
          },
        },
      },
    };

    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={[...baseCreateModeMocks, successCreateMock]}
        corpusId={TEST_CORPUS_ID}
        onSuccess={() => {
          onSuccessCalled = true;
        }}
        onClose={() => {
          onCloseCalled = true;
        }}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Fill in name (default action type is fieldset)
    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("My Fieldset Action");

    // Open the fieldset dropdown
    await page.getByRole("combobox", { name: "Fieldset" }).click();
    await page.getByText("Contract Fields", { exact: true }).click();

    // Submit
    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    // onCompleted -> onSuccess + onClose
    await expect.poll(() => onSuccessCalled, { timeout: 10000 }).toBe(true);
    await expect.poll(() => onCloseCalled, { timeout: 10000 }).toBe(true);

    await component.unmount();
  });

  test("update mutation is invoked from edit mode", async ({ mount, page }) => {
    let onSuccessCalled = false;

    const updateMock: MockedResponse = {
      request: {
        query: UPDATE_CORPUS_ACTION,
        variables: {
          id: "act-3",
          name: "Renamed Action",
          trigger: "add_document",
          fieldsetId: "fs-1",
          analyzerId: undefined,
          agentConfigId: undefined,
          taskInstructions: undefined,
          preAuthorizedTools: undefined,
          disabled: false,
          runOnAllCorpuses: false,
        },
      },
      result: {
        data: {
          updateCorpusAction: {
            ok: true,
            message: "Updated",
            obj: {
              id: "act-3",
              name: "Renamed Action",
              trigger: "ADD_DOCUMENT",
              disabled: false,
              runOnAllCorpuses: false,
              fieldset: { id: "fs-1", name: "Contract Fields" },
              analyzer: null,
              agentConfig: null,
              taskInstructions: null,
              preAuthorizedTools: null,
            },
          },
        },
      },
    };

    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={[...baseCreateModeMocks, updateMock]}
        corpusId={TEST_CORPUS_ID}
        onSuccess={() => {
          onSuccessCalled = true;
        }}
        actionToEdit={{
          id: "act-3",
          name: "Original Name",
          trigger: "ADD_DOCUMENT",
          disabled: false,
          runOnAllCorpuses: false,
          fieldset: { id: "fs-1", name: "Contract Fields" },
        }}
      />
    );

    await expect(
      page.getByText("Edit Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Rename the action
    const nameInput = page.locator('input[placeholder="Enter action name"]');
    await nameInput.fill("Renamed Action");

    await page
      .getByRole("button", { name: "Update Action", exact: true })
      .click();

    await expect.poll(() => onSuccessCalled, { timeout: 10000 }).toBe(true);

    await component.unmount();
  });

  test("changing trigger to new_thread fetches moderation tools", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={[
          fieldsetsMock,
          analyzersMock,
          agentConfigsMock,
          documentToolsMock,
          moderationToolsMock,
        ]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Open the trigger dropdown
    await page.getByRole("combobox", { name: "Trigger" }).click();
    await page.getByText("On New Thread", { exact: true }).click();

    // Forced into agent action type with helper text
    await expect(
      page.getByText(
        "Thread/message triggers only support agent-based actions."
      )
    ).toBeVisible({ timeout: 5000 });

    // Inline mode is selected by default for thread triggers
    await expect(page.getByText("Quick Create Moderator")).toBeVisible();

    // Moderation tool descriptions from the dynamic mock (unique vs. defaults)
    await expect(page.getByText("Lock a thread")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Soft delete a message")).toBeVisible();

    await component.unmount();
  });

  test("inline agent: Clear All / Select All toggle tool selection", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Switch to agent action type
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Agent (AI-powered action)").click();

    await expect(page.getByText("Agent Configuration")).toBeVisible({
      timeout: 10000,
    });

    // Wait for document tools to load (they're auto-selected on load)
    await expect(page.getByText("read document text")).toBeVisible({
      timeout: 10000,
    });

    // Both tools start auto-selected: badge shows "2 selected"
    await expect(page.getByText("2 selected")).toBeVisible();

    // Clear All collapses badge to "0 selected"
    await page.getByRole("button", { name: "Clear All", exact: true }).click();
    await expect(page.getByText("0 selected")).toBeVisible({ timeout: 5000 });

    // Select All restores both
    await page.getByRole("button", { name: "Select All", exact: true }).click();
    await expect(page.getByText("2 selected")).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("switch to existing-agent mode shows agent dropdown", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Switch action type to agent
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Agent (AI-powered action)").click();

    await expect(page.getByText("Agent Configuration")).toBeVisible({
      timeout: 10000,
    });

    // Switch to "Use Existing Agent" tab
    await page.getByText("Use Existing Agent", { exact: true }).click();

    // Agent dropdown placeholder should appear
    await expect(
      page.getByText("Select agent configuration", { exact: true })
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("analyzer action: validation prompts to select analyzer", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Switch action type to analyzer
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Analyzer (Run analysis)").click();

    await expect(page.getByText("Analyzer Configuration")).toBeVisible({
      timeout: 10000,
    });

    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("My Analyzer Action");

    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect(page.getByText("Please select an analyzer")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("inline agent: empty name fails validation", async ({ mount, page }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("Outer action name");

    // Switch to agent
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Agent (AI-powered action)").click();

    await expect(page.getByText("Agent Configuration")).toBeVisible({
      timeout: 10000,
    });

    // Inline mode is default for document triggers — leave inline agent name empty
    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect(
      page.getByText("Please enter a name for the agent")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("inline agent: missing system instructions fails validation", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await page.locator('input[placeholder="Enter action name"]').fill("Outer");

    // Switch to agent
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Agent (AI-powered action)").click();

    await expect(page.getByText("Agent Configuration")).toBeVisible({
      timeout: 10000,
    });

    // Fill inline agent name via placeholder selector (document-trigger variant)
    await page
      .locator('input[placeholder="e.g., Document Summarizer"]')
      .fill("Doc Agent");

    // Clear the system-instructions textarea (document-trigger variant)
    await page
      .locator('textarea[placeholder*="Brief role description"]')
      .fill("");

    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect(
      page.getByText("Please enter system instructions for the agent")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("existing-agent mode: missing selection fails validation", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("Pickless");

    // Switch action type to agent and then to "Use Existing Agent"
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Agent (AI-powered action)").click();
    await expect(page.getByText("Agent Configuration")).toBeVisible({
      timeout: 10000,
    });
    await page.getByText("Use Existing Agent", { exact: true }).click();

    // Click Create Action without selecting an agent
    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect(
      page.getByText("Please select an agent configuration")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("inline-agent create: full happy path calls create mutation", async ({
    mount,
    page,
  }) => {
    let successCount = 0;

    // The default trigger is "add_document" (a document trigger), so the
    // textarea initialises with DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS. Importing
    // the constant keeps the mutation variables in sync if the default copy
    // ever changes.
    const inlineCreateMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_ACTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          name: "Inline Agent Action",
          trigger: "add_document",
          fieldsetId: undefined,
          analyzerId: undefined,
          agentConfigId: undefined,
          taskInstructions: "Process each document carefully.",
          preAuthorizedTools: ["read_document_text", "update_document_summary"],
          createAgentInline: true,
          inlineAgentName: "Inline Doc Agent",
          inlineAgentDescription: undefined,
          // The test does not fill the agent-instructions textarea, so the
          // submitted value is whatever the component initialises it to for the
          // default (document-add) trigger.
          inlineAgentInstructions: DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS,
          inlineAgentTools: ["read_document_text", "update_document_summary"],
          disabled: false,
          runOnAllCorpuses: false,
        },
      },
      result: {
        data: {
          createCorpusAction: {
            ok: true,
            message: "Created",
            obj: {
              id: "ca-inline",
              name: "Inline Agent Action",
              trigger: "ADD_DOCUMENT",
              disabled: false,
              runOnAllCorpuses: false,
              fieldset: null,
              analyzer: null,
              agentConfig: {
                id: "brand-new-agent",
                name: "Inline Doc Agent",
                description: "",
              },
              taskInstructions: "Process each document carefully.",
              preAuthorizedTools: [
                "read_document_text",
                "update_document_summary",
              ],
            },
          },
        },
      },
    };

    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={[...baseCreateModeMocks, inlineCreateMock]}
        corpusId={TEST_CORPUS_ID}
        onSuccess={() => {
          successCount += 1;
        }}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("Inline Agent Action");

    // Switch action type to agent (inline mode is the default for doc triggers)
    await page.getByRole("combobox", { name: "Action Type" }).click();
    await page.getByText("Agent (AI-powered action)").click();

    await expect(page.getByText("Agent Configuration")).toBeVisible({
      timeout: 10000,
    });

    // Fill inline agent name via placeholder
    await page
      .locator('input[placeholder="e.g., Document Summarizer"]')
      .fill("Inline Doc Agent");

    // Task instructions textarea (document-trigger variant)
    await page
      .locator(
        'textarea[placeholder*="Summarize this document and update its description"]'
      )
      .fill("Process each document carefully.");

    // Submit
    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect
      .poll(() => successCount, { timeout: 10000 })
      .toBeGreaterThan(0);

    await component.unmount();
  });

  test("create mutation error surfaces toast error", async ({
    mount,
    page,
  }) => {
    const erroringCreateMock: MockedResponse = {
      request: {
        query: CREATE_CORPUS_ACTION,
        variables: {
          corpusId: TEST_CORPUS_ID,
          name: "Will Fail",
          trigger: "add_document",
          fieldsetId: "fs-1",
          analyzerId: undefined,
          agentConfigId: undefined,
          taskInstructions: undefined,
          preAuthorizedTools: undefined,
          createAgentInline: undefined,
          inlineAgentName: undefined,
          inlineAgentDescription: undefined,
          inlineAgentInstructions: undefined,
          inlineAgentTools: undefined,
          disabled: false,
          runOnAllCorpuses: false,
        },
      },
      result: {
        data: {
          createCorpusAction: {
            ok: false,
            message: "Backend rejected the action",
            obj: null,
          },
        },
      },
    };

    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={[...baseCreateModeMocks, erroringCreateMock]}
        corpusId={TEST_CORPUS_ID}
      />
    );

    await expect(
      page.getByText("Create New Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("Will Fail");

    await page.getByRole("combobox", { name: "Fieldset" }).click();
    await page.getByText("Contract Fields", { exact: true }).click();

    await page
      .getByRole("button", { name: "Create Action", exact: true })
      .click();

    await expect(page.getByText("Backend rejected the action")).toBeVisible({
      timeout: 10000,
    });

    await component.unmount();
  });

  test("edit mode: analyzer action pre-populates selector", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
        actionToEdit={{
          id: "act-an-1",
          name: "My Analyzer Action",
          trigger: "ADD_DOCUMENT",
          disabled: false,
          runOnAllCorpuses: false,
          analyzer: { id: "an-1", name: "test-analyzer" },
        }}
      />
    );

    await expect(
      page.getByText("Edit Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    await expect(page.getByText("Analyzer Configuration")).toBeVisible();

    // Analyzer's description is rendered in the selected option
    const nameInput = page.locator('input[placeholder="Enter action name"]');
    await expect(nameInput).toHaveValue("My Analyzer Action");

    await component.unmount();
  });

  test("edit mode: legacy trigger casing normalizes to add_document", async ({
    mount,
    page,
  }) => {
    // "Add_Document" is neither fully upper-case nor lower-case — normalizer
    // falls through to default "add_document".
    const component = await mount(
      <CreateCorpusActionModalTestWrapper
        mocks={baseCreateModeMocks}
        corpusId={TEST_CORPUS_ID}
        actionToEdit={{
          id: "act-x",
          name: "Legacy",
          // Intentionally invalid trigger string — the double cast bypasses the
          // tight CorpusActionTrigger union type to exercise the normalizer's
          // default fallback branch.
          trigger: "Weird_Trigger" as unknown as string,
          disabled: false,
          runOnAllCorpuses: false,
          fieldset: { id: "fs-1", name: "Contract Fields" },
        }}
      />
    );

    await expect(
      page.getByText("Edit Corpus Action", { exact: true })
    ).toBeVisible({ timeout: 20000 });

    // Trigger label falls back to "On Document Add"
    await expect(page.getByText("On Document Add")).toBeVisible();

    await component.unmount();
  });
});
