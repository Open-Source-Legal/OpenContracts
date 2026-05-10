import React from "react";
import { test, expect } from "./utils/coverage";
import { HeaderBarTestWrapper } from "./HeaderBarTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test.describe("HeaderBar", () => {
  test("renders title, filetype, creator and created date when metadata is complete", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={false}
        metadata={{
          title: "Quarterly Earnings Report",
          fileType: "application/pdf",
          creator: { email: "alice@example.com" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    await expect(page.getByText("Quarterly Earnings Report")).toBeVisible();
    await expect(page.getByText("application/pdf")).toBeVisible();
    await expect(page.getByText("alice@example.com")).toBeVisible();
    await expect(page.getByText(/Created:/)).toBeVisible();
    // Confirm a real date is rendered (not the em-dash placeholder).
    await expect(page.getByText("—")).toHaveCount(0);

    await docScreenshot(page, "knowledge-base--header-bar--with-metadata");

    await component.unmount();
  });

  test("renders em-dash placeholder when created is null (no today-flash)", async ({
    mount,
    page,
  }) => {
    const today = new Date().toLocaleDateString();

    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={false}
        metadata={{
          title: "Loading Document",
          fileType: "application/pdf",
          creator: { email: "bob@example.com" },
          created: null,
        }}
      />
    );

    await expect(page.getByText(/Created:/)).toBeVisible();
    await expect(page.getByText("—")).toBeVisible();
    // Today's date must NOT appear — that was the bug being fixed.
    await expect(page.getByText(today)).toHaveCount(0);

    await docScreenshot(page, "knowledge-base--header-bar--null-created");

    await component.unmount();
  });

  test("shows Add-to-Corpus button when no corpus is bound and not readOnly", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={false}
        readOnly={false}
        metadata={{
          title: "Standalone Document",
          fileType: "application/pdf",
          creator: { email: "alice@example.com" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    const addBtn = page.getByTestId("add-to-corpus-button");
    await expect(addBtn).toBeVisible();
    await expect(addBtn).toContainText("Add to Corpus");

    await docScreenshot(page, "knowledge-base--header-bar--add-to-corpus-cta");

    await component.unmount();
  });

  test("hides Add-to-Corpus button when corpus is bound", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={true}
        corpusId="corpus-1"
        metadata={{
          title: "Corpus Document",
          fileType: "application/pdf",
          creator: { email: "alice@example.com" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    await expect(page.getByTestId("add-to-corpus-button")).toHaveCount(0);
    // Back button is always present.
    await expect(page.getByTestId("back-button")).toBeVisible();

    await component.unmount();
  });

  test("hides Add-to-Corpus button when readOnly even without corpus", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={false}
        readOnly={true}
        metadata={{
          title: "Read-only Document",
          fileType: "application/pdf",
          creator: { email: "alice@example.com" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    await expect(page.getByTestId("add-to-corpus-button")).toHaveCount(0);

    await component.unmount();
  });
});
