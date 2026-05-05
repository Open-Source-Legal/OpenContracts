// Playwright Component Test for ChatMessage in-flight signal.
//
// Originally these tests covered the "Agent is thinking..." pill
// (`data-testid="processing-indicator"`) added in #687. That pill was
// replaced by the inline `StreamingThoughtTicker` (icon + latest-step
// title + breathing dot) so the in-flight cue lives on the assistant's
// own message bubble instead of as a separate banner. The tests below
// pin the new contract: ticker visible while assistant streams (with or
// without timeline entries), gone once the message is complete, never
// rendered for user messages, and the old pill is gone.
import React from "react";
import { test, expect } from "./utils/coverage";
import { ChatMessage } from "../src/components/widgets/chat/ChatMessage";
import { ChatMessageTestWrapper } from "./ChatMessageTestWrapper";

const baseAssistantMessage = {
  user: "Assistant",
  timestamp: new Date().toLocaleString(),
  isAssistant: true,
};

const baseUserMessage = {
  user: "testuser@example.com",
  timestamp: new Date().toLocaleString(),
  isAssistant: false,
};

test.describe("ChatMessage in-flight ticker", () => {
  test("shows streaming ticker when assistant message is incomplete with no content and no timeline", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content=""
          isComplete={false}
          timeline={[]}
        />
      </ChatMessageTestWrapper>
    );

    const ticker = page.locator('[data-testid="streaming-thought-ticker"]');
    await expect(ticker).toBeVisible({ timeout: 3000 });

    // Generic "Thinking" placeholder text shows when no timeline entry has
    // arrived yet — replaces the old "Agent is thinking..." pill copy.
    await expect(ticker.locator("text=Thinking")).toBeVisible();

    // Message content bubble should NOT be visible mid-stream.
    await expect(
      page.locator('[data-testid="message-content"]')
    ).not.toBeVisible();

    // The legacy pill is gone.
    await expect(
      page.locator('[data-testid="processing-indicator"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("hides ticker when content arrives", async ({ mount, page }) => {
    const component = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content=""
          isComplete={false}
          timeline={[]}
        />
      </ChatMessageTestWrapper>
    );

    await expect(
      page.locator('[data-testid="streaming-thought-ticker"]')
    ).toBeVisible({ timeout: 3000 });

    await component.unmount();

    // Re-mount with non-empty content (simulating ASYNC_CONTENT having
    // arrived). The ticker drops out and the bubble takes over.
    const componentWithContent = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Hello, I can help you with that."
          isComplete={false}
          timeline={[]}
        />
      </ChatMessageTestWrapper>
    );

    await expect(
      page.locator('[data-testid="streaming-thought-ticker"]')
    ).not.toBeVisible();
    await expect(
      page.locator("text=Hello, I can help you with that.")
    ).toBeVisible();

    await componentWithContent.unmount();
  });

  test("ticker shows latest timeline entry title when timeline arrives first", async ({
    mount,
    page,
  }) => {
    const timelineEntries = [
      {
        type: "thought" as const,
        text: "Analyzing the user request",
      },
    ];

    const component = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content=""
          isComplete={false}
          timeline={timelineEntries}
          hasTimeline={true}
        />
      </ChatMessageTestWrapper>
    );

    const ticker = page.locator('[data-testid="streaming-thought-ticker"]');
    await expect(ticker).toBeVisible({ timeout: 3000 });

    // Latest entry's title (resolved by getTimelineTitle) is rendered.
    await expect(ticker.locator("text=Thinking")).toBeVisible();

    // The bordered timeline panel must NOT render mid-stream.
    await expect(
      page.locator('[data-testid="timeline-container"]')
    ).not.toBeVisible();

    // Legacy pill is gone.
    await expect(
      page.locator('[data-testid="processing-indicator"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("does NOT show ticker for user messages", async ({ mount, page }) => {
    const component = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseUserMessage}
          content=""
          isComplete={false}
          timeline={[]}
        />
      </ChatMessageTestWrapper>
    );

    await expect(
      page.locator('[data-testid="streaming-thought-ticker"]')
    ).not.toBeVisible();
    // And the legacy pill stays absent for user messages too.
    await expect(
      page.locator('[data-testid="processing-indicator"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("does NOT show ticker when message is complete", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <ChatMessageTestWrapper>
        <ChatMessage
          {...baseAssistantMessage}
          content="Here is my response."
          isComplete={true}
          timeline={[]}
        />
      </ChatMessageTestWrapper>
    );

    await expect(
      page.locator('[data-testid="streaming-thought-ticker"]')
    ).not.toBeVisible();
    await expect(page.locator("text=Here is my response.")).toBeVisible();

    await component.unmount();
  });
});
