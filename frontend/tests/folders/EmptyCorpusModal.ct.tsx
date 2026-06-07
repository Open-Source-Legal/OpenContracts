import { test, expect } from "../utils/coverage";
import { docScreenshot } from "../utils/docScreenshot";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import { EmptyCorpusModal } from "../../src/components/corpuses/folders/EmptyCorpusModal";

/**
 * EmptyCorpusModal is the confirmation surface for the corpus-level
 * "empty everything" action: it moves every document in the corpus to Trash
 * and removes all folders. It is a plain prop-driven component (open / onClose
 * / corpusId), so we mount it directly through FolderTestWrapper rather than a
 * Jotai-backed fixture.
 */
test.describe("EmptyCorpusModal", () => {
  const noop = () => {};

  test.describe("Modal Visibility", () => {
    test("renders confirmation dialog when open", async ({ mount, page }) => {
      const component = await mount(
        <FolderTestWrapper>
          <EmptyCorpusModal open={true} onClose={noop} corpusId="corpus-1" />
        </FolderTestWrapper>
      );

      // Modal renders to document.body (portal), so check page not component
      await expect(
        page.locator(".oc-modal-header__title", { hasText: "Empty Corpus" })
      ).toBeVisible({ timeout: 5000 });

      await expect(page.getByText("Move everything to Trash?")).toBeVisible();

      await docScreenshot(page, "folders--empty-corpus-modal--confirmation");
    });

    test("does not render when open is false", async ({ mount, page }) => {
      const component = await mount(
        <FolderTestWrapper>
          <EmptyCorpusModal open={false} onClose={noop} corpusId="corpus-1" />
        </FolderTestWrapper>
      );

      await expect(
        page.getByText("Move everything to Trash?")
      ).not.toBeVisible();
    });
  });

  test.describe("Warning Content", () => {
    test("explains the trash + folder-removal behavior", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <FolderTestWrapper>
          <EmptyCorpusModal open={true} onClose={noop} corpusId="corpus-1" />
        </FolderTestWrapper>
      );

      // Every document moves to Trash...
      await expect(
        page.locator("strong", { hasText: "every document in this corpus" })
      ).toBeVisible({ timeout: 5000 });
      // ...and all folders are removed.
      await expect(
        page.locator("strong", { hasText: "all folders" })
      ).toBeVisible();
      // Recoverability is called out so the action doesn't read as permanent.
      await expect(
        page.getByText(
          "Documents are recoverable from the Trash until you empty it."
        )
      ).toBeVisible();
    });
  });

  test.describe("Modal Actions", () => {
    test("has a Cancel button", async ({ mount, page }) => {
      const component = await mount(
        <FolderTestWrapper>
          <EmptyCorpusModal open={true} onClose={noop} corpusId="corpus-1" />
        </FolderTestWrapper>
      );

      await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible({
        timeout: 5000,
      });
    });

    test("has a danger-styled confirm button", async ({ mount, page }) => {
      const component = await mount(
        <FolderTestWrapper>
          <EmptyCorpusModal open={true} onClose={noop} corpusId="corpus-1" />
        </FolderTestWrapper>
      );

      const confirmButton = page.getByRole("button", {
        name: "Move Everything to Trash",
      });
      await expect(confirmButton).toBeVisible({ timeout: 5000 });
      await expect(confirmButton).toHaveClass(/oc-button--danger/);
    });

    test("close button has aria-label", async ({ mount, page }) => {
      const component = await mount(
        <FolderTestWrapper>
          <EmptyCorpusModal open={true} onClose={noop} corpusId="corpus-1" />
        </FolderTestWrapper>
      );

      const closeButton = page.getByRole("button", { name: "Close" });
      await expect(closeButton).toBeVisible({ timeout: 5000 });
      await expect(closeButton).toHaveAttribute("aria-label", "Close");
    });
  });
});
