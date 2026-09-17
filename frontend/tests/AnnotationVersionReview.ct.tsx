import { test, expect } from "./utils/coverage";
import { AnnotationVersionReviewTestWrapper } from "./AnnotationVersionReviewTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";

test("reviews unchanged, corrected and removed text and updates the version badge", async ({
  mount,
  page,
}) => {
  await page.setViewportSize({ width: 800, height: 1400 });
  await mount(<AnnotationVersionReviewTestWrapper />);
  await expect(page.getByRole("button", { name: /Version 2/ })).toContainText(
    "3 stale"
  );
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  const pay = page.locator("article").filter({ hasText: "Pay promptly." });
  await expect(pay).toBeVisible();
  await docScreenshot(page, "versioning--annotation-review--stale", {
    element: page.getByRole("region", { name: "Annotation version review" }),
  });
  await pay.getByRole("button", { name: "Approve" }).click();
  await expect(pay).toContainText("Re-approved");
  const notify = page
    .locator("article")
    .filter({ hasText: "Notify the owner." });
  await expect(notify.getByRole("button", { name: "Approve" })).toBeDisabled();
  await notify.getByRole("button", { name: "Place" }).click();
  await expect(
    page.getByRole("status", { name: "Annotation placement" })
  ).toContainText("Select the corrected passage");
  await page.getByRole("button", { name: "Select corrected passage" }).click();
  await expect(
    page.getByRole("list", { name: "Saved annotations" })
  ).toContainText("Notify the new owner.");
  await expect(page.getByLabel("Submitted placement")).toContainText(
    '"annotationId":"old-1"'
  );
  await expect(page.getByLabel("Submitted placement")).toContainText(
    '"json":{"start":28,"end":49'
  );
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  await expect(notify).toContainText("Corrected");
  await page
    .locator("article")
    .filter({ hasText: "Removed clause." })
    .getByRole("button", { name: "Drop" })
    .click();
  await expect(
    page.locator("article").filter({ hasText: "Removed clause." })
  ).toContainText("Dropped");
  await expect(
    page.getByRole("button", { name: /Version 2/ })
  ).not.toContainText("stale");
});

test("a rejected placement remains pending and never appears as a saved annotation", async ({
  mount,
  page,
}) => {
  await mount(<AnnotationVersionReviewTestWrapper rejectPlacement />);
  await page.getByRole("button", { name: /Carried-over annotations/ }).click();
  await page
    .locator("article")
    .filter({ hasText: "Notify the owner." })
    .getByRole("button", { name: "Place" })
    .click();
  await page.getByRole("button", { name: "Select corrected passage" }).click();
  await expect(page.getByLabel("Submitted placement")).toContainText("old-1");
  await expect(
    page.getByRole("status", { name: "Annotation placement" })
  ).toContainText("Select the corrected passage");
  await expect(
    page.getByRole("list", { name: "Saved annotations" }).getByRole("listitem")
  ).toHaveCount(0);
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
