import React from "react";
import { test, expect } from "./utils/coverage";
import { MockedProvider } from "@apollo/client/testing";
import { CorpusActionsSection } from "../src/components/corpuses/settings/CorpusActionsSection";
import { docScreenshot } from "./utils/docScreenshot";

const mockActions = [
  {
    id: "action-1",
    name: "Auto-Summarize Documents",
    trigger: "add_document",
    disabled: false,
    runOnAllCorpuses: false,
    agentConfig: {
      id: "agent-1",
      name: "Document Summarizer",
      description: "Summarizes documents on upload",
    },
    taskInstructions:
      "Read the document and create a concise summary highlighting key points, parties, and important dates.",
    preAuthorizedTools: ["load_document_text", "update_document_summary"],
    creator: { username: "admin" },
    created: "2026-01-15T10:00:00Z",
  },
  {
    id: "action-2",
    name: "Extract Contract Terms",
    trigger: "add_document",
    disabled: false,
    runOnAllCorpuses: false,
    fieldset: { id: "fs-1", name: "Contract Terms Fieldset" },
    creator: { username: "admin" },
    created: "2026-01-20T14:30:00Z",
  },
  {
    id: "action-3",
    name: "Thread Moderator",
    trigger: "new_thread",
    disabled: true,
    runOnAllCorpuses: false,
    agentConfig: {
      id: "agent-2",
      name: "Content Moderator",
      description: "Moderates discussion threads",
    },
    taskInstructions:
      "Review new threads for policy compliance. Use moderation tools as needed.",
    preAuthorizedTools: [
      "get_thread_context",
      "get_thread_messages",
      "delete_message",
      "lock_thread",
    ],
    creator: { username: "moderator" },
    created: "2026-02-01T09:15:00Z",
  },
];

test.describe("CorpusActionsSection - List View", () => {
  test("should display action cards with details", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <CorpusActionsSection
          actions={mockActions}
          onAddAction={() => {}}
          onEditAction={() => {}}
          onDeleteAction={() => {}}
        />
      </MockedProvider>
    );

    // Verify all actions are displayed
    await expect(page.locator("text=Auto-Summarize Documents")).toBeVisible();
    await expect(page.locator("text=Extract Contract Terms")).toBeVisible();
    await expect(page.locator("text=Thread Moderator")).toBeVisible();

    // Verify action type info
    await expect(page.locator("text=Agent: Document Summarizer")).toBeVisible();
    await expect(
      page.locator("text=Fieldset: Contract Terms Fieldset")
    ).toBeVisible();

    // Verify status badges
    await expect(page.locator("text=Disabled")).toBeVisible();

    await docScreenshot(page, "corpus-actions--list-view--with-actions", {
      fullPage: true,
    });

    await component.unmount();
  });

  test("shows the Layers batch-run button only for enabled agent actions when the viewer has UPDATE", async ({
    mount,
    page,
  }) => {
    let batchRunCalls = 0;
    let lastBatchRunActionId: string | undefined;

    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <CorpusActionsSection
          actions={mockActions}
          canUpdate={true}
          onAddAction={() => {}}
          onEditAction={() => {}}
          onDeleteAction={() => {}}
          onBatchRunAction={(action) => {
            batchRunCalls += 1;
            lastBatchRunActionId = action.id;
          }}
        />
      </MockedProvider>
    );

    // Three actions total: action-1 (agent, enabled), action-2 (fieldset),
    // action-3 (agent, disabled). Only action-1 should get a Layers button.
    const layersButtons = page.locator(
      'button[aria-label="Run this agent action on every document in the corpus"]'
    );
    await expect(layersButtons).toHaveCount(1);

    await layersButtons.first().click();
    expect(batchRunCalls).toBe(1);
    expect(lastBatchRunActionId).toBe("action-1");

    await docScreenshot(
      page,
      "corpus-actions--list-view--layers-button-visible",
      { fullPage: true }
    );

    await component.unmount();
  });

  test("hides the Layers batch-run button when the viewer cannot UPDATE the corpus", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <CorpusActionsSection
          actions={mockActions}
          canUpdate={false}
          onAddAction={() => {}}
          onEditAction={() => {}}
          onDeleteAction={() => {}}
          onBatchRunAction={() => {}}
        />
      </MockedProvider>
    );

    await expect(
      page.locator(
        'button[aria-label="Run this agent action on every document in the corpus"]'
      )
    ).toHaveCount(0);

    await component.unmount();
  });
});
