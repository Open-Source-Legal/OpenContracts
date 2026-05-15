import React from "react";
import { test, expect } from "./utils/coverage";
import { CreateUrlAnnotationModal } from "../src/components/annotator/components/modals/CreateUrlAnnotationModal";
import { docScreenshot } from "./utils/docScreenshot";

/**
 * Component coverage for CreateUrlAnnotationModal:
 *   - renders only when visible
 *   - shows the selected text as a read-only chip
 *   - rejects empty / unsafe URLs and surfaces an inline error
 *   - calls onConfirm with the trimmed URL on Create / Enter / Save
 *   - calls onCancel on Cancel
 *   - prefills the input on edit and toggles the header label
 *
 * The modal is the user's last client-side checkpoint before the URL is
 * sent to the server; the validation cases below pin the allow-list
 * (http(s):// + site-relative) that mirrors the backend.
 */

test.describe("CreateUrlAnnotationModal", () => {
  test("does not render when visible is false", async ({ mount, page }) => {
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={false}
        selectedText="hello"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );

    // The modal title for the create path. If the modal is closed, the
    // text must not be present in the DOM.
    await expect(page.getByText("Add link")).toHaveCount(0);

    await component.unmount();
  });

  test("renders the create header and selected-text chip", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="hello world"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );

    await expect(page.getByText("Add link")).toBeVisible({ timeout: 5000 });
    // The selected text is shown as context above the URL input.
    await expect(page.getByText("hello world")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Create link" })
    ).toBeVisible();

    await docScreenshot(page, "annotations--url-annotation--create-empty");

    await component.unmount();
  });

  test("renders the edit header and prefilled URL", async ({ mount, page }) => {
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        initialUrl="https://example.com/existing"
        onCancel={() => {}}
        onConfirm={() => {}}
      />
    );

    await expect(page.getByText("Edit link target")).toBeVisible({
      timeout: 5000,
    });
    // The save button label differs from the create variant.
    await expect(page.getByRole("button", { name: "Save link" })).toBeVisible();
    // The input is prefilled with the initialUrl.
    await expect(page.locator("#oc-url-input")).toHaveValue(
      "https://example.com/existing"
    );

    await docScreenshot(page, "annotations--url-annotation--edit-prefilled");

    await component.unmount();
  });

  test("rejects empty URL with inline error", async ({ mount, page }) => {
    let confirmed: string | null = null;
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        onCancel={() => {}}
        onConfirm={(url) => {
          confirmed = url;
        }}
      />
    );

    await expect(
      page.getByRole("button", { name: "Create link" })
    ).toBeVisible();
    await page.getByRole("button", { name: "Create link" }).click();

    await expect(page.getByText("URL is required.")).toBeVisible();
    // The callback must NOT have fired for an empty URL.
    expect(confirmed).toBeNull();

    await docScreenshot(page, "annotations--url-annotation--error-empty");

    await component.unmount();
  });

  test("rejects unsafe scheme with inline error", async ({ mount, page }) => {
    let confirmed: string | null = null;
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        onCancel={() => {}}
        onConfirm={(url) => {
          confirmed = url;
        }}
      />
    );

    await page.locator("#oc-url-input").fill("javascript:alert(1)");
    await page.getByRole("button", { name: "Create link" }).click();

    // Inline guidance mentions the allow-list.
    await expect(
      page.getByText(
        "URL must start with http://, https://, or '/' (site-relative path)."
      )
    ).toBeVisible();
    expect(confirmed).toBeNull();

    await component.unmount();
  });

  test("calls onConfirm with the trimmed URL on Create", async ({
    mount,
    page,
  }) => {
    let confirmed: string | null = null;
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        onCancel={() => {}}
        onConfirm={(url) => {
          confirmed = url;
        }}
      />
    );

    // Surrounding whitespace is stripped before validation/onConfirm.
    await page.locator("#oc-url-input").fill("  https://example.com/path  ");
    await page.getByRole("button", { name: "Create link" }).click();

    await expect.poll(() => confirmed).toBe("https://example.com/path");

    await component.unmount();
  });

  test("calls onConfirm when Enter is pressed in the input", async ({
    mount,
    page,
  }) => {
    let confirmed: string | null = null;
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        onCancel={() => {}}
        onConfirm={(url) => {
          confirmed = url;
        }}
      />
    );

    await page.locator("#oc-url-input").fill("https://example.com");
    await page.locator("#oc-url-input").press("Enter");

    await expect.poll(() => confirmed).toBe("https://example.com");

    await component.unmount();
  });

  test("calls onCancel when Cancel is clicked", async ({ mount, page }) => {
    let cancelled = false;
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        onCancel={() => {
          cancelled = true;
        }}
        onConfirm={() => {}}
      />
    );

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect.poll(() => cancelled).toBe(true);

    await component.unmount();
  });

  test("accepts site-relative paths", async ({ mount, page }) => {
    // The allow-list mirrors the backend: site-relative paths starting
    // with "/" are valid in addition to http(s) URLs.
    let confirmed: string | null = null;
    const component = await mount(
      <CreateUrlAnnotationModal
        visible={true}
        selectedText="anchor"
        onCancel={() => {}}
        onConfirm={(url) => {
          confirmed = url;
        }}
      />
    );

    await page.locator("#oc-url-input").fill("/corpus/foo/doc/bar");
    await page.getByRole("button", { name: "Create link" }).click();

    await expect.poll(() => confirmed).toBe("/corpus/foo/doc/bar");

    await component.unmount();
  });
});
