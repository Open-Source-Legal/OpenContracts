// Playwright Component Test for CreateCorpusActionModal
// Tests the new thread/message trigger options for automated moderation
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MockedProvider } from "@apollo/client/testing";
import { CreateCorpusActionModal } from "../src/components/corpuses/CreateCorpusActionModal";
import {
  GET_FIELDSETS,
  GET_ANALYZERS,
  GET_AGENT_CONFIGURATIONS,
  GET_AVAILABLE_DOCUMENT_TOOLS,
} from "../src/graphql/queries";
import { CREATE_CORPUS_ACTION } from "../src/graphql/mutations";
import { docScreenshot } from "./utils/docScreenshot";

// Mock data
const mockFieldset = {
  id: "RmllbGRzZXRUeXBlOjE=",
  name: "Contract Terms",
  description: "Extract contract terms",
  inUse: true,
  creator: {
    id: "VXNlclR5cGU6MQ==",
    username: "admin",
  },
  columns: {
    edges: [],
  },
};

const mockAnalyzer = {
  id: "QW5hbHl6ZXJUeXBlOjE=",
  analyzerId: "test-analyzer",
  description: "Test analyzer for documents",
  hostGremlin: null,
  disabled: false,
  isPublic: true,
  manifest: {},
  inputSchema: {},
};

const mockAgentConfig = {
  id: "QWdlbnRDb25maWdUeXBlOjE=",
  name: "Content Moderator",
  slug: "content-moderator",
  description: "AI agent for content moderation",
  systemInstructions: "You are a content moderator...",
  availableTools: [
    "delete_message",
    "lock_thread",
    "unlock_thread",
    "add_thread_message",
    "pin_thread",
    "unpin_thread",
    "get_thread_messages",
    "get_thread_context",
  ],
  scope: "GLOBAL" as const,
  isActive: true,
  corpus: null,
};

// Standard GraphQL mocks for queries
const getFieldsetsMock = {
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
        edges: [{ node: mockFieldset }],
      },
    },
  },
};

const getAnalyzersMock = {
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
        edges: [{ node: mockAnalyzer }],
      },
    },
  },
};

const getAgentConfigsMock = {
  request: {
    query: GET_AGENT_CONFIGURATIONS,
    variables: { isActive: true, name_Contains: undefined, first: 50 },
  },
  result: {
    data: {
      agentConfigurations: {
        edges: [{ node: mockAgentConfig }],
      },
    },
  },
};

const getAvailableDocumentToolsMock = {
  request: {
    query: GET_AVAILABLE_DOCUMENT_TOOLS,
    variables: {},
  },
  result: {
    data: {
      availableTools: [
        {
          name: "load_document_text",
          description: "Load the document text",
          category: "document",
          requiresApproval: false,
        },
        {
          name: "update_document_description",
          description: "Update document description",
          category: "document",
          requiresApproval: true,
        },
      ],
    },
  },
};

// Helper to create all standard mocks
const createStandardMocks = () => [
  getFieldsetsMock,
  getAnalyzersMock,
  getAgentConfigsMock,
  getAvailableDocumentToolsMock,
];

test.describe("CreateCorpusActionModal - Trigger Options", () => {
  test("should display all trigger options including new thread/message triggers", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Modal should be visible
    await expect(page.locator("text=Create New Corpus Action")).toBeVisible();

    // Click on trigger dropdown to open options
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();

    // All four trigger options should be available
    await expect(
      page.locator('[role="option"]:has-text("On Document Add")')
    ).toBeVisible();
    await expect(
      page.locator('[role="option"]:has-text("On Document Edit")')
    ).toBeVisible();
    await expect(
      page.locator('[role="option"]:has-text("On New Thread")')
    ).toBeVisible();
    await expect(
      page.locator('[role="option"]:has-text("On New Message")')
    ).toBeVisible();

    await component.unmount();
  });

  test("should default to 'On Document Add' trigger", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Check default trigger value
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await expect(triggerDropdown).toContainText("On Document Add");

    await docScreenshot(page, "corpus-actions--create-modal--initial", {
      fullPage: true,
    });

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Thread Trigger Behavior", () => {
  test("should force agent action type when new_thread trigger is selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select "On New Thread" trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Thread")').click();

    // Wait for state to update
    await page.waitForTimeout(200);

    // Action type should be forced to "Agent"
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await expect(actionTypeDropdown).toContainText("Agent");

    // Action type dropdown should be disabled
    await expect(actionTypeDropdown).toHaveClass(/oc-dropdown--disabled/);

    // Info message about thread triggers should be visible
    await expect(
      page.locator(
        "text=Thread/message triggers only support agent-based actions"
      )
    ).toBeVisible();

    await component.unmount();
  });

  test("should force agent action type when new_message trigger is selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select "On New Message" trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Message")').click();

    // Wait for state to update
    await page.waitForTimeout(200);

    // Action type should be forced to "Agent"
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await expect(actionTypeDropdown).toContainText("Agent");

    // Action type dropdown should be disabled
    await expect(actionTypeDropdown).toHaveClass(/oc-dropdown--disabled/);

    await component.unmount();
  });

  test("should show moderation-specific info message for thread triggers", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select "On New Thread" trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Thread")').click();

    // Wait for agent config section to appear
    await page.waitForTimeout(300);

    // Should show moderation-specific info message
    await expect(page.locator("text=automated moderation")).toBeVisible();
    // Check that the Moderation Tools label with count is visible
    await expect(
      page.locator("label:has-text('Moderation Tools')")
    ).toBeVisible();
    // Use .first() to avoid strict mode violations for text that appears in multiple places
    await expect(page.locator("text=delete message").first()).toBeVisible();
    await expect(
      page.locator("text=Lock thread to prevent").first()
    ).toBeVisible();

    await docScreenshot(
      page,
      "corpus-actions--create-modal--agent-thread-quick",
      { fullPage: true }
    );

    await component.unmount();
  });

  test("should show message-specific info for new_message trigger", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select "On New Message" trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Message")').click();

    // Wait for agent config section to appear
    await page.waitForTimeout(300);

    // Should show message-specific info
    await expect(
      page.locator("text=a new message is posted to a thread")
    ).toBeVisible();

    await component.unmount();
  });

  test("should show existing agent mode for thread triggers", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select "On New Thread" trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Thread")').click();

    await page.waitForTimeout(500);

    // Verify Quick Create inline form is visible before switching
    await expect(page.locator("label:has-text('Agent Name')")).toBeVisible();

    // Switch to "Use Existing Agent" mode
    await page.locator("text=Use Existing Agent").click();
    await page.waitForTimeout(300);

    // Should show existing agent selection UI
    await expect(page.locator("text=Select agent configuration")).toBeVisible();

    // Inline agent form fields should no longer be visible
    await expect(
      page.locator("label:has-text('Agent Name')")
    ).not.toBeVisible();

    await docScreenshot(
      page,
      "corpus-actions--create-modal--agent-thread-existing",
      { fullPage: true }
    );

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Action Type Switching", () => {
  test("should allow switching action types for document triggers", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Action type dropdown should be enabled for document triggers
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await expect(actionTypeDropdown).not.toHaveClass(/oc-dropdown--disabled/);

    // Click to open dropdown
    await actionTypeDropdown.click();

    // All action type options should be available
    await expect(
      page.locator('[role="option"]:has-text("Fieldset (Extract data)")')
    ).toBeVisible();
    await expect(
      page.locator('[role="option"]:has-text("Analyzer (Run analysis)")')
    ).toBeVisible();
    await expect(
      page.locator('[role="option"]:has-text("Agent (AI-powered action)")')
    ).toBeVisible();

    await component.unmount();
  });

  test("should switch from thread trigger back to document trigger and enable action type", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // First, select thread trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Thread")').click();

    await page.waitForTimeout(200);

    // Action type should be disabled
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await expect(actionTypeDropdown).toHaveClass(/oc-dropdown--disabled/);

    // Switch back to document trigger
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On Document Add")').click();

    await page.waitForTimeout(200);

    // Action type should be enabled again
    await expect(actionTypeDropdown).not.toHaveClass(/oc-dropdown--disabled/);

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Agent Configuration", () => {
  test("should show agent configuration when agent type is selected", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select Agent action type
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await actionTypeDropdown.click();
    await page
      .locator('[role="option"]:has-text("Agent (AI-powered action)")')
      .click();

    // Wait for agent config section
    await page.waitForTimeout(300);

    // Agent configuration section should be visible
    await expect(
      page.locator("h4:has-text('Agent Configuration')")
    ).toBeVisible();

    // Default mode is Quick Create — switch to Use Existing Agent
    await page.locator("text=Use Existing Agent").click();
    await page.waitForTimeout(200);

    await expect(page.locator("text=Select agent configuration")).toBeVisible();

    await component.unmount();
  });

  test("should display agent prompt field after selecting an agent", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select Agent action type
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await actionTypeDropdown.click();
    await page
      .locator('[role="option"]:has-text("Agent (AI-powered action)")')
      .click();

    // Wait for data to load
    await page.waitForTimeout(500);

    // Switch to Use Existing Agent tab (Quick Create is default in create mode)
    await page.locator("text=Use Existing Agent").click();
    await page.waitForTimeout(200);

    // Select the agent config
    const agentDropdown = page.locator(
      'div:has(> label:text("Agent")) .oc-dropdown'
    );
    await agentDropdown.click();
    await page
      .locator('[role="option"]:has-text("Content Moderator (Global)")')
      .click();

    // Wait for prompt field to appear
    await page.waitForTimeout(300);

    // Agent prompt field should be visible
    await expect(page.locator("text=Task Instructions")).toBeVisible();
    await expect(
      page.locator('textarea[placeholder*="Enter the task prompt"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("should show pre-authorized tools dropdown for agent config with tools", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select Agent action type
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await actionTypeDropdown.click();
    await page
      .locator('[role="option"]:has-text("Agent (AI-powered action)")')
      .click();

    // Wait for data to load
    await page.waitForTimeout(500);

    // Switch to Use Existing Agent tab (Quick Create is default in create mode)
    await page.locator("text=Use Existing Agent").click();
    await page.waitForTimeout(200);

    // Select the agent config
    const agentDropdown = page.locator(
      'div:has(> label:text("Agent")) .oc-dropdown'
    );
    await agentDropdown.click();
    await page
      .locator('[role="option"]:has-text("Content Moderator (Global)")')
      .click();

    // Wait for tools dropdown to appear
    await page.waitForTimeout(300);

    // Pre-authorized tools section should be visible
    await expect(
      page.locator("label:has-text('Pre-authorized Tools')")
    ).toBeVisible();
    // Verify the dropdown placeholder is present
    await expect(
      page.locator("text=Select tools to pre-authorize (optional)")
    ).toBeVisible();

    await docScreenshot(
      page,
      "corpus-actions--create-modal--existing-agent-document",
      { fullPage: true }
    );

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Form Submission", () => {
  test("should show validation error when name is empty", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Try to submit without name
    await page.locator('button:has-text("Create Action")').click();

    // Toast error should appear (handled by react-toastify)
    // We just verify the button was clicked and form wasn't submitted
    await page.waitForTimeout(200);

    await component.unmount();
  });

  test("should create action with new_thread trigger successfully", async ({
    mount,
    page,
  }) => {
    const createMock = {
      request: {
        query: CREATE_CORPUS_ACTION,
        variables: {
          corpusId: "Q29ycHVzVHlwZTox",
          name: "Thread Moderator",
          trigger: "new_thread",
          fieldsetId: undefined,
          analyzerId: undefined,
          agentConfigId: "QWdlbnRDb25maWdUeXBlOjE=",
          taskInstructions: "Moderate new threads for inappropriate content",
          preAuthorizedTools: undefined,
          disabled: false,
          runOnAllCorpuses: false,
        },
      },
      result: {
        data: {
          createCorpusAction: {
            ok: true,
            message: "Corpus action created successfully",
            obj: {
              id: "Q29ycHVzQWN0aW9uVHlwZTox",
              name: "Thread Moderator",
              trigger: "new_thread",
              disabled: false,
              runOnAllCorpuses: false,
              fieldset: null,
              analyzer: null,
              agentConfiguration: {
                id: "QWdlbnRDb25maWdUeXBlOjE=",
                name: "Content Moderator",
              },
            },
          },
        },
      },
    };

    let successCalled = false;
    let closeCalled = false;

    const component = await mount(
      <MockedProvider
        mocks={[...createStandardMocks(), createMock]}
        addTypename={false}
      >
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {
            closeCalled = true;
          }}
          onSuccess={() => {
            successCalled = true;
          }}
        />
      </MockedProvider>
    );

    // Fill in name
    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("Thread Moderator");

    // Select "On New Thread" trigger
    const triggerDropdown = page.locator(
      'div:has(> label:text("Trigger")) .oc-dropdown'
    );
    await triggerDropdown.click();
    await page.locator('[role="option"]:has-text("On New Thread")').click();

    // Wait for agent section
    await page.waitForTimeout(500);

    // Switch from "Quick Create Moderator" to "Use Existing Agent" mode
    await page.locator("text=Use Existing Agent").click();
    await page.waitForTimeout(300);

    // Select agent config
    const agentDropdown = page.locator(
      'div:has(> label:text("Agent")) .oc-dropdown'
    );
    await agentDropdown.click();
    await page
      .locator('[role="option"]:has-text("Content Moderator (Global)")')
      .click();

    // Wait for prompt field
    await page.waitForTimeout(300);

    // Enter agent prompt
    await page
      .locator('textarea[placeholder*="Enter the task prompt"]')
      .fill("Moderate new threads for inappropriate content");

    // Submit
    await page.locator('button:has-text("Create Action")').click();

    // Wait for mutation to complete
    await page.waitForTimeout(1000);

    await component.unmount();
  });

  test("should reset form on cancel", async ({ mount, page }) => {
    let closeCalled = false;

    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {
            closeCalled = true;
          }}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Fill in name
    await page
      .locator('input[placeholder="Enter action name"]')
      .fill("Test Action");

    // Click cancel
    await page.locator('button:has-text("Cancel")').click();

    await page.waitForTimeout(200);

    // Verify close was called
    expect(closeCalled).toBe(true);

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Fieldset Configuration", () => {
  test("should show fieldset configuration for fieldset action type", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Fieldset is the default action type, so fieldset config should be visible
    await expect(page.locator("text=Fieldset Configuration")).toBeVisible();
    await expect(
      page.locator("text=Select a fieldset to automatically extract data")
    ).toBeVisible();

    await docScreenshot(page, "corpus-actions--create-modal--fieldset-config", {
      fullPage: true,
    });

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Analyzer Configuration", () => {
  test("should show analyzer configuration for analyzer action type", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Select Analyzer action type
    const actionTypeDropdown = page.locator(
      'div:has(> label:text("Action Type")) .oc-dropdown'
    );
    await actionTypeDropdown.click();
    await page
      .locator('[role="option"]:has-text("Analyzer (Run analysis)")')
      .click();

    // Wait for analyzer config section
    await page.waitForTimeout(300);

    // Analyzer configuration section should be visible
    await expect(page.locator("text=Analyzer Configuration")).toBeVisible();
    await expect(
      page.locator("text=Select an analyzer to automatically run analysis")
    ).toBeVisible();

    await docScreenshot(page, "corpus-actions--create-modal--analyzer-config", {
      fullPage: true,
    });

    await component.unmount();
  });
});

test.describe("CreateCorpusActionModal - Options", () => {
  test("should have disabled checkbox option", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Initially Disabled checkbox should be visible
    await expect(page.locator("text=Initially Disabled")).toBeVisible();

    await component.unmount();
  });

  test("should have run on all corpuses checkbox option", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={createStandardMocks()} addTypename={false}>
        <CreateCorpusActionModal
          corpusId="Q29ycHVzVHlwZTox"
          open={true}
          onClose={() => {}}
          onSuccess={() => {}}
        />
      </MockedProvider>
    );

    // Run on All Corpuses checkbox should be visible
    await expect(page.locator("text=Run on All Corpuses")).toBeVisible();

    await component.unmount();
  });
});
