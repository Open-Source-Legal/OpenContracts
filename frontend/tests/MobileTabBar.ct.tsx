import { test, expect } from "./utils/coverage";
import { MobileTabBar } from "./MobileTabBar.harness";

test("renders all four tabs", async ({ mount }) => {
  const c = await mount(<MobileTabBar active="document" onSelect={() => {}} />);
  for (const t of ["Document", "Summary", "Annotations", "More"]) {
    await expect(c.getByRole("tab", { name: t })).toBeVisible();
  }
});

test("marks the active tab", async ({ mount }) => {
  const c = await mount(<MobileTabBar active="summary" onSelect={() => {}} />);
  await expect(c.getByRole("tab", { name: "Summary" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
});

test("clicking a tab fires onSelect with its id", async ({ mount }) => {
  let picked = "";
  const c = await mount(
    <MobileTabBar
      active="document"
      onSelect={(id) => {
        picked = id;
      }}
    />
  );
  await c.getByRole("tab", { name: "Annotations" }).click();
  expect(picked).toBe("annotations");
});
