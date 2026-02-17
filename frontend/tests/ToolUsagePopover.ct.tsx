// Playwright Component Test for ChatMessage Tool Usage Popover
// Tests the ToolUsageIndicator component and captures documentation screenshots.
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { ChatMessage } from "../src/components/widgets/chat/ChatMessage";
import { ChatMessageTestWrapper } from "./ChatMessageTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

// Realistic timeline with a single tool call + result
const singleToolTimeline = [
  { type: "thought" as const, text: "Analyzing user request about payments" },
  {
    type: "tool_call" as const,
    tool: "similarity_search",
    args: { query: "payment terms", limit: 10 },
  },
  {
    type: "tool_result" as const,
    tool: "similarity_search",
    result: "Found 3 matching annotations",
  },
  { type: "content" as const, text: "Based on the document analysis..." },
];

// Realistic timeline with multiple different tool calls
const multiToolTimeline = [
  { type: "thought" as const, text: "Breaking down the query" },
  {
    type: "tool_call" as const,
    tool: "similarity_search",
    args: { query: "indemnification clause", limit: 5 },
  },
  {
    type: "tool_result" as const,
    tool: "similarity_search",
    result: "Found 5 matching annotations",
  },
  {
    type: "tool_call" as const,
    tool: "search_exact_text",
    args: { query: "shall indemnify and hold harmless" },
  },
  {
    type: "tool_result" as const,
    tool: "search_exact_text",
    result: "Found 2 exact text matches",
  },
  {
    type: "tool_call" as const,
    tool: "ask_document",
    args: { question: "What are the indemnification obligations?" },
  },
  {
    type: "tool_result" as const,
    tool: "ask_document",
    result:
      "The agreement requires mutual indemnification for third-party claims arising from breach of representations.",
  },
  { type: "content" as const, text: "Here is my analysis..." },
];

// Timeline with tool calls but no results yet (streaming state)
const pendingToolTimeline = [
  { type: "thought" as const, text: "Searching the document" },
  {
    type: "tool_call" as const,
    tool: "similarity_search",
    args: { query: "termination provisions" },
  },
];

const baseAssistantMessage = {
  user: "Assistant",
  timestamp: new Date().toLocaleString(),
  isAssistant: true,
};

test.describe("Tool Usage Popover", () => {
  test("should show tool badge when timeline has tool calls", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Based on the document analysis, the payment terms require net-30 settlement."
          isComplete={true}
          timeline={singleToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    // The tool badge should be visible
    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });
    await expect(badge).toContainText("1 tool used");
  });

  test("should show correct count for multiple tools", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Here is my analysis of the indemnification clauses."
          isComplete={true}
          timeline={multiToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });
    await expect(badge).toContainText("3 tools used");
  });

  test("should not show tool badge for user messages", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          user="testuser@example.com"
          timestamp={new Date().toLocaleString()}
          isAssistant={false}
          content="What are the payment terms?"
          isComplete={true}
          timeline={[]}
        />
      </ChatMessageTestWrapper>
    );

    // No tool badge should appear for user messages
    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).not.toBeVisible();
  });

  test("should not show tool badge when timeline has no tool calls", async ({
    mount,
    page,
  }) => {
    const noToolTimeline = [
      { type: "thought" as const, text: "Thinking about the answer" },
      { type: "content" as const, text: "Here is my response" },
      { type: "status" as const, msg: "run_finished" },
    ];

    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="I can answer that directly."
          isComplete={true}
          timeline={noToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).not.toBeVisible();
  });

  test("should open popover on hover and show tool details", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Based on the document analysis, the payment terms require net-30 settlement."
          isComplete={true}
          timeline={singleToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Hover to open popover
    await badge.hover();

    // Popover dialog should appear
    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });

    // Should show the tool name in title case
    await expect(popover).toContainText("Similarity Search");

    // Should show input args
    await expect(popover).toContainText("payment terms");

    // Should show result
    await expect(popover).toContainText("Found 3 matching annotations");
  });

  test("should open popover via keyboard (Enter key)", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="The payment terms are net-30."
          isComplete={true}
          timeline={singleToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Focus and press Enter
    await badge.focus();
    await page.keyboard.press("Enter");

    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });
    await expect(popover).toContainText("Similarity Search");
  });

  test("should close popover via Escape key", async ({ mount, page }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="The payment terms are net-30."
          isComplete={true}
          timeline={singleToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Open via keyboard
    await badge.focus();
    await page.keyboard.press("Enter");

    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });

    // Press Escape to close
    await page.keyboard.press("Escape");
    await expect(popover).not.toBeVisible({ timeout: 3000 });
  });

  test("should have correct ARIA attributes on badge", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Result of analysis."
          isComplete={true}
          timeline={singleToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Badge should have proper ARIA attributes when closed
    await expect(badge).toHaveAttribute("aria-expanded", "false");
    await expect(badge).toHaveAttribute("aria-haspopup", "dialog");

    // Open and verify expanded state
    await badge.hover();
    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });
    await expect(badge).toHaveAttribute("aria-expanded", "true");
  });

  test("should display multiple tool calls in popover with all details", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Here is my analysis of the indemnification clauses."
          isComplete={true}
          timeline={multiToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Hover to open
    await badge.hover();

    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });

    // Should show header with correct count
    await expect(popover).toContainText("Tool Usage (3 calls)");

    // All three tool names should be visible
    await expect(popover).toContainText("Similarity Search");
    await expect(popover).toContainText("Search Exact Text");
    await expect(popover).toContainText("Ask Document");

    // Results should be visible
    await expect(popover).toContainText("Found 5 matching annotations");
    await expect(popover).toContainText("Found 2 exact text matches");
    await expect(popover).toContainText("mutual indemnification");
  });

  test("should handle tool call with no result yet (pending)", async ({
    mount,
    page,
  }) => {
    await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content=""
          isComplete={false}
          timeline={pendingToolTimeline}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });
    await expect(badge).toContainText("1 tool used");

    // Open popover
    await badge.hover();
    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });

    // Tool name and args should show, but no output section
    await expect(popover).toContainText("Similarity Search");
    await expect(popover).toContainText("termination provisions");

    // The "Output" label should not be present since there's no result
    const outputLabels = popover.locator("text=Output");
    await expect(outputLabels).toHaveCount(0);
  });

  // --- Documentation Screenshots ---
  //
  // ChatMessage uses framer-motion entrance animation (opacity 0→1, 300ms)
  // and has transparent backgrounds designed for the chat panel's #f8fafc bg.
  // We provide that background and wait for the animation to settle.

  test("screenshot: single tool badge (collapsed)", async ({ mount, page }) => {
    await page.setViewportSize({ width: 1536, height: 864 });

    const component = await mount(
      <ChatMessageTestWrapper>
        <div style={{ background: "#f8fafc", padding: "1rem" }}>
          <ChatMessage
            {...baseAssistantMessage}
            content="Based on the document analysis, the payment terms require net-30 settlement with standard penalty clauses."
            isComplete={true}
            timeline={singleToolTimeline}
            hasTimeline={true}
          />
        </div>
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Wait for framer-motion entrance animation to complete
    await page.waitForTimeout(500);

    await docScreenshot(page, "chat--tool-badge--single", {
      element: component,
    });
  });

  test("screenshot: single tool popover open", async ({ mount, page }) => {
    // Widen viewport and add left padding so the right-aligned popover
    // (min-width 320px) doesn't extend past the left viewport edge.
    await page.setViewportSize({ width: 1440, height: 720 });

    await mount(
      <ChatMessageTestWrapper>
        <div
          style={{
            background: "#f8fafc",
            padding: "1rem",
            paddingLeft: "360px",
          }}
        >
          <ChatMessage
            {...baseAssistantMessage}
            content="Based on the document analysis, the payment terms require net-30 settlement with standard penalty clauses."
            isComplete={true}
            timeline={singleToolTimeline}
            hasTimeline={true}
          />
        </div>
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Wait for framer-motion entrance animation to complete
    await page.waitForTimeout(500);

    // Open the popover
    await badge.hover();
    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });

    // Capture the popover element directly for a clean, focused screenshot
    await docScreenshot(page, "chat--tool-popover--single-tool", {
      element: popover,
    });
  });

  test("screenshot: multi-tool popover open", async ({ mount, page }) => {
    // Widen viewport and add left padding so the right-aligned popover
    // (min-width 320px) doesn't extend past the left viewport edge.
    await page.setViewportSize({ width: 1440, height: 960 });

    await mount(
      <ChatMessageTestWrapper>
        <div
          style={{
            background: "#f8fafc",
            padding: "1rem",
            paddingLeft: "360px",
          }}
        >
          <ChatMessage
            {...baseAssistantMessage}
            content="Here is my analysis of the indemnification clauses in this agreement."
            isComplete={true}
            timeline={multiToolTimeline}
            hasTimeline={true}
          />
        </div>
      </ChatMessageTestWrapper>
    );

    const badge = page.locator("role=button[name=/tool/i]");
    await expect(badge).toBeVisible({ timeout: 5000 });

    // Wait for framer-motion entrance animation to complete
    await page.waitForTimeout(500);

    // Open the popover
    await badge.hover();
    const popover = page.locator("role=dialog[name=/tool usage/i]");
    await expect(popover).toBeVisible({ timeout: 3000 });

    // Capture the popover element directly for a clean, focused screenshot
    await docScreenshot(page, "chat--tool-popover--multi-tool", {
      element: popover,
    });
  });
});
