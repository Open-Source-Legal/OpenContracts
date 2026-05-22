import { test, expect } from "./utils/coverage";
import { MobileAskBar } from "./MobileAskBar.harness";

test("renders the prompt", async ({ mount }) => {
  const c = await mount(
    <MobileAskBar onActivate={() => {}} onSubmit={() => {}} />
  );
  await expect(c.getByPlaceholder(/ask anything/i)).toBeVisible();
});

test("focusing the input fires onActivate", async ({ mount }) => {
  let activated = false;
  const c = await mount(
    <MobileAskBar
      onActivate={() => {
        activated = true;
      }}
      onSubmit={() => {}}
    />
  );
  await c.getByPlaceholder(/ask anything/i).focus();
  expect(activated).toBe(true);
});

test("submitting non-empty text fires onSubmit with the text", async ({
  mount,
}) => {
  let sent = "";
  const c = await mount(
    <MobileAskBar
      onActivate={() => {}}
      onSubmit={(t) => {
        sent = t;
      }}
    />
  );
  const input = c.getByPlaceholder(/ask anything/i);
  await input.fill("what year?");
  await input.press("Enter");
  expect(sent).toBe("what year?");
});
