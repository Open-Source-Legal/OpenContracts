import { test, expect } from "./utils/coverage";
import { MobileSheet } from "./MobileSheet.harness";

test("renders title and content when open", async ({ mount }) => {
  const c = await mount(
    <MobileSheet open title="Chat" onClose={() => {}}>
      <div>sheet-body</div>
    </MobileSheet>
  );
  await expect(c.getByText("Chat")).toBeVisible();
  await expect(c.getByText("sheet-body")).toBeVisible();
});

test("does not render content when closed", async ({ mount }) => {
  const c = await mount(
    <MobileSheet open={false} title="Chat" onClose={() => {}}>
      <div>sheet-body</div>
    </MobileSheet>
  );
  await expect(c.getByText("sheet-body")).toHaveCount(0);
});

test("close button fires onClose", async ({ mount }) => {
  let closed = false;
  const c = await mount(
    <MobileSheet
      open
      title="Chat"
      onClose={() => {
        closed = true;
      }}
    >
      <div>x</div>
    </MobileSheet>
  );
  await c.getByRole("button", { name: /close/i }).click();
  expect(closed).toBe(true);
});
