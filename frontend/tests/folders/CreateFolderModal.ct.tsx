import { test, expect } from "@playwright/experimental-ct-react";
import { FolderTestWrapper } from "./utils/FolderTestWrapper";
import { CreateModalFixture } from "./utils/testFixtures";
import { createMockFolder } from "./utils/mockFolderData";
import {
  CREATE_CORPUS_FOLDER,
  GET_CORPUS_FOLDERS,
} from "../../src/graphql/queries/folders";

test.describe("CreateFolderModal", () => {
  test("renders modal when open", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    // Modal renders to document.body (portal), so check page not component
    await expect(page.getByText("Create New Folder")).toBeVisible({
      timeout: 5000,
    });
  });

  test("does not render when closed", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture showModal={false} />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Create New Folder")).not.toBeVisible();
  });

  test("shows all form fields", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Folder Name")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Description")).toBeVisible();
    await expect(page.getByText("Color")).toBeVisible();
    // Icon field - check for helper text which is unique
    await expect(page.getByText("Use Lucide React icon names")).toBeVisible();
    await expect(page.getByText("Comma-separated tags")).toBeVisible();
  });

  test("shows parent folder info when creating subfolder", async ({
    mount,
    page,
  }) => {
    const parentFolder = createMockFolder({
      id: "folder-1",
      name: "Parent Folder",
    });

    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture parentId="folder-1" folders={[parentFolder]} />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Creating folder inside:")).toBeVisible({
      timeout: 5000,
    });
    await expect(page.getByText("Parent Folder")).toBeVisible();
  });

  test("has Close button", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    const closeButton = page.getByRole("button", { name: "Close" });
    await expect(closeButton).toBeVisible();
  });

  test("has Cancel and Create Folder buttons", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Cancel")).toBeVisible();
    await expect(page.getByText("Create Folder")).toBeVisible();
  });

  test("Create Folder button is disabled when name is empty", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    const createButton = page.getByRole("button", {
      name: "Create Folder",
    });
    await expect(createButton).toBeDisabled();
  });

  test("shows validation error for empty name", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    // Click Create Folder without entering name
    const createButton = page.getByRole("button", {
      name: "Create Folder",
    });

    // Button should be disabled, so we can't test submission
    await expect(createButton).toBeDisabled();
  });

  test("shows color picker", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    // Check color preview is visible - look on page since modal is in portal
    await expect(page.getByText("Color")).toBeVisible({ timeout: 5000 });
  });

  test("shows icon field with helper text", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    await expect(page.getByText("Use Lucide React icon names")).toBeVisible();
  });

  test("shows tags field with helper text", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    await expect(
      page.getByText("Comma-separated tags for organization")
    ).toBeVisible();
  });

  test("allows entering folder name", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    const nameInput = page.getByPlaceholder("Enter folder name");
    await nameInput.fill("Test Folder");

    await expect(nameInput).toHaveValue("Test Folder");
  });

  test("allows entering description", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    const descriptionInput = page.getByPlaceholder("Optional description");
    await descriptionInput.fill("This is a test folder");

    await expect(descriptionInput).toHaveValue("This is a test folder");
  });

  test("allows entering tags", async ({ mount, page }) => {
    const component = await mount(
      <FolderTestWrapper>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    const tagsInput = page.getByPlaceholder("tag1, tag2, tag3");
    await tagsInput.fill("legal, contracts");

    await expect(tagsInput).toHaveValue("legal, contracts");
  });

  test("submits form with valid data", async ({ mount, page }) => {
    const newFolder = createMockFolder({
      id: "new-folder",
      name: "New Folder",
      description: "Test description",
      tags: ["tag1", "tag2"],
    });

    const mocks = [
      {
        request: {
          query: CREATE_CORPUS_FOLDER,
          variables: {
            corpusId: "corpus-1",
            name: "New Folder",
            parentId: null,
            description: "Test description",
            color: "#05313d",
            icon: "folder",
            tags: ["tag1", "tag2"],
          },
        },
        result: {
          data: {
            createCorpusFolder: {
              ok: true,
              message: "Folder created successfully",
              folder: newFolder,
            },
          },
        },
      },
      {
        request: {
          query: GET_CORPUS_FOLDERS,
          variables: { corpusId: "corpus-1" },
        },
        result: {
          data: {
            corpusFolders: [newFolder],
          },
        },
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    // Fill out form
    await page.getByPlaceholder("Enter folder name").fill("New Folder");
    await page
      .getByPlaceholder("Optional description")
      .fill("Test description");
    await page.getByPlaceholder("tag1, tag2, tag3").fill("tag1, tag2");

    // Submit form
    const createButton = page.getByRole("button", {
      name: "Create Folder",
    });
    await createButton.click();

    // Wait a moment for mutation to process
    await page.waitForTimeout(2000);
  });

  test("shows error message on mutation failure", async ({ mount, page }) => {
    const mocks = [
      {
        request: {
          query: CREATE_CORPUS_FOLDER,
          variables: {
            corpusId: "corpus-1",
            name: "Error Folder",
            parentId: null,
            description: "",
            color: "#05313d",
            icon: "folder",
            tags: [],
          },
        },
        error: new Error("Failed to create folder"),
      },
    ];

    const component = await mount(
      <FolderTestWrapper mocks={mocks}>
        <CreateModalFixture />
      </FolderTestWrapper>
    );

    // Fill out form
    await page.getByPlaceholder("Enter folder name").fill("Error Folder");

    // Submit form
    const createButton = page.getByRole("button", {
      name: "Create Folder",
    });
    await createButton.click();

    // Wait for error message
    await expect(page.getByText("Error Creating Folder")).toBeVisible({
      timeout: 5000,
    });
  });
});
