import React from "react";
import { test, expect } from "@playwright/experimental-ct-react";
import { MessageComposer } from "../src/components/threads/MessageComposer";

test.describe("MessageComposer", () => {
  test("renders with placeholder", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write something..."
        onSubmit={async () => {}}
      />
    );

    await expect(page.locator(".ProseMirror")).toBeVisible();
    // Check that the editor has the is-editor-empty class (TipTap adds this)
    await expect(page.locator(".ProseMirror p.is-editor-empty")).toBeVisible();
  });

  test("accepts text input", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
      />
    );

    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Hello, this is a test message!");

    await expect(editor).toContainText("Hello, this is a test message!");
  });

  test("shows character count", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
        maxLength={100}
      />
    );

    // Type content into the editor to trigger character count update
    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Test message");

    // Wait for character count to update
    await page.waitForTimeout(100);

    // Should show character count (12 chars in "Test message")
    await expect(page.getByText(/12 \/ 100/)).toBeVisible();
  });

  test("disables send button when empty", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
      />
    );

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeDisabled();
  });

  test("enables send button when text is entered", async ({ mount, page }) => {
    // Mount with initialContent to properly set TipTap's internal state
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
        initialContent="<p>Hello!</p>"
      />
    );

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeEnabled();
  });

  test("calls onSubmit when send button clicked", async ({ mount, page }) => {
    let submittedContent = "";

    // Mount with initialContent to properly set TipTap's internal state
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async (content) => {
          submittedContent = content;
        }}
        initialContent="<p>Test submission</p>"
      />
    );

    const sendButton = page.getByRole("button", { name: /send/i });
    await sendButton.click();

    // Wait a bit for async handling
    await page.waitForTimeout(100);

    expect(submittedContent).toContain("Test submission");
  });

  test("applies bold formatting", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
      />
    );

    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Bold text");

    // Select all text
    await page.keyboard.press("Control+A");

    // Click bold button
    const boldButton = page.getByTitle("Bold (Cmd+B)");
    await boldButton.click();

    // Check for bold tag
    await expect(editor.locator("strong")).toContainText("Bold text");
  });

  test("applies italic formatting", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
      />
    );

    const editor = page.locator(".ProseMirror");
    await editor.click();
    await editor.fill("Italic text");

    // Select all text
    await page.keyboard.press("Control+A");

    // Click italic button
    const italicButton = page.getByTitle("Italic (Cmd+I)");
    await italicButton.click();

    // Check for italic tag
    await expect(editor.locator("em")).toContainText("Italic text");
  });

  test("creates bullet list", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
      />
    );

    const editor = page.locator(".ProseMirror");
    await editor.click();

    // Click bullet list button
    const bulletButton = page.getByTitle("Bullet List");
    await bulletButton.click();

    // Type list items
    await editor.fill("Item 1");

    // Check for bullet list
    await expect(editor.locator("ul")).toBeVisible();
    await expect(editor.locator("li")).toContainText("Item 1");
  });

  test("creates numbered list", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
      />
    );

    const editor = page.locator(".ProseMirror");
    await editor.click();

    // Click numbered list button
    const numberedButton = page.getByTitle("Numbered List");
    await numberedButton.click();

    // Type list items
    await editor.fill("Item 1");

    // Check for numbered list
    await expect(editor.locator("ol")).toBeVisible();
    await expect(editor.locator("li")).toContainText("Item 1");
  });

  test("shows error message", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
        error="Something went wrong!"
      />
    );

    await expect(page.getByText("Something went wrong!")).toBeVisible();
  });

  test("disables composer when disabled prop is true", async ({
    mount,
    page,
  }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
        disabled={true}
      />
    );

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeDisabled();

    const boldButton = page.getByTitle("Bold (Cmd+B)");
    await expect(boldButton).toBeDisabled();
  });

  test("shows over-limit warning", async ({ mount, page }) => {
    // Mount with initialContent exceeding maxLength
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
        maxLength={10}
        initialContent="<p>This is definitely more than ten characters</p>"
      />
    );

    await expect(page.getByText(/too long/)).toBeVisible();

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeDisabled();
  });

  test("clears content after successful submit", async ({ mount, page }) => {
    // Mount with initialContent to properly set TipTap's internal state
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {
          // Simulate successful submit
        }}
        initialContent="<p>Test message</p>"
      />
    );

    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    // Wait for async handling and editor to clear
    await page.waitForTimeout(200);

    // Editor should be cleared (placeholder class should be back)
    await expect(page.locator(".ProseMirror p.is-editor-empty")).toBeVisible();
  });

  test("auto-focuses when autoFocus prop is true", async ({ mount, page }) => {
    await mount(
      <MessageComposer
        placeholder="Write your message..."
        onSubmit={async () => {}}
        autoFocus={true}
      />
    );

    const editor = page.locator(".ProseMirror");

    // Wait for editor to be focused - check for focus class
    await expect(editor).toHaveClass(/ProseMirror-focused/);

    // Add a small delay to ensure focus is fully settled
    await page.waitForTimeout(100);

    // Editor should be focused - we can type without clicking
    await page.keyboard.type("Auto-focused!");

    await expect(editor).toContainText("Auto-focused!");
  });
});
