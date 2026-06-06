import { test, expect } from "../utils/coverage";
import { docScreenshot } from "../utils/docScreenshot";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import { ToolbarFixture } from "./utils/testFixtures";

test.describe("FolderToolbar", () => {
  test.describe("Navigation Buttons", () => {
    test("back button is disabled when canGoBack is false", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture canGoBack={false} />
        </FolderTestWrapper>
      );

      const backButton = component.getByRole("button", { name: "Go back" });
      await expect(backButton).toBeVisible();
      await expect(backButton).toBeDisabled();
    });

    test("back button is enabled when canGoBack is true", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture canGoBack={true} />
        </FolderTestWrapper>
      );

      const backButton = component.getByRole("button", { name: "Go back" });
      await expect(backButton).toBeVisible();
      await expect(backButton).toBeEnabled();
    });

    test("up button is disabled when at root (selectedFolderId is null)", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture selectedFolderId={null} />
        </FolderTestWrapper>
      );

      const upButton = component.getByRole("button", { name: "Go to root" });
      await expect(upButton).toBeVisible();
      await expect(upButton).toBeDisabled();
    });

    test("up button is enabled when in a folder", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture selectedFolderId="folder-1" />
        </FolderTestWrapper>
      );

      const upButton = component.getByRole("button", { name: "Go to root" });
      await expect(upButton).toBeVisible();
      await expect(upButton).toBeEnabled();
    });
  });

  test.describe("View Mode Toggles", () => {
    test("shows all three view mode buttons", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture />
        </FolderTestWrapper>
      );

      await expect(
        component.getByRole("button", { name: "List view" })
      ).toBeVisible();
      await expect(
        component.getByRole("button", { name: "Card view" })
      ).toBeVisible();
      await expect(
        component.getByRole("button", { name: "Table view" })
      ).toBeVisible();
    });

    test("list view button is active when viewMode is modern-list", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture viewMode="modern-list" />
        </FolderTestWrapper>
      );

      const listButton = component.getByTestId("list-view-button");
      // Check that it has the active background color (accent color)
      const style = await listButton.evaluate((el) =>
        window.getComputedStyle(el)
      );
      // Active button should have accent background (not white)
      expect(style.backgroundColor).not.toBe("rgb(255, 255, 255)");
    });

    test("card view button is active when viewMode is modern-card", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture viewMode="modern-card" />
        </FolderTestWrapper>
      );

      const cardButton = component.getByTestId("card-view-button");
      const style = await cardButton.evaluate((el) =>
        window.getComputedStyle(el)
      );
      expect(style.backgroundColor).not.toBe("rgb(255, 255, 255)");
    });

    test("table view button is active when viewMode is grid", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture viewMode="grid" />
        </FolderTestWrapper>
      );

      const gridButton = component.getByTestId("grid-view-button");
      const style = await gridButton.evaluate((el) =>
        window.getComputedStyle(el)
      );
      expect(style.backgroundColor).not.toBe("rgb(255, 255, 255)");
    });
  });

  test.describe("Action Buttons", () => {
    test("shows upload button", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture />
        </FolderTestWrapper>
      );

      // Main upload button has text "Upload" - use exact match to avoid matching dropdown
      const uploadButton = component.getByRole("button", {
        name: "Upload",
        exact: true,
      });
      await expect(uploadButton).toBeVisible();
    });

    test("shows new folder button when canCreateFolders is true", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture canCreateFolders={true} />
        </FolderTestWrapper>
      );

      // New folder button has text "New Folder"
      const newFolderButton = component.getByRole("button", {
        name: /New Folder/i,
      });
      await expect(newFolderButton).toBeVisible();
    });

    test("hides new folder button when canCreateFolders is false", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture canCreateFolders={false} />
        </FolderTestWrapper>
      );

      // Look for button with text "New Folder" - should not exist
      const newFolderButtons = component.locator(
        'button:has-text("New Folder")'
      );
      await expect(newFolderButtons).toHaveCount(0);
    });
  });

  test.describe("Sidebar Toggle", () => {
    test("shows sidebar toggle when showSidebar is true", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture showSidebar={true} />
        </FolderTestWrapper>
      );

      const sidebarToggle = component.getByRole("button", {
        name: /folders/i,
      });
      await expect(sidebarToggle.first()).toBeVisible();
    });

    test("hides sidebar toggle when showSidebar is false", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture showSidebar={false} />
        </FolderTestWrapper>
      );

      // Should not have a sidebar toggle button
      const sidebarButtons = component.getByRole("button", {
        name: /Show folders|Hide folders/i,
      });
      await expect(sidebarButtons).toHaveCount(0);
    });
  });

  test.describe("Mobile Menu", () => {
    // Mobile menu is only visible at mobile viewport (max-width: 768px)
    test.use({ viewport: { width: 375, height: 667 } });

    test("shows mobile kebab menu button when showSidebar is true", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture showSidebar={true} />
        </FolderTestWrapper>
      );

      const kebabButton = component.getByRole("button", {
        name: "More options",
      });
      await expect(kebabButton).toBeVisible();
    });

    test("hides mobile kebab menu button when showSidebar is false", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture showSidebar={false} />
        </FolderTestWrapper>
      );

      const kebabButton = component.getByRole("button", {
        name: "More options",
      });
      await expect(kebabButton).toHaveCount(0);
    });

    test("mobile menu has correct ARIA attributes", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture showSidebar={true} />
        </FolderTestWrapper>
      );

      // Open the mobile menu
      const kebabButton = component.getByRole("button", {
        name: "More options",
      });
      await kebabButton.click();

      // Check menu has role="menu" and aria-label
      const menu = component.getByRole("menu");
      await expect(menu).toBeVisible();
      await expect(menu).toHaveAttribute("aria-label", "Toolbar actions menu");

      // Check menu items have role="menuitem"
      const menuItems = component.getByRole("menuitem");
      expect(await menuItems.count()).toBeGreaterThan(0);
    });
  });

  test.describe("Accessibility", () => {
    test("all interactive elements have accessible names", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture />
        </FolderTestWrapper>
      );

      // Check that all buttons have aria-labels or accessible names
      const backButton = component.getByRole("button", { name: "Go back" });
      await expect(backButton).toHaveAttribute("aria-label", "Go back");

      const upButton = component.getByRole("button", { name: "Go to root" });
      await expect(upButton).toHaveAttribute("aria-label", "Go to root");

      const listButton = component.getByRole("button", { name: "List view" });
      await expect(listButton).toHaveAttribute("aria-label", "List view");

      const cardButton = component.getByRole("button", { name: "Card view" });
      await expect(cardButton).toHaveAttribute("aria-label", "Card view");

      const tableButton = component.getByRole("button", { name: "Table view" });
      await expect(tableButton).toHaveAttribute("aria-label", "Table view");
    });
  });

  test.describe("Selection Controls", () => {
    test("shows selection group when documents exist and onSelectAll is provided", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
          />
        </FolderTestWrapper>
      );

      // Selection group should be visible with Select All button
      const selectAllButton = component.getByRole("button", {
        name: "Select all",
      });
      await expect(selectAllButton).toBeVisible();
    });

    test("hides selection group when no documents exist", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={0}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
          />
        </FolderTestWrapper>
      );

      // Selection group should not be visible
      const selectAllButtons = component.locator(
        'button:has-text("Select All")'
      );
      await expect(selectAllButtons).toHaveCount(0);
    });

    test("shows selection count when documents are selected", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={3}
            onSelectAll={() => {}}
            onClearSelection={() => {}}
          />
        </FolderTestWrapper>
      );

      // Should show "3 of 10" text
      await expect(component.locator("text=3 of 10")).toBeVisible();
    });

    test("shows clear selection button when documents are selected", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={3}
            onSelectAll={() => {}}
            onClearSelection={() => {}}
          />
        </FolderTestWrapper>
      );

      const clearButton = component.getByRole("button", {
        name: "Clear selection",
      });
      await expect(clearButton).toBeVisible();
    });

    test("calls onSelectAll when Select All button is clicked", async ({
      mount,
    }) => {
      let selectAllCalled = false;
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {
              selectAllCalled = true;
            }}
          />
        </FolderTestWrapper>
      );

      const selectAllButton = component.getByRole("button", {
        name: "Select all",
      });
      await selectAllButton.click();

      expect(selectAllCalled).toBe(true);
    });

    test("calls onClearSelection when clear button is clicked", async ({
      mount,
    }) => {
      let clearCalled = false;
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={3}
            onSelectAll={() => {}}
            onClearSelection={() => {
              clearCalled = true;
            }}
          />
        </FolderTestWrapper>
      );

      const clearButton = component.getByRole("button", {
        name: "Clear selection",
      });
      await clearButton.click();

      expect(clearCalled).toBe(true);
    });

    test("Select All button is disabled when loading", async ({ mount }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
            isLoading={true}
          />
        </FolderTestWrapper>
      );

      const selectAllButton = component.getByRole("button", {
        name: "Loading documents",
      });
      await expect(selectAllButton).toBeDisabled();
    });

    test("shows checkmark icon when all documents are selected", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={10}
            onSelectAll={() => {}}
            allSelected={true}
          />
        </FolderTestWrapper>
      );

      // When all selected, button should say "Deselect all"
      const deselectButton = component.getByRole("button", {
        name: "Deselect all",
      });
      await expect(deselectButton).toBeVisible();
    });
  });

  test.describe("Remove from Corpus Button", () => {
    test("shows Remove button when documents are selected", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={3}
            onSelectAll={() => {}}
            onRemoveFromCorpus={() => {}}
          />
        </FolderTestWrapper>
      );

      // Remove button should show count
      const removeButton = component.locator('button:has-text("Remove (3)")');
      await expect(removeButton).toBeVisible();
    });

    test("hides Remove button when no documents are selected", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
            onRemoveFromCorpus={() => {}}
          />
        </FolderTestWrapper>
      );

      const removeButtons = component.locator('button:has-text("Remove")');
      await expect(removeButtons).toHaveCount(0);
    });

    test("calls onRemoveFromCorpus when Remove button is clicked", async ({
      mount,
    }) => {
      let removeCalled = false;
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={3}
            onSelectAll={() => {}}
            onRemoveFromCorpus={() => {
              removeCalled = true;
            }}
          />
        </FolderTestWrapper>
      );

      const removeButton = component.locator('button:has-text("Remove (3)")');
      await removeButton.click();

      expect(removeCalled).toBe(true);
    });

    test("Remove button shows correct singular text for 1 document", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={1}
            onSelectAll={() => {}}
            onRemoveFromCorpus={() => {}}
          />
        </FolderTestWrapper>
      );

      const removeButton = component.locator('button:has-text("Remove (1)")');
      await expect(removeButton).toBeVisible();
    });
  });

  test.describe("Empty Corpus Button", () => {
    test("shows Empty Corpus when onEmptyCorpus provided and documents exist", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
            onEmptyCorpus={() => {}}
          />
        </FolderTestWrapper>
      );

      const emptyButton = component.getByRole("button", {
        name: "Empty Corpus",
      });
      await expect(emptyButton).toBeVisible();

      await docScreenshot(page, "folders--folder-toolbar--empty-corpus-action");
    });

    test("hides Empty Corpus when onEmptyCorpus is omitted (no delete permission)", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
          />
        </FolderTestWrapper>
      );

      const emptyButtons = component.getByRole("button", {
        name: "Empty Corpus",
      });
      await expect(emptyButtons).toHaveCount(0);
    });

    test("hides Empty Corpus when corpus has no documents", async ({
      mount,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={0}
            selectedDocumentCount={0}
            onEmptyCorpus={() => {}}
          />
        </FolderTestWrapper>
      );

      const emptyButtons = component.getByRole("button", {
        name: "Empty Corpus",
      });
      await expect(emptyButtons).toHaveCount(0);
    });

    test("calls onEmptyCorpus when the button is clicked", async ({
      mount,
    }) => {
      let emptyCalled = false;
      const component = await mount(
        <FolderTestWrapper>
          <ToolbarFixture
            totalDocumentCount={10}
            selectedDocumentCount={0}
            onSelectAll={() => {}}
            onEmptyCorpus={() => {
              emptyCalled = true;
            }}
          />
        </FolderTestWrapper>
      );

      await component.getByRole("button", { name: "Empty Corpus" }).click();
      expect(emptyCalled).toBe(true);
    });
  });
});
