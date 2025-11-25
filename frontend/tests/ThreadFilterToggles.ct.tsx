import { test, expect } from "@playwright/experimental-ct-react";
import { Provider as JotaiProvider } from "jotai";
import { ThreadFilterToggles } from "../src/components/threads/ThreadFilterToggles";

test.describe("ThreadFilterToggles", () => {
  test("renders with default filters (showLocked=true, showDeleted=false)", async ({
    mount,
  }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadFilterToggles />
      </JotaiProvider>
    );

    await expect(component.getByText("Show:")).toBeVisible();

    const lockedButton = component.getByRole("button", {
      name: /locked threads/i,
    });
    await expect(lockedButton).toBeVisible();
    await expect(lockedButton).toHaveAttribute("aria-pressed", "true");

    // Deleted button should not be visible (showModeratorFilters=false)
    await expect(
      component.getByRole("button", { name: /deleted threads/i })
    ).not.toBeVisible();
  });

  test("toggles locked filter when clicked", async ({ mount }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadFilterToggles />
      </JotaiProvider>
    );

    const lockedButton = component.getByRole("button", {
      name: /locked threads/i,
    });

    // Initially active
    await expect(lockedButton).toHaveAttribute("aria-pressed", "true");

    // Click to toggle off
    await lockedButton.click();
    await expect(lockedButton).toHaveAttribute("aria-pressed", "false");

    // Click to toggle on again
    await lockedButton.click();
    await expect(lockedButton).toHaveAttribute("aria-pressed", "true");
  });

  test("shows deleted filter when showModeratorFilters=true", async ({
    mount,
  }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadFilterToggles showModeratorFilters={true} />
      </JotaiProvider>
    );

    const deletedButton = component.getByRole("button", {
      name: /deleted threads/i,
    });
    await expect(deletedButton).toBeVisible();

    // Should be off by default
    await expect(deletedButton).toHaveAttribute("aria-pressed", "false");
  });

  test("toggles deleted filter when showModeratorFilters=true", async ({
    mount,
  }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadFilterToggles showModeratorFilters={true} />
      </JotaiProvider>
    );

    const deletedButton = component.getByRole("button", {
      name: /deleted threads/i,
    });

    // Initially inactive
    await expect(deletedButton).toHaveAttribute("aria-pressed", "false");

    // Click to toggle on
    await deletedButton.click();
    await expect(deletedButton).toHaveAttribute("aria-pressed", "true");

    // Click to toggle off
    await deletedButton.click();
    await expect(deletedButton).toHaveAttribute("aria-pressed", "false");
  });

  test("displays lock and trash icons", async ({ mount }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadFilterToggles showModeratorFilters={true} />
      </JotaiProvider>
    );

    const lockedButton = component.getByRole("button", {
      name: /locked threads/i,
    });
    const deletedButton = component.getByRole("button", {
      name: /deleted threads/i,
    });

    // Check icons are present (Lucide icons render as SVG)
    await expect(lockedButton.locator("svg")).toBeVisible();
    await expect(deletedButton.locator("svg")).toBeVisible();
  });

  test("maintains independent toggle states", async ({ mount }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadFilterToggles showModeratorFilters={true} />
      </JotaiProvider>
    );

    const lockedButton = component.getByRole("button", {
      name: /locked threads/i,
    });
    const deletedButton = component.getByRole("button", {
      name: /deleted threads/i,
    });

    // Initial: locked=true, deleted=false
    await expect(lockedButton).toHaveAttribute("aria-pressed", "true");
    await expect(deletedButton).toHaveAttribute("aria-pressed", "false");

    // Toggle both
    await lockedButton.click();
    await deletedButton.click();

    // Now: locked=false, deleted=true
    await expect(lockedButton).toHaveAttribute("aria-pressed", "false");
    await expect(deletedButton).toHaveAttribute("aria-pressed", "true");

    // Toggle locked back
    await lockedButton.click();

    // Now: locked=true, deleted=true
    await expect(lockedButton).toHaveAttribute("aria-pressed", "true");
    await expect(deletedButton).toHaveAttribute("aria-pressed", "true");
  });
});
