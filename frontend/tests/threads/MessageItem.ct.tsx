/**
 * Component tests for MessageItem
 *
 * Tests the agent message styling and accessibility features
 * introduced in Issue #688.
 */
import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MessageItem } from "../../src/components/threads/MessageItem";
import { ThreadTestWrapper } from "./utils/ThreadTestWrapper";
import { createMockMessage } from "./utils/mockThreadData";
import { docScreenshot, releaseScreenshot } from "../utils/docScreenshot";
import type { MessageNode } from "../../src/components/threads/utils";
import type { AgentConfigurationType } from "../../src/types/graphql-api";

/**
 * Creates a MessageNode from a ChatMessageType for testing
 */
function createMockMessageNode(overrides?: Partial<MessageNode>): MessageNode {
  const baseMessage = createMockMessage();
  return {
    ...baseMessage,
    children: [],
    depth: 0,
    ...overrides,
  };
}

/**
 * Creates a mock agent configuration for testing
 */
function createMockAgentConfig(
  overrides?: Partial<AgentConfigurationType>
): AgentConfigurationType {
  return {
    id: "agent-1",
    name: "Test AI Agent",
    description: "A test agent for automated responses",
    systemInstructions: "You are a helpful assistant",
    scope: "CORPUS",
    isActive: true,
    created: new Date().toISOString(),
    modified: new Date().toISOString(),
    badgeConfig: { color: "#10B981", icon: "Bot" },
    creator: {
      id: "user-1",
      username: "system",
      email: "system@example.com",
      slug: "system",
      name: "System",
      isUsageCapped: false,
    },
    ...overrides,
  };
}

test.describe("MessageItem - Agent Messages", () => {
  test("renders agent message with correct content", async ({
    mount,
    page,
  }) => {
    const agentConfig = createMockAgentConfig();
    const message = createMockMessageNode({
      id: "agent-msg-1",
      content: "Hello, I am an AI assistant. How can I help you today?",
      agentConfiguration: agentConfig,
      msgType: "AGENT",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    // Check message content is visible
    await expect(
      component.getByText("Hello, I am an AI assistant.")
    ).toBeVisible({ timeout: 5000 });

    await docScreenshot(page, "threads--agent-message--response", {
      element: component,
    });
    await releaseScreenshot(page, "v3.0.0.b3", "agent-response", {
      element: component,
    });
  });

  test("agent avatar displays Bot icon with proper title", async ({
    mount,
  }) => {
    const agentConfig = createMockAgentConfig();
    const message = createMockMessageNode({
      id: "agent-msg-2",
      content: "Agent response",
      agentConfiguration: agentConfig,
      msgType: "AGENT",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    // Bot icon should be present (lucide-react Bot icon is an SVG)
    const avatar = component.locator('[title="Test AI Agent (AI Agent)"]');
    await expect(avatar).toBeVisible({ timeout: 5000 });

    // Should have an SVG icon inside the avatar
    const svg = avatar.locator("svg");
    await expect(svg).toBeVisible({ timeout: 2000 });
  });

  test("agent message renders with custom badge color", async ({ mount }) => {
    const agentConfig = createMockAgentConfig({
      name: "Custom Agent",
      badgeConfig: { color: "#FF5733" },
    });
    const message = createMockMessageNode({
      id: "agent-msg-4",
      content: "Custom colored message",
      agentConfiguration: agentConfig,
      msgType: "AGENT",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    // Content should be visible
    await expect(component.getByText("Custom colored message")).toBeVisible({
      timeout: 5000,
    });

    // Avatar with agent title should be visible
    const avatar = component.locator('[title="Custom Agent (AI Agent)"]');
    await expect(avatar).toBeVisible({ timeout: 5000 });
  });

  test("agent message renders with null badgeConfig", async ({ mount }) => {
    const agentConfig = createMockAgentConfig({
      name: "Default Agent",
      badgeConfig: null,
    });
    const message = createMockMessageNode({
      id: "agent-msg-5",
      content: "Default styled message",
      agentConfiguration: agentConfig,
      msgType: "AGENT",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    await expect(component.getByText("Default styled message")).toBeVisible({
      timeout: 5000,
    });

    // Agent should still show proper title
    const avatar = component.locator('[title="Default Agent (AI Agent)"]');
    await expect(avatar).toBeVisible({ timeout: 5000 });
  });

  test("agent message renders with invalid color in badgeConfig", async ({
    mount,
  }) => {
    const agentConfig = createMockAgentConfig({
      name: "Invalid Color Agent",
      badgeConfig: { color: "not-a-valid-color" },
    });
    const message = createMockMessageNode({
      id: "agent-msg-6",
      content: "Message with invalid color",
      agentConfiguration: agentConfig,
      msgType: "AGENT",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    await expect(component.getByText("Message with invalid color")).toBeVisible(
      { timeout: 5000 }
    );
  });
});

test.describe("MessageItem - Human Messages", () => {
  test("renders human message without agent styling", async ({ mount }) => {
    const message = createMockMessageNode({
      id: "human-msg-1",
      content: "This is a message from a human user.",
      agentConfiguration: null,
      msgType: "HUMAN",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    await expect(
      component.getByText("This is a message from a human user.")
    ).toBeVisible({ timeout: 5000 });
  });

  test("human message displays User icon with username title", async ({
    mount,
  }) => {
    const message = createMockMessageNode({
      id: "human-msg-3",
      content: "User message",
      agentConfiguration: null,
      msgType: "HUMAN",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    // Avatar should be titled with the username (no AI Agent suffix)
    const avatar = component.locator('[title="testuser"]');
    await expect(avatar).toBeVisible({ timeout: 5000 });
  });
});

test.describe("MessageItem - Reply Functionality", () => {
  test("reply button is visible and clickable", async ({ mount }) => {
    const message = createMockMessageNode({
      id: "msg-reply-test",
      content: "Message with reply button",
    });

    let replyClicked = false;
    const handleReply = () => {
      replyClicked = true;
    };

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} onReply={handleReply} />
      </ThreadTestWrapper>
    );

    const replyButton = component.getByRole("button", { name: /reply/i });
    await expect(replyButton).toBeVisible({ timeout: 5000 });

    await replyButton.click();
    expect(replyClicked).toBe(true);
  });
});

test.describe("MessageItem - Highlighted State", () => {
  test("highlighted message renders content correctly", async ({ mount }) => {
    const message = createMockMessageNode({
      id: "highlighted-msg",
      content: "This message is highlighted",
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} isHighlighted={true} />
      </ThreadTestWrapper>
    );

    await expect(
      component.getByText("This message is highlighted")
    ).toBeVisible({ timeout: 5000 });
  });
});

test.describe("MessageItem - Deleted Messages", () => {
  test("deleted message shows placeholder text", async ({ mount }) => {
    const message = createMockMessageNode({
      id: "deleted-msg",
      content: "Original content that should not be shown",
      deletedAt: new Date().toISOString(),
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    await expect(
      component.getByText("[This message has been deleted]")
    ).toBeVisible({ timeout: 5000 });

    // Original content should NOT be visible
    await expect(
      component.getByText("Original content that should not be shown")
    ).not.toBeVisible();
  });

  test("deleted message does not show reply button", async ({ mount }) => {
    const message = createMockMessageNode({
      id: "deleted-msg-2",
      content: "Deleted message",
      deletedAt: new Date().toISOString(),
    });

    const component = await mount(
      <ThreadTestWrapper>
        <MessageItem message={message} />
      </ThreadTestWrapper>
    );

    // Reply button should not be visible for deleted messages
    const replyButton = component.getByRole("button", { name: /reply/i });
    await expect(replyButton).not.toBeVisible();
  });
});
