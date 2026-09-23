import type { Page } from "@playwright/test";
import { test, expect } from "./utils/coverage";
import { AnnotationVersionReviewTestWrapper } from "./AnnotationVersionReviewTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

const row = (page: Page, text: string) =>
  page.locator("article").filter({ hasText: text });

test("machine-carried and unplaced annotations stay flagged until a person decides", async ({
  mount,
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 1400 });
  await mount(<AnnotationVersionReviewTestWrapper />);
  const versionPill = page.getByRole("button", { name: /Version 2/ });
  await expect(versionPill).toContainText("3 to review");
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();

  const pay = row(page, "Pay promptly.");
  const notify = row(page, "Notify the owner.");
  await expect(pay).toContainText("Auto-carried · unreviewed");
  await expect(notify).toContainText("Needs placement");
  await expect(notify.getByRole("button", { name: "Approve" })).toBeDisabled();
  await docScreenshot(page, "versioning--annotation-review--stale", {
    element: page.getByRole("region", { name: "Annotation version review" }),
  });

  await pay.getByRole("button", { name: "Approve" }).click();
  await expect(pay).toContainText("Approved");
  await expect(pay).toContainText("Reviewed by reviewer");

  await notify.getByRole("button", { name: "Place" }).click();
  await page.getByRole("button", { name: "Select corrected passage" }).click();
  const placement = page.getByLabel("Submitted placement");
  await expect(placement).toContainText('"annotationId":"old-1"');
  await expect(placement).toContainText('"json":{"start":28,"end":49');
  await expect(
    page.getByRole("list", { name: "Saved annotations" })
  ).toContainText("Notify the new owner.");
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  await expect(notify).toContainText("Corrected");
  await expect(notify).toContainText("Now: Notify the new owner.");

  await row(page, "Removed clause.")
    .getByRole("button", { name: "Drop" })
    .click();
  await expect(row(page, "Removed clause.")).toContainText("Dropped");
  await expect(versionPill).not.toContainText("to review");
});

test("dropping an auto-carried annotation removes it from the viewer", async ({
  mount,
  page,
}) => {
  await mount(<AnnotationVersionReviewTestWrapper />);
  const saved = page.getByRole("list", { name: "Saved annotations" });
  await expect(saved).toContainText("Pay promptly.");
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  await row(page, "Pay promptly.")
    .getByRole("button", { name: "Drop" })
    .click();
  await expect(row(page, "Pay promptly.")).toContainText("Dropped");
  await expect(saved.getByRole("listitem")).toHaveCount(0);
});

test("a rejected placement remains pending and never appears as a saved annotation", async ({
  mount,
  page,
}) => {
  await mount(<AnnotationVersionReviewTestWrapper rejectPlacement />);
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  await row(page, "Notify the owner.")
    .getByRole("button", { name: "Place" })
    .click();
  await page.getByRole("button", { name: "Select corrected passage" }).click();
  await expect(page.getByLabel("Submitted placement")).toContainText("old-1");
  await expect(
    page.getByRole("status", { name: "Annotation placement" })
  ).toContainText("Select the corrected passage");
  await expect(
    page.getByRole("list", { name: "Saved annotations" })
  ).not.toContainText("Notify the new owner.");
  await page.getByRole("button", { name: "Cancel placement" }).click();
  await expect(
    page.getByRole("button", { name: "Select corrected passage" })
  ).toHaveCount(0);
});

test("read-only viewers can inspect the review but cannot decide", async ({
  mount,
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mount(<AnnotationVersionReviewTestWrapper readOnly />);
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  await expect(
    page.getByText(
      "Update permission on this document and corpus is required to review."
    )
  ).toBeVisible();
  for (const action of ["Approve", "Place", "Drop"]) {
    await expect(
      page.locator("article").first().getByRole("button", { name: action })
    ).toBeDisabled();
  }
  const review = page.getByRole("region", {
    name: "Annotation version review",
  });
  expect((await review.boundingBox())!.width).toBeLessThanOrEqual(390);
  await review.screenshot({ path: testInfo.outputPath("review-mobile.png") });
});
