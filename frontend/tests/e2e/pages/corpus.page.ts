import { Page, Locator, expect } from "@playwright/test";

/**
 * Page Object for Corpus-related pages.
 *
 * Handles navigation and interactions with corpus list, corpus view,
 * document uploads, and folder management.
 */
export class CorpusPage {
  readonly page: Page;

  // Corpus list elements
  readonly corpusList: Locator;
  readonly createCorpusButton: Locator;

  // Corpus view elements
  readonly corpusTitle: Locator;
  readonly documentGrid: Locator;
  readonly folderTree: Locator;
  readonly uploadButton: Locator;

  // Folder elements
  readonly folderCards: Locator;
  readonly parentFolderCard: Locator;

  // Document elements
  readonly documentCards: Locator;

  constructor(page: Page) {
    this.page = page;

    // Corpus list
    this.corpusList = page.locator('[data-testid="corpus-list"], .corpus-list');
    this.createCorpusButton = page.locator(
      'button:has-text("Create Corpus"), button:has-text("New Corpus"), [data-testid="create-corpus-btn"]'
    );

    // Corpus view
    this.corpusTitle = page
      .locator('[data-testid="corpus-title"], h1, h2')
      .first();
    this.documentGrid = page.locator(
      '[data-testid="document-grid"], #corpus-document-card-content-container'
    );
    this.folderTree = page.locator(
      '[data-testid="folder-tree"], [class*="FolderTree"], [class*="folder-sidebar"]'
    );
    this.uploadButton = page.locator(
      'button:has-text("Upload"), [data-testid="upload-btn"]'
    );

    // Folders
    this.folderCards = page.locator(
      '[data-testid="folder-card"], [class*="FolderCard"]'
    );
    this.parentFolderCard = page.locator(
      '[data-testid="parent-folder-card"], [class*="ParentFolderCard"]'
    );

    // Documents
    this.documentCards = page.locator(
      '[data-testid="document-card"], [class*="DocumentCard"]'
    );
  }

  /**
   * Navigate to the corpuses list
   */
  async gotoCorpusList() {
    await this.page.goto("/corpuses");
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Navigate to a specific corpus by ID
   */
  async gotoCorpus(corpusId: string) {
    await this.page.goto(`/corpuses/${corpusId}`);
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Navigate to a specific corpus by user/slug URL
   */
  async gotoCorpusBySlug(username: string, corpusSlug: string) {
    await this.page.goto(`/${username}/${corpusSlug}`);
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Click on a folder to navigate into it
   */
  async clickFolder(folderName: string) {
    const folder = this.page.locator(
      `[data-testid="folder-card"]:has-text("${folderName}"), [class*="FolderCard"]:has-text("${folderName}")`
    );
    await folder.click();
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Navigate back to parent folder
   */
  async clickParentFolder() {
    await this.parentFolderCard.click();
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Get count of visible folders
   */
  async getFolderCount(): Promise<number> {
    return this.folderCards.count();
  }

  /**
   * Get count of visible documents
   */
  async getDocumentCount(): Promise<number> {
    return this.documentCards.count();
  }

  /**
   * Check if a specific document is visible
   */
  async isDocumentVisible(documentTitle: string): Promise<boolean> {
    const doc = this.page.locator(
      `[data-testid="document-card"]:has-text("${documentTitle}"), [class*="DocumentCard"]:has-text("${documentTitle}")`
    );
    return doc.isVisible();
  }

  /**
   * Check if a specific folder is visible
   */
  async isFolderVisible(folderName: string): Promise<boolean> {
    const folder = this.page.locator(
      `[data-testid="folder-card"]:has-text("${folderName}"), [class*="FolderCard"]:has-text("${folderName}")`
    );
    return folder.isVisible();
  }

  /**
   * Upload a file using the file input
   * Note: This triggers the file chooser dialog programmatically
   */
  async uploadFile(filePath: string) {
    // Most upload implementations use a hidden file input
    const fileInput = this.page.locator('input[type="file"]');

    // Set the file(s)
    await fileInput.setInputFiles(filePath);

    // Wait for upload to complete (look for success indicator)
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Upload multiple files
   */
  async uploadFiles(filePaths: string[]) {
    const fileInput = this.page.locator('input[type="file"]');
    await fileInput.setInputFiles(filePaths);
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Drag a document to a folder
   */
  async dragDocumentToFolder(documentTitle: string, folderName: string) {
    const document = this.page.locator(
      `[data-testid="document-card"]:has-text("${documentTitle}")`
    );
    const folder = this.page.locator(
      `[data-testid="folder-card"]:has-text("${folderName}")`
    );

    // Get bounding boxes
    const docBox = await document.boundingBox();
    const folderBox = await folder.boundingBox();

    if (!docBox || !folderBox) {
      throw new Error("Could not find document or folder element");
    }

    // Perform drag operation
    await this.page.mouse.move(
      docBox.x + docBox.width / 2,
      docBox.y + docBox.height / 2
    );
    await this.page.mouse.down();
    await this.page.mouse.move(
      folderBox.x + folderBox.width / 2,
      folderBox.y + folderBox.height / 2,
      { steps: 10 }
    );
    await this.page.mouse.up();

    // Wait for move to complete
    await this.page.waitForTimeout(1000);
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Wait for corpus content to load
   */
  async waitForContent() {
    await expect(this.documentGrid).toBeVisible({ timeout: 15000 });
  }

  /**
   * Assert no documents are shown
   */
  async expectNoDocuments() {
    await expect(this.documentCards).toHaveCount(0);
  }

  /**
   * Assert specific number of documents
   */
  async expectDocumentCount(count: number) {
    await expect(this.documentCards).toHaveCount(count, { timeout: 10000 });
  }

  /**
   * Assert specific number of folders
   */
  async expectFolderCount(count: number) {
    await expect(this.folderCards).toHaveCount(count, { timeout: 10000 });
  }
}
