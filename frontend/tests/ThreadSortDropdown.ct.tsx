import { test, expect } from "@playwright/experimental-ct-react";
import { Provider as JotaiProvider } from "jotai";
import { ThreadSortDropdown } from "../src/components/threads/ThreadSortDropdown";
import { threadSortAtom } from "../src/atoms/threadAtoms";

test.describe("ThreadSortDropdown", () => {
  test("renders with default sort option", async ({ mount }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    await expect(component.getByText("Sort: Pinned First")).toBeVisible();
  });

  test("opens dropdown when clicked", async ({ mount, page }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Check all options are visible
    await expect(
      page.getByRole("menuitem", { name: /Sort by Pinned First/i })
    ).toBeVisible();
    await expect(
      page.getByRole("menuitem", { name: /Sort by Newest/i })
    ).toBeVisible();
    await expect(
      page.getByRole("menuitem", { name: /Sort by Most Active/i })
    ).toBeVisible();
    await expect(
      page.getByRole("menuitem", { name: /Sort by Most Upvoted/i })
    ).toBeVisible();
  });

  test("changes sort option when clicked", async ({ mount, page }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    // Open dropdown
    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Click "Newest" option
    await page.getByRole("menuitem", { name: /Sort by Newest/i }).click();

    // Verify button text updated
    await expect(component.getByText("Sort: Newest")).toBeVisible();
  });

  test("closes dropdown after selecting option", async ({ mount, page }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Select an option
    await page.getByRole("menuitem", { name: /Sort by Most Active/i }).click();

    // Dropdown should be closed
    await expect(
      page.getByRole("menuitem", { name: /Sort by Newest/i })
    ).not.toBeVisible();
  });

  test("closes dropdown on Escape key", async ({ mount, page }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Press Escape
    await page.keyboard.press("Escape");

    // Dropdown should be closed
    await expect(
      page.getByRole("menuitem", { name: /Sort by Newest/i })
    ).not.toBeVisible();
  });

  test("closes dropdown when clicking outside", async ({ mount, page }) => {
    const component = await mount(
      <div>
        <JotaiProvider>
          <div>
            <ThreadSortDropdown />
            <div data-testid="outside">Outside element</div>
          </div>
        </JotaiProvider>
      </div>
    );

    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Verify dropdown is open
    await expect(
      page.getByRole("menuitem", { name: /Sort by Newest/i })
    ).toBeVisible();

    // Click outside
    await page.getByTestId("outside").click();

    // Dropdown should be closed
    await expect(
      page.getByRole("menuitem", { name: /Sort by Newest/i })
    ).not.toBeVisible();
  });

  test("highlights active option", async ({ mount, page }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Default is "Pinned First", should show checkmark
    const pinnedOption = page.getByRole("menuitem", {
      name: /Sort by Pinned First/i,
    });
    await expect(pinnedOption).toBeVisible();

    // Checkmark icon should be visible (represented by Check component)
    const checkIcon = pinnedOption.locator("svg");
    await expect(checkIcon).toBeVisible();
  });

  test("displays all sort options with descriptions", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <JotaiProvider>
        <ThreadSortDropdown />
      </JotaiProvider>
    );

    const button = component.getByRole("button", { name: /sort threads/i });
    await button.click();

    // Check all descriptions are present
    await expect(
      page.getByText("Show pinned threads at the top")
    ).toBeVisible();
    await expect(page.getByText("Most recently created threads")).toBeVisible();
    await expect(page.getByText("Recently updated threads")).toBeVisible();
    await expect(page.getByText("Threads with most engagement")).toBeVisible();
  });
});
