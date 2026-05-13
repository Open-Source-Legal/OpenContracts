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
          creator: { id: "user-1", slug: "alice" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    await expect(page.getByText("Quarterly Earnings Report")).toBeVisible();
    await expect(page.getByText("application/pdf")).toBeVisible();
    // Slug-only privacy: cross-user surfaces render the slug, never email.
    await expect(page.getByText("alice")).toBeVisible();
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
          creator: { id: "user-2", slug: "bob" },
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
          creator: { id: "user-1", slug: "alice" },
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

  test("keeps mobile header compact with actions on-screen", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 402, height: 874 });

    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={false}
        readOnly={false}
        metadata={{
          title: "sample",
          fileType: "application/pdf",
          creator: { id: "user-1", slug: "gustyCoral" },
          created: "2026-05-10T12:00:00Z",
        }}
      />
    );

    const headerBox = await page.getByTestId("document-header").boundingBox();
    const addBox = await page.getByTestId("add-to-corpus-button").boundingBox();
    const backBox = await page.getByTestId("back-button").boundingBox();

    expect(headerBox).not.toBeNull();
    expect(addBox).not.toBeNull();
    expect(backBox).not.toBeNull();

    expect(headerBox!.height).toBeLessThanOrEqual(112);
    expect(headerBox!.x + headerBox!.width).toBeLessThanOrEqual(402);
    expect(addBox!.x + addBox!.width).toBeLessThanOrEqual(
      headerBox!.x + headerBox!.width
    );
    expect(backBox!.x + backBox!.width).toBeLessThanOrEqual(
      headerBox!.x + headerBox!.width
    );

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
          creator: { id: "user-1", slug: "alice" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    await expect(page.getByTestId("add-to-corpus-button")).toHaveCount(0);
    // Back button is always present.
    await expect(page.getByTestId("back-button")).toBeVisible();

    await component.unmount();
  });

  test("clicking the back button invokes onClose (covers logging branch)", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={true}
        corpusId="corpus-1"
        metadata={{
          title: "Closeable Document",
          fileType: "application/pdf",
          creator: { id: "user-1", slug: "alice" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    const wrapper = page.getByTestId("header-bar-test-wrapper");
    await expect(wrapper).toHaveAttribute("data-close-count", "0");

    await page.getByTestId("back-button").click();

    await expect(wrapper).toHaveAttribute("data-close-count", "1");

    await component.unmount();
  });

  test("clicking Add-to-Corpus invokes onAddToCorpus when corpus is absent", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <HeaderBarTestWrapper
        hasCorpus={false}
        metadata={{
          title: "Orphan Document",
          fileType: "application/pdf",
          creator: { id: "user-1", slug: "alice" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    const wrapper = page.getByTestId("header-bar-test-wrapper");
    await expect(wrapper).toHaveAttribute("data-add-count", "0");

    await page.getByTestId("add-to-corpus-button").click();

    await expect(wrapper).toHaveAttribute("data-add-count", "1");

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
          creator: { id: "user-1", slug: "alice" },
          created: "2025-09-10T12:00:00Z",
        }}
      />
    );

    await expect(page.getByTestId("add-to-corpus-button")).toHaveCount(0);

    await component.unmount();
  });
});
