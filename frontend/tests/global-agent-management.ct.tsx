// Playwright Component Test for GlobalAgentManagement CRUD flows.
// Extends the coverage in admin-components.ct.tsx by exercising the create,
// update, and delete code paths plus form validation + error branches.
import React from "react";
import { test, expect } from "./utils/coverage";
import {
  GlobalAgentManagementWrapper,
  GlobalAgentManagementWithToastsWrapper,
} from "./AdminComponentsTestWrapper";
// Import the same GraphQL documents the production component uses so a
// field/variable change on one side is caught by tsc or a mock miss,
// rather than silently desyncing the test copy.
import {
  GET_GLOBAL_AGENTS,
  CREATE_GLOBAL_AGENT_CONFIGURATION,
  UPDATE_GLOBAL_AGENT_CONFIGURATION,
  DELETE_GLOBAL_AGENT_CONFIGURATION,
} from "../src/components/admin/global_agent_management.graphql";

const baseAgent = {
  id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZTox",
  name: "Research Assistant",
  slug: "research-assistant",
  description: "AI assistant for research and document analysis",
  systemInstructions: "You are a helpful research assistant...",
  availableTools: ["similarity_search", "load_document_text"],
  permissionRequiredTools: [] as string[],
  badgeConfig: { icon: "robot", color: "#6366f1", label: "AI" },
  avatarUrl: null as string | null,
  scope: "GLOBAL",
  isActive: true,
  isPublic: true,
  creator: { id: "VXNlclR5cGU6MQ==", username: "admin" },
  created: "2024-01-15T10:30:00Z",
  modified: "2024-01-15T10:30:00Z",
};

const emptyAgentsMock = {
  request: { query: GET_GLOBAL_AGENTS },
  result: { data: { agentConfigurations: { edges: [] } } },
};

const singleAgentMock = {
  request: { query: GET_GLOBAL_AGENTS },
  result: {
    data: { agentConfigurations: { edges: [{ node: baseAgent }] } },
  },
};

test.describe("GlobalAgentManagement — loading and error states", () => {
  test("shows loading state while the agents query is pending", async ({
    mount,
    page,
  }) => {
    const delayedMock = {
      request: { query: GET_GLOBAL_AGENTS },
      result: {
        data: { agentConfigurations: { edges: [] } },
      },
      delay: 800,
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[delayedMock]} />
    );

    await expect(page.locator("text=Loading agents...")).toBeVisible();

    await component.unmount();
  });

  test("shows error state when the agents query fails", async ({
    mount,
    page,
  }) => {
    const errorMock = {
      request: { query: GET_GLOBAL_AGENTS },
      error: new Error("You are not allowed to view this page"),
    };

    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[errorMock]} />
    );

    // MockedProvider surfaces an Apollo NetworkError whose message varies by
    // version ("Error message not found." in some 3.x builds). We only assert
    // that the <ErrorMessage> title is rendered — that alone demonstrates
    // the `if (error)` branch in GlobalAgentManagement was taken.
    await expect(page.locator("text=Error loading agents")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});

test.describe("GlobalAgentManagement — agent list rendering", () => {
  test("renders a dash when the slug is missing", async ({ mount, page }) => {
    const noSlugAgent = {
      ...baseAgent,
      id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZToxMDA=",
      slug: null,
    };

    const component = await mount(
      <GlobalAgentManagementWrapper
        mocks={[
          {
            request: { query: GET_GLOBAL_AGENTS },
            result: {
              data: { agentConfigurations: { edges: [{ node: noSlugAgent }] } },
            },
          },
        ]}
      />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });
    // Slug cell renders "-" when slug is null
    await expect(page.locator("code:has-text('-')")).toBeVisible();

    await component.unmount();
  });

  test("truncates long descriptions and renders '+N' badge for >3 tools", async ({
    mount,
    page,
  }) => {
    const longDescription = "x".repeat(150);
    const manyToolsAgent = {
      ...baseAgent,
      id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZTpkZXNjcmlwdGlvbg==",
      description: longDescription,
      availableTools: [
        "similarity_search",
        "load_document_text",
        "search_exact_text",
        "create_annotation",
        "web_fetch",
      ],
    };

    const component = await mount(
      <GlobalAgentManagementWrapper
        mocks={[
          {
            request: { query: GET_GLOBAL_AGENTS },
            result: {
              data: {
                agentConfigurations: { edges: [{ node: manyToolsAgent }] },
              },
            },
          },
        ]}
      />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    // Description gets a trailing "..." after the first 100 chars.
    await expect(page.locator("text=xxx...").first()).toBeVisible();

    // 5 tools total: only 3 rendered + a "+2" overflow badge.
    await expect(page.locator("text=+2")).toBeVisible();
    await expect(page.locator("text=similarity_search")).toBeVisible();
    await expect(page.locator("text=load_document_text")).toBeVisible();
    await expect(page.locator("text=search_exact_text")).toBeVisible();

    await component.unmount();
  });

  test("shows Inactive status badge when isActive=false", async ({
    mount,
    page,
  }) => {
    const inactiveAgent = { ...baseAgent, isActive: false };
    const component = await mount(
      <GlobalAgentManagementWrapper
        mocks={[
          {
            request: { query: GET_GLOBAL_AGENTS },
            result: {
              data: {
                agentConfigurations: { edges: [{ node: inactiveAgent }] },
              },
            },
          },
        ]}
      />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.locator("text=Inactive")).toBeVisible();

    await component.unmount();
  });
});

test.describe("GlobalAgentManagement — create flow", () => {
  test("disables the submit button until required fields are filled", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[emptyAgentsMock]} />
    );

    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button:has-text("Create Agent")').first().click();
    await expect(page.locator("text=Create Global Agent")).toBeVisible();

    const submit = page.locator(
      '.oc-modal-footer button:has-text("Create Agent")'
    );
    await expect(submit).toBeDisabled();

    // Fill partial — still disabled
    await page.locator("input[placeholder='Agent name']").fill("Test Agent");
    await expect(submit).toBeDisabled();

    await page
      .locator("textarea[placeholder^='Brief description']")
      .fill("A test description");
    await expect(submit).toBeDisabled();

    await page
      .locator("textarea[placeholder='System prompt for the agent...']")
      .fill("You are a test agent.");
    await expect(submit).toBeEnabled();

    await component.unmount();
  });

  test("shows a validation toast when badge config is invalid JSON", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper mocks={[emptyAgentsMock]} />
    );

    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button:has-text("Create Agent")').first().click();

    // Fill required fields
    await page.locator("input[placeholder='Agent name']").fill("Test Agent");
    await page
      .locator("textarea[placeholder^='Brief description']")
      .fill("Description");
    await page
      .locator("textarea[placeholder='System prompt for the agent...']")
      .fill("Instructions");

    // Corrupt the badge config to invalid JSON
    const badge = page.locator(
      "textarea[placeholder*='robot'][placeholder*='color']"
    );
    await badge.fill("not-json{{{");

    const submit = page.locator(
      '.oc-modal-footer button:has-text("Create Agent")'
    );
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page.locator("text=Invalid badge config JSON")).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });

  test("submits a create mutation, shows toast, and refetches the list", async ({
    mount,
    page,
  }) => {
    const createMock = {
      request: {
        query: CREATE_GLOBAL_AGENT_CONFIGURATION,
        variables: {
          name: "New Test Agent",
          description: "New description",
          systemInstructions: "Follow these rules.",
          availableTools: ["similarity_search", "load_document_text"],
          permissionRequiredTools: ["create_annotation"],
          badgeConfig: JSON.stringify({
            icon: "robot",
            color: "#6366f1",
            label: "AI",
          }),
          avatarUrl: "https://example.com/avatar.png",
          scope: "GLOBAL",
          isPublic: false,
        },
      },
      result: {
        data: {
          createAgentConfiguration: {
            ok: true,
            message: "Agent created",
            agent: {
              id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZToy",
              name: "New Test Agent",
              slug: "new-test-agent",
              description: "New description",
            },
          },
        },
      },
    };

    const afterCreateMock = {
      request: { query: GET_GLOBAL_AGENTS },
      result: {
        data: {
          agentConfigurations: {
            edges: [
              {
                node: {
                  ...baseAgent,
                  id: "QWdlbnRDb25maWd1cmF0aW9uVHlwZToy",
                  name: "New Test Agent",
                  slug: "new-test-agent",
                  description: "New description",
                },
              },
            ],
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper
        mocks={[emptyAgentsMock, createMock, afterCreateMock]}
      />
    );

    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button:has-text("Create Agent")').first().click();

    await page
      .locator("input[placeholder='Agent name']")
      .fill("New Test Agent");
    await page
      .locator("textarea[placeholder^='Brief description']")
      .fill("New description");
    await page
      .locator("textarea[placeholder='System prompt for the agent...']")
      .fill("Follow these rules.");
    await page
      .locator("input[placeholder*='similarity_search']")
      .fill(" similarity_search , load_document_text , ");
    await page
      .locator("input[placeholder*='require explicit permission']")
      .fill("create_annotation");
    await page
      .locator("input[placeholder='https://example.com/avatar.png']")
      .fill("https://example.com/avatar.png");

    // Uncheck "Publicly visible" to exercise the non-default branch
    const publicCheckbox = page.locator("input[type=checkbox]").first();
    await publicCheckbox.uncheck();

    const submit = page.locator(
      '.oc-modal-footer button:has-text("Create Agent")'
    );
    await expect(submit).toBeEnabled();
    await submit.click();

    await expect(page.locator("text=Agent created successfully")).toBeVisible({
      timeout: 5000,
    });

    // Modal should close and refetched list should display the new agent.
    await expect(page.locator("text=New Test Agent")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("shows server-side error toast when create mutation returns ok=false", async ({
    mount,
    page,
  }) => {
    const failingCreateMock = {
      request: {
        query: CREATE_GLOBAL_AGENT_CONFIGURATION,
        variables: {
          name: "Conflict Agent",
          description: "desc",
          systemInstructions: "instr",
          availableTools: null,
          permissionRequiredTools: null,
          badgeConfig: JSON.stringify({
            icon: "robot",
            color: "#6366f1",
            label: "AI",
          }),
          avatarUrl: null,
          scope: "GLOBAL",
          isPublic: true,
        },
      },
      result: {
        data: {
          createAgentConfiguration: {
            ok: false,
            message: "An agent with this name already exists",
            agent: null,
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper
        mocks={[emptyAgentsMock, failingCreateMock]}
      />
    );

    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button:has-text("Create Agent")').first().click();

    await page
      .locator("input[placeholder='Agent name']")
      .fill("Conflict Agent");
    await page
      .locator("textarea[placeholder^='Brief description']")
      .fill("desc");
    await page
      .locator("textarea[placeholder='System prompt for the agent...']")
      .fill("instr");

    await page
      .locator('.oc-modal-footer button:has-text("Create Agent")')
      .click();

    await expect(
      page.locator("text=An agent with this name already exists")
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });
});

test.describe("GlobalAgentManagement — edit flow", () => {
  test("pre-fills the edit form with the agent's existing values", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[singleAgentMock]} />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button[aria-label="Edit agent"]').first().click();

    await expect(
      page.locator("text=Edit Agent: Research Assistant")
    ).toBeVisible();

    // Name + description pre-filled
    await expect(page.locator("input[placeholder='Agent name']")).toHaveValue(
      "Research Assistant"
    );
    await expect(
      page.locator("textarea[placeholder^='Brief description']")
    ).toHaveValue(baseAgent.description);

    // availableTools joined by ", "
    await expect(
      page.locator("input[placeholder*='similarity_search']")
    ).toHaveValue(baseAgent.availableTools.join(", "));

    // Active + public checkboxes — both should be checked in the edit modal.
    const checkboxes = page.locator(".oc-modal-body input[type='checkbox']");
    await expect(checkboxes).toHaveCount(2);
    await expect(checkboxes.nth(0)).toBeChecked();
    await expect(checkboxes.nth(1)).toBeChecked();

    await component.unmount();
  });

  test("submits an update mutation and shows a success toast", async ({
    mount,
    page,
  }) => {
    const updatedAgent = {
      ...baseAgent,
      name: "Research Assistant v2",
      description: "Updated description",
    };

    const updateMock = {
      request: {
        query: UPDATE_GLOBAL_AGENT_CONFIGURATION,
        variables: {
          agentId: baseAgent.id,
          name: "Research Assistant v2",
          description: "Updated description",
          systemInstructions: baseAgent.systemInstructions,
          availableTools: ["similarity_search", "load_document_text"],
          permissionRequiredTools: [],
          badgeConfig: JSON.stringify(baseAgent.badgeConfig),
          avatarUrl: null,
          isActive: true,
          isPublic: true,
        },
      },
      result: {
        data: {
          updateAgentConfiguration: {
            ok: true,
            message: "Updated",
            agent: {
              id: baseAgent.id,
              name: "Research Assistant v2",
              slug: baseAgent.slug,
              description: "Updated description",
            },
          },
        },
      },
    };

    const afterUpdateMock = {
      request: { query: GET_GLOBAL_AGENTS },
      result: {
        data: { agentConfigurations: { edges: [{ node: updatedAgent }] } },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper
        mocks={[singleAgentMock, updateMock, afterUpdateMock]}
      />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button[aria-label="Edit agent"]').first().click();

    await page
      .locator("input[placeholder='Agent name']")
      .fill("Research Assistant v2");
    await page
      .locator("textarea[placeholder^='Brief description']")
      .fill("Updated description");

    await page
      .locator('.oc-modal-footer button:has-text("Save Changes")')
      .click();

    await expect(page.locator("text=Agent updated successfully")).toBeVisible({
      timeout: 5000,
    });

    // Refetched list should show the updated name
    await expect(
      page.locator("text=Research Assistant v2").first()
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("shows invalid JSON error when editing badge config to bad JSON", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper mocks={[singleAgentMock]} />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button[aria-label="Edit agent"]').first().click();

    const badge = page
      .locator(".oc-modal-body textarea[placeholder*='robot']")
      .first();
    await badge.fill("bad-json{{");

    await page
      .locator('.oc-modal-footer button:has-text("Save Changes")')
      .click();

    await expect(page.locator("text=Invalid badge config JSON")).toBeVisible({
      timeout: 3000,
    });

    await component.unmount();
  });
});

test.describe("GlobalAgentManagement — delete flow", () => {
  test("opens the delete confirmation modal with agent name and cancels", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <GlobalAgentManagementWrapper mocks={[singleAgentMock]} />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button[aria-label="Delete agent"]').first().click();

    // ConfirmModal message contains the agent name.
    await expect(
      page.locator(
        'text=Are you sure you want to delete the agent "Research Assistant"'
      )
    ).toBeVisible();

    // Click the "No"/Cancel option — agent should still be visible afterwards.
    await page
      .getByRole("button", { name: /no|cancel/i })
      .first()
      .click();

    await expect(page.locator("text=Research Assistant")).toBeVisible();

    await component.unmount();
  });

  test("confirming delete fires the mutation, shows toast, and refetches", async ({
    mount,
    page,
  }) => {
    const deleteMock = {
      request: {
        query: DELETE_GLOBAL_AGENT_CONFIGURATION,
        variables: { agentId: baseAgent.id },
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

    const afterDeleteMock = {
      request: { query: GET_GLOBAL_AGENTS },
      result: { data: { agentConfigurations: { edges: [] } } },
    };

    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper
        mocks={[singleAgentMock, deleteMock, afterDeleteMock]}
      />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button[aria-label="Delete agent"]').first().click();

    await expect(
      page.locator("text=Are you sure you want to delete")
    ).toBeVisible();

    // ConfirmModal exposes "Yes" as the confirmation button.
    await page.getByRole("button", { name: /yes/i }).first().click();

    await expect(page.locator("text=Agent deleted successfully")).toBeVisible({
      timeout: 5000,
    });

    // The empty-state message returns after the refetch.
    await expect(page.locator("text=No Global Agents")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });

  test("shows server-side error toast when delete mutation returns ok=false", async ({
    mount,
    page,
  }) => {
    const failingDeleteMock = {
      request: {
        query: DELETE_GLOBAL_AGENT_CONFIGURATION,
        variables: { agentId: baseAgent.id },
      },
      result: {
        data: {
          deleteAgentConfiguration: {
            ok: false,
            message: "Agent is in use",
          },
        },
      },
    };

    const component = await mount(
      <GlobalAgentManagementWithToastsWrapper
        mocks={[singleAgentMock, failingDeleteMock]}
      />
    );

    await expect(page.locator("text=Research Assistant")).toBeVisible({
      timeout: 5000,
    });

    await page.locator('button[aria-label="Delete agent"]').first().click();
    await page.getByRole("button", { name: /yes/i }).first().click();

    await expect(page.locator("text=Agent is in use")).toBeVisible({
      timeout: 5000,
    });

    await component.unmount();
  });
});
