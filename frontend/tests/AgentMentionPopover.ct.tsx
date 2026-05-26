import React from "react";
import type { Page } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import { AgentMentionPopover } from "../src/components/chat/AgentMentionPopover";
import type { AgentItem } from "../src/components/chat/AgentMentionPopover";
import { docScreenshot } from "./utils/docScreenshot";

// The popover listens to document-level keydown (capture phase) in a
// useEffect. page.keyboard.press routes through whatever element holds focus,
// and on a fresh mount the Playwright iframe sometimes doesn't yet hold
// document focus on the first attempt, so the keystroke is silently dropped
// (the test passes only on retry). Dispatching the KeyboardEvent on document
// directly avoids the focus dependency.
async function pressDocumentKey(page: Page, key: string): Promise<void> {
  await page.evaluate((k) => {
    document.dispatchEvent(
      new KeyboardEvent("keydown", {
        key: k,
        code: k,
        bubbles: true,
        cancelable: true,
      })
    );
  }, key);
}

const AGENTS: AgentItem[] = [
  { id: "1", slug: "research-bot", name: "Research Bot", scope: "GLOBAL" },
  { id: "2", slug: "auditor", name: "Auditor", scope: "GLOBAL" },
  {
    id: "3",
    slug: "summarizer",
    name: "Summarizer",
    scope: "CORPUS",
    corpus: { slug: "acme", title: "Acme Corp" },
  },
];

test.describe("AgentMentionPopover", () => {
  test("renders matching agents filtered by fragment", async ({
    mount,
    page,
  }) => {
    await mount(
      <AgentMentionPopover
        fragment="res"
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    await expect(page.getByText("Research Bot")).toBeVisible();
    await expect(page.getByText("Auditor")).not.toBeVisible();
    await expect(page.getByText("Summarizer")).not.toBeVisible();
  });

  test("shows all agents when fragment is empty", async ({ mount, page }) => {
    await mount(
      <AgentMentionPopover
        fragment=""
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    // Use accessible-name role locators to avoid strict-mode collisions
    // between the name <strong> and the slug <span>.
    await expect(
      page.getByRole("option", { name: /Research Bot @research-bot/ })
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: /Auditor @auditor/ })
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: /Summarizer @summarizer/ })
    ).toBeVisible();
    await docScreenshot(page, "chat--agent-mention-popover--with-agents");
  });

  test("shows corpus name for corpus-scoped agents", async ({
    mount,
    page,
  }) => {
    await mount(
      <AgentMentionPopover
        fragment="sum"
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    await expect(page.getByText("Acme Corp", { exact: false })).toBeVisible();
  });

  test("clicking an agent emits onSelect with that agent", async ({
    mount,
    page,
  }) => {
    let selected: AgentItem | null = null;
    await mount(
      <AgentMentionPopover
        fragment=""
        agents={AGENTS}
        onSelect={(a) => {
          selected = a;
        }}
        onDismiss={() => {}}
      />
    );
    await page.getByText("Research Bot").click();
    await expect.poll(() => selected?.slug).toBe("research-bot");
  });

  test("Escape calls onDismiss", async ({ mount, page }) => {
    let dismissed = false;
    await mount(
      <AgentMentionPopover
        fragment=""
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {
          dismissed = true;
        }}
      />
    );
    // Wait until the popover is in the DOM so the capture-phase keydown
    // listener (attached in useEffect) is wired before dispatching Escape.
    await expect(
      page.locator('[data-testid="agent-mention-popover"]')
    ).toBeVisible();
    await pressDocumentKey(page, "Escape");
    await expect.poll(() => dismissed).toBe(true);
  });

  test("empty agents list shows 'No matching agents'", async ({
    mount,
    page,
  }) => {
    await mount(
      <AgentMentionPopover
        fragment="xyz"
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    await expect(page.getByText("No matching agents.")).toBeVisible();
  });

  test("ArrowDown moves aria-selected to the next option (wraps)", async ({
    mount,
    page,
  }) => {
    await mount(
      <AgentMentionPopover
        fragment=""
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    const options = page.getByRole("option");
    await expect(options.nth(0)).toHaveAttribute("aria-selected", "true");

    await pressDocumentKey(page, "ArrowDown");
    await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(options.nth(0)).toHaveAttribute("aria-selected", "false");

    await pressDocumentKey(page, "ArrowDown");
    await expect(options.nth(2)).toHaveAttribute("aria-selected", "true");

    // Wrap to first
    await pressDocumentKey(page, "ArrowDown");
    await expect(options.nth(0)).toHaveAttribute("aria-selected", "true");
  });

  test("ArrowUp wraps from the first option to the last", async ({
    mount,
    page,
  }) => {
    await mount(
      <AgentMentionPopover
        fragment=""
        agents={AGENTS}
        onSelect={() => {}}
        onDismiss={() => {}}
      />
    );
    const options = page.getByRole("option");
    await expect(options.nth(0)).toHaveAttribute("aria-selected", "true");

    await pressDocumentKey(page, "ArrowUp");
    await expect(options.nth(2)).toHaveAttribute("aria-selected", "true");
  });

  test("Enter selects the currently active option", async ({ mount, page }) => {
    let selected: AgentItem | null = null;
    await mount(
      <AgentMentionPopover
        fragment=""
        agents={AGENTS}
        onSelect={(a) => {
          selected = a;
        }}
        onDismiss={() => {}}
      />
    );
    await pressDocumentKey(page, "ArrowDown"); // move to "Auditor"
    await pressDocumentKey(page, "Enter");
    await expect.poll(() => selected?.slug).toBe("auditor");
  });
});
