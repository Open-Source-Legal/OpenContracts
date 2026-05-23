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

test("submitting empty or whitespace-only text does not fire onSubmit", async ({
  mount,
}) => {
  let submitCount = 0;
  const c = await mount(
    <MobileAskBar
      onActivate={() => {}}
      onSubmit={() => {
        submitCount += 1;
      }}
    />
  );
  const input = c.getByPlaceholder(/ask anything/i);

  // Enter on an empty field — the `if (!trimmed) return` guard suppresses it.
  await input.press("Enter");
  // Whitespace-only input trims to "" and is likewise suppressed.
  await input.fill("   ");
  await input.press("Enter");
  // The send button on whitespace-only input is also a no-op.
  await c.getByRole("button", { name: "Send" }).click();

  expect(submitCount).toBe(0);
});

test("submitting via the send button trims the text and clears the input", async ({
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
  await input.fill("  hello there  ");
  await c.getByRole("button", { name: "Send" }).click();
  expect(sent).toBe("hello there");
  // The input is cleared after a successful submit.
  await expect(input).toHaveValue("");
});
