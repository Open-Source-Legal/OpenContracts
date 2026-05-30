import { test, expect } from "./utils/coverage";
import { CorpusCategoryManagementTestWrapper } from "./CorpusCategoryManagementTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  GET_ADMIN_CORPUS_CATEGORIES,
  CREATE_CORPUS_CATEGORY,
} from "../src/components/admin/corpus_categories/graphql";

const categoriesMock = {
  request: { query: GET_ADMIN_CORPUS_CATEGORIES },
  result: {
    data: {
      corpusCategories: {
        edges: [
          {
            node: {
              id: "cat-1",
              name: "Case Law",
              description: "Court decisions and judicial opinions",
              icon: "gavel",
              color: "#8B5CF6",
              sortOrder: 1,
              corpusCount: 3,
            },
          },
          {
            node: {
              id: "cat-2",
              name: "Contracts",
              description: "Commercial agreements",
              icon: "file-text",
              color: "#10B981",
              sortOrder: 2,
              corpusCount: 7,
            },
          },
        ],
      },
    },
  },
};

const createMock = {
  request: {
    query: CREATE_CORPUS_CATEGORY,
    variables: {
      name: "Statutes",
      description: "",
      icon: "scroll",
      color: "#3B82F6",
      sortOrder: 0,
    },
  },
  result: {
    data: {
      createCorpusCategory: {
        ok: true,
        message: "Success",
        obj: {
          id: "cat-3",
          name: "Statutes",
          description: "",
          icon: "scroll",
          color: "#3B82F6",
          sortOrder: 0,
          corpusCount: 0,
        },
      },
    },
  },
};

const emptyCategoriesMock = {
  request: { query: GET_ADMIN_CORPUS_CATEGORIES },
  result: {
    data: {
      corpusCategories: {
        edges: [],
      },
    },
  },
};

test.describe("CorpusCategoryManagement", () => {
  test("renders the empty state when there are no categories", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusCategoryManagementTestWrapper mocks={[emptyCategoriesMock]} />
    );

    await expect(page.getByText("No categories yet")).toBeVisible({
      timeout: 10000,
    });
    await expect(
      page.getByText("Create your first corpus category to start tagging")
    ).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "admin--corpus-categories--empty-state");
  });

  test("renders the category list for a superuser", async ({ mount, page }) => {
    await mount(
      <CorpusCategoryManagementTestWrapper
        mocks={[categoriesMock, categoriesMock]}
      />
    );

    await expect(page.getByText("Corpus Categories")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Case Law")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Contracts")).toBeVisible({ timeout: 10000 });
    // corpusCount column rendered
    await expect(
      page.getByText("Court decisions and judicial opinions")
    ).toBeVisible({ timeout: 10000 });

    await docScreenshot(page, "admin--corpus-categories--list-view");
  });

  test("blocks non-superusers", async ({ mount, page }) => {
    await mount(
      <CorpusCategoryManagementTestWrapper
        mocks={[categoriesMock]}
        isSuperuser={false}
      />
    );

    await expect(page.getByText("Superuser access required")).toBeVisible({
      timeout: 10000,
    });
    await expect(page.getByText("Case Law")).toHaveCount(0);
  });

  test("opens the create modal and submits a new category", async ({
    mount,
    page,
  }) => {
    await mount(
      <CorpusCategoryManagementTestWrapper
        mocks={[categoriesMock, categoriesMock, createMock, categoriesMock]}
      />
    );

    await expect(page.getByText("Corpus Categories")).toBeVisible({
      timeout: 10000,
    });

    await page.getByRole("button", { name: "New Category" }).click();
    // The unique "Create Category" submit button signals the modal is open
    // (avoids colliding with the "New Category" trigger button text).
    const submitButton = page.getByRole("button", { name: "Create Category" });
    await expect(submitButton).toBeVisible({ timeout: 5000 });

    await page.locator("#category-name").fill("Statutes");
    await page.locator("#category-icon").fill("scroll");

    await submitButton.click();

    // After a successful create the modal closes and the list refetches.
    await expect(submitButton).toHaveCount(0, { timeout: 10000 });
  });
});
