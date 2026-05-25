import React from "react";
import { test, expect } from "./utils/coverage";
import {
  ApprovalDialog,
  PendingApproval,
} from "../src/components/chat/ApprovalDialog";
import { docScreenshot } from "./utils/docScreenshot";

const sampleApproval: PendingApproval = {
  messageId: "msg-123",
  toolCall: {
    name: "search_documents",
    arguments: { query: "contract terms", limit: 10 },
    tool_call_id: "tc-456",
  },
};

test.describe("ApprovalDialog", () => {
  test("renders with pending approval data", async ({ mount, page }) => {
    const component = await mount(
      <ApprovalDialog
        pendingApproval={sampleApproval}
        onHide={() => {}}
        onDecision={() => {}}
      />
    );

    await expect(page.getByText("Tool Approval Required")).toBeVisible({
      timeout: 5000,
    });
    await expect(
      page.getByText("The assistant wants to execute the following tool:")
    ).toBeVisible();
    await expect(page.getByText("Tool: search_documents")).toBeVisible();
    await expect(page.getByText("Arguments:")).toBeVisible();

    // Check action buttons
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();

    // Modal exposes dialog semantics for screen readers
    await expect(page.getByRole("dialog")).toBeVisible();

    await docScreenshot(page, "chat--approval-modal--pending");

    await component.unmount();
  });

  test("calls onHide when the close button is clicked", async ({
    mount,
    page,
  }) => {
    let hidden = false;

    const component = await mount(
      <ApprovalDialog
        pendingApproval={sampleApproval}
        onHide={() => {
          hidden = true;
        }}
        onDecision={() => {}}
      />
    );

    const closeBtn = page.getByRole("button", { name: "Close approval modal" });
    await expect(closeBtn).toBeVisible({ timeout: 5000 });
    await closeBtn.click();

    expect(hidden).toBe(true);

    await component.unmount();
  });

  test("calls onDecision with true when Approve is clicked", async ({
    mount,
    page,
  }) => {
    let decision: boolean | null = null;

    const component = await mount(
      <ApprovalDialog
        pendingApproval={sampleApproval}
        onHide={() => {}}
        onDecision={(approved) => {
          decision = approved;
        }}
      />
    );

    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "Approve" }).click();

    expect(decision).toBe(true);

    await component.unmount();
  });

  test("calls onDecision with false when Reject is clicked", async ({
    mount,
    page,
  }) => {
    let decision: boolean | null = null;

    const component = await mount(
      <ApprovalDialog
        pendingApproval={sampleApproval}
        onHide={() => {}}
        onDecision={(approved) => {
          decision = approved;
        }}
      />
    );

    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible({
      timeout: 5000,
    });
    await page.getByRole("button", { name: "Reject" }).click();

    expect(decision).toBe(false);

    await component.unmount();
  });

  test("calls onHide when Escape key is pressed", async ({ mount, page }) => {
    let hidden = false;

    const component = await mount(
      <ApprovalDialog
        pendingApproval={sampleApproval}
        onHide={() => {
          hidden = true;
        }}
        onDecision={() => {}}
      />
    );

    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5000 });
    await page.keyboard.press("Escape");

    expect(hidden).toBe(true);

    await component.unmount();
  });

  test("displays tool arguments as JSON", async ({ mount, page }) => {
    const component = await mount(
      <ApprovalDialog
        pendingApproval={sampleApproval}
        onHide={() => {}}
        onDecision={() => {}}
      />
    );

    // The arguments should be displayed as formatted JSON
    await expect(page.getByText('"contract terms"')).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("10")).toBeVisible();

    await component.unmount();
  });

  test("constrains modal height and scrolls body when args are very long", async ({
    mount,
    page,
  }) => {
    // Build a tool call whose arguments produce a multi-thousand-char JSON
    // payload — the bug was that the modal grew unbounded and pushed the
    // Approve/Reject buttons off-screen.
    const longText = "Lorem ipsum dolor sit amet ".repeat(400);
    const longArgsApproval: PendingApproval = {
      messageId: "msg-long",
      toolCall: {
        name: "update_corpus_description",
        arguments: { new_content: longText },
        tool_call_id: "tc-long",
      },
    };

    const component = await mount(
      <ApprovalDialog
        pendingApproval={longArgsApproval}
        onHide={() => {}}
        onDecision={() => {}}
      />
    );

    const approveBtn = page.getByRole("button", { name: "Approve" });
    const rejectBtn = page.getByRole("button", { name: "Reject" });
    await expect(approveBtn).toBeVisible({ timeout: 5000 });
    await expect(rejectBtn).toBeVisible();

    // Both action buttons must remain inside the viewport regardless of how
    // much JSON the tool call carries.
    const viewport = page.viewportSize();
    const approveBox = await approveBtn.boundingBox();
    const rejectBox = await rejectBtn.boundingBox();
    expect(viewport).not.toBeNull();
    expect(approveBox).not.toBeNull();
    expect(rejectBox).not.toBeNull();
    if (viewport && approveBox && rejectBox) {
      expect(approveBox.y + approveBox.height).toBeLessThanOrEqual(
        viewport.height
      );
      expect(approveBox.y).toBeGreaterThanOrEqual(0);
      expect(rejectBox.y + rejectBox.height).toBeLessThanOrEqual(
        viewport.height
      );
      expect(rejectBox.y).toBeGreaterThanOrEqual(0);
    }

    await component.unmount();
  });
});
