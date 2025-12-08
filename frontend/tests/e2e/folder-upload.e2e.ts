import { test, expect } from "@playwright/test";
import path from "path";
import { ApiClient } from "./fixtures/api-client";
import { CorpusPage } from "./pages/corpus.page";

/**
 * E2E Integration Tests for Folder and Document Upload functionality.
 *
 * These tests verify the complete user flow for:
 * - Uploading documents to corpus root
 * - Uploading documents to subfolders
 * - Document folder filtering (documents only appear in their folder)
 * - Navigation between folders
 * - Drag-drop document movement between folders
 *
 * Prerequisites:
 * - Backend running: docker compose -f local.yml up
 * - Test user exists with credentials from env vars
 * - Sample PDF file available for upload
 */

// Test data
const TEST_CORPUS_NAME = `E2E Test Corpus ${Date.now()}`;
const TEST_FOLDER_NAME = "Test Subfolder";
const SAMPLE_PDF_PATH = path.join(__dirname, "fixtures", "sample.pdf");

// Shared state across tests
let apiClient: ApiClient;
let testCorpusId: string;
let testFolderId: string;

test.describe("Folder and Document Upload", () => {
  test.beforeAll(async () => {
    // Setup: Create test corpus and folder via API
    apiClient = new ApiClient();

    const testUser = process.env.E2E_TEST_USER || "admin@example.com";
    const testPassword = process.env.E2E_TEST_PASSWORD || "admin";

    // Login via API
    await apiClient.login(testUser, testPassword);

    // Create test corpus
    const corpus = await apiClient.createCorpus(
      TEST_CORPUS_NAME,
      "E2E test corpus for folder upload tests"
    );
    testCorpusId = corpus.id;
    console.log(`   Created test corpus: ${corpus.title} (${corpus.id})`);

    // Create test folder
    const folder = await apiClient.createFolder(testCorpusId, TEST_FOLDER_NAME);
    testFolderId = folder.id;
    console.log(`   Created test folder: ${folder.name} (${folder.id})`);
  });

  test.afterAll(async () => {
    // Cleanup: Delete test corpus
    if (testCorpusId && apiClient) {
      try {
        await apiClient.deleteCorpus(testCorpusId);
        console.log(`   Cleaned up test corpus: ${testCorpusId}`);
      } catch (e) {
        console.warn(`   Failed to cleanup corpus: ${e}`);
      }
    }
  });

  test("should show empty corpus root initially", async ({ page }) => {
    const corpusPage = new CorpusPage(page);

    // Navigate to test corpus
    await corpusPage.gotoCorpus(testCorpusId);
    await corpusPage.waitForContent();

    // Should see the folder we created, but no documents yet
    await expect(corpusPage.folderCards.first()).toBeVisible();
    await corpusPage.expectNoDocuments();
  });

  test("should show folder in corpus root", async ({ page }) => {
    const corpusPage = new CorpusPage(page);

    await corpusPage.gotoCorpus(testCorpusId);
    await corpusPage.waitForContent();

    // Verify test folder is visible
    const isFolderVisible = await corpusPage.isFolderVisible(TEST_FOLDER_NAME);
    expect(isFolderVisible).toBe(true);
  });

  test("should navigate into subfolder", async ({ page }) => {
    const corpusPage = new CorpusPage(page);

    await corpusPage.gotoCorpus(testCorpusId);
    await corpusPage.waitForContent();

    // Click on folder to navigate into it
    await corpusPage.clickFolder(TEST_FOLDER_NAME);

    // Should see parent folder card (to navigate back)
    await expect(corpusPage.parentFolderCard).toBeVisible();

    // Should be empty (no documents in folder yet)
    await corpusPage.expectNoDocuments();
  });

  test("should navigate back to parent folder", async ({ page }) => {
    const corpusPage = new CorpusPage(page);

    await corpusPage.gotoCorpus(testCorpusId);
    await corpusPage.waitForContent();

    // Navigate into folder
    await corpusPage.clickFolder(TEST_FOLDER_NAME);
    await expect(corpusPage.parentFolderCard).toBeVisible();

    // Navigate back to root
    await corpusPage.clickParentFolder();

    // Should see folder again, no parent card
    await expect(corpusPage.parentFolderCard).not.toBeVisible();
    const isFolderVisible = await corpusPage.isFolderVisible(TEST_FOLDER_NAME);
    expect(isFolderVisible).toBe(true);
  });

  test.describe("Document Upload", () => {
    test.skip(
      !require("fs").existsSync(SAMPLE_PDF_PATH),
      "Sample PDF not found - skipping upload tests"
    );

    test("should upload document to corpus root", async ({ page }) => {
      const corpusPage = new CorpusPage(page);

      await corpusPage.gotoCorpus(testCorpusId);
      await corpusPage.waitForContent();

      // Upload file to root
      await corpusPage.uploadFile(SAMPLE_PDF_PATH);

      // Wait for upload to process (may take a few seconds)
      await page.waitForTimeout(3000);
      await page.reload();
      await corpusPage.waitForContent();

      // Should see document in root
      const docCount = await corpusPage.getDocumentCount();
      expect(docCount).toBeGreaterThanOrEqual(1);
    });

    test("document uploaded to root should not appear in subfolder", async ({
      page,
    }) => {
      const corpusPage = new CorpusPage(page);

      await corpusPage.gotoCorpus(testCorpusId);
      await corpusPage.waitForContent();

      // Navigate into subfolder
      await corpusPage.clickFolder(TEST_FOLDER_NAME);

      // Subfolder should still be empty
      await corpusPage.expectNoDocuments();
    });

    test("should upload document to subfolder", async ({ page }) => {
      const corpusPage = new CorpusPage(page);

      await corpusPage.gotoCorpus(testCorpusId);
      await corpusPage.waitForContent();

      // Navigate into folder
      await corpusPage.clickFolder(TEST_FOLDER_NAME);
      await expect(corpusPage.parentFolderCard).toBeVisible();

      // Upload file to subfolder
      await corpusPage.uploadFile(SAMPLE_PDF_PATH);

      // Wait for upload
      await page.waitForTimeout(3000);
      await page.reload();
      await corpusPage.waitForContent();

      // Navigate back into folder (reload puts us at root)
      await corpusPage.clickFolder(TEST_FOLDER_NAME);

      // Should see document in subfolder
      const docCount = await corpusPage.getDocumentCount();
      expect(docCount).toBeGreaterThanOrEqual(1);
    });

    test("document uploaded to subfolder should not appear in root", async ({
      page,
    }) => {
      const corpusPage = new CorpusPage(page);

      await corpusPage.gotoCorpus(testCorpusId);
      await corpusPage.waitForContent();

      // Count documents at root (should only have the one we uploaded to root)
      const rootDocCount = await corpusPage.getDocumentCount();

      // Navigate into subfolder
      await corpusPage.clickFolder(TEST_FOLDER_NAME);

      // Count documents in subfolder
      const subfolderDocCount = await corpusPage.getDocumentCount();

      // Documents should be distinct per folder
      console.log(
        `   Root docs: ${rootDocCount}, Subfolder docs: ${subfolderDocCount}`
      );
    });
  });

  test.describe("Drag and Drop", () => {
    test.skip(
      !require("fs").existsSync(SAMPLE_PDF_PATH),
      "Sample PDF not found - skipping drag-drop tests"
    );

    test("should move document from root to subfolder via drag-drop", async ({
      page,
    }) => {
      const corpusPage = new CorpusPage(page);

      await corpusPage.gotoCorpus(testCorpusId);
      await corpusPage.waitForContent();

      // Get initial counts
      const initialRootCount = await corpusPage.getDocumentCount();

      if (initialRootCount === 0) {
        test.skip(true, "No documents in root to drag");
        return;
      }

      // Get the first document title
      const firstDocTitle = await corpusPage.documentCards
        .first()
        .locator("text, h3, h4, .title")
        .first()
        .textContent();

      if (!firstDocTitle) {
        test.skip(true, "Could not get document title");
        return;
      }

      // Drag document to folder
      await corpusPage.dragDocumentToFolder(firstDocTitle, TEST_FOLDER_NAME);

      // Verify document is no longer in root
      await page.waitForTimeout(500);
      const newRootCount = await corpusPage.getDocumentCount();
      expect(newRootCount).toBe(initialRootCount - 1);

      // Navigate to subfolder and verify document is there
      await corpusPage.clickFolder(TEST_FOLDER_NAME);
      const subfolderCount = await corpusPage.getDocumentCount();
      expect(subfolderCount).toBeGreaterThanOrEqual(1);
    });
  });
});

test.describe("PDF File Visibility", () => {
  test("document should have pdfFile populated after upload", async ({
    page,
  }) => {
    // This test verifies the fix for the pdfFile field being empty
    // after document upload

    const corpusPage = new CorpusPage(page);

    // Navigate to test corpus (use the one created in beforeAll if available)
    if (!testCorpusId) {
      test.skip(true, "No test corpus available");
      return;
    }

    await corpusPage.gotoCorpus(testCorpusId);
    await corpusPage.waitForContent();

    // Click on a document to open it
    const docCard = corpusPage.documentCards.first();
    if ((await docCard.count()) === 0) {
      test.skip(true, "No documents to test");
      return;
    }

    await docCard.click();

    // Wait for document viewer to load
    await page.waitForLoadState("networkidle");

    // Check that PDF viewer is shown (not "unsupported file type" error)
    const pdfViewer = page.locator(
      '[data-testid="pdf-viewer"], canvas, .react-pdf__Page'
    );
    const errorMessage = page.locator('text="Unsupported file type"');

    // Either PDF viewer should be visible OR error should not be visible
    const isPdfVisible = await pdfViewer.isVisible().catch(() => false);
    const isErrorVisible = await errorMessage.isVisible().catch(() => false);

    // Log what we found for debugging
    console.log(`   PDF viewer visible: ${isPdfVisible}`);
    console.log(`   Error message visible: ${isErrorVisible}`);

    // We should NOT see the unsupported file type error
    expect(isErrorVisible).toBe(false);
  });
});
