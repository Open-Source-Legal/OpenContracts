import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MobileDocToolbar } from "./MobileDocToolbar.harness";

test("renders the three controls", async ({ mount, page }) => {
  const c = await mount(
    <MobileDocToolbar
      zoomPercent={100}
      onSections={() => {}}
      onFind={() => {}}
      onFitWidth={() => {}}
    />
  );
  await expect(c.getByRole("button", { name: /sections/i })).toBeVisible();
  await expect(c.getByRole("button", { name: /find/i })).toBeVisible();
  await expect(c.getByRole("button", { name: /fit width/i })).toBeVisible();
  await docScreenshot(page, "annotations--mobile-doc-toolbar--floating-pill");
});

test("buttons fire their callbacks", async ({ mount }) => {
  const hits: string[] = [];
  const c = await mount(
    <MobileDocToolbar
      zoomPercent={100}
      onSections={() => hits.push("s")}
      onFind={() => hits.push("f")}
      onFitWidth={() => hits.push("z")}
    />
  );
  await c.getByRole("button", { name: /sections/i }).click();
  await c.getByRole("button", { name: /find/i }).click();
  await c.getByRole("button", { name: /fit width/i }).click();
  expect(hits).toEqual(["s", "f", "z"]);
});
