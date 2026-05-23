import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MobileAskBar } from "./MobileAskBar.harness";

test("renders the prompt", async ({ mount }) => {
  const c = await mount(<MobileAskBar onSubmit={() => {}} />);
  await expect(c.getByPlaceholder(/ask anything/i)).toBeVisible();
});

test("focusing the input does not auto-open the chat sheet", async ({
  mount,
}) => {
  // The bar used to fire `onActivate` on focus, which the layout used to open
  // the chat sheet. That hop covered the bar before the user could type — now
  // focus is a no-op so users can compose their message inline on the main
  // view and submit only when they're ready.
  let submitCount = 0;
  let historyCount = 0;
  const c = await mount(
    <MobileAskBar
      onSubmit={() => (submitCount += 1)}
      onOpenHistory={() => (historyCount += 1)}
    />
  );
  await c.getByPlaceholder(/ask anything/i).focus();
  expect(submitCount).toBe(0);
  expect(historyCount).toBe(0);
});

test("submitting non-empty text fires onSubmit with the text", async ({
  mount,
}) => {
  let sent = "";
  const c = await mount(
    <MobileAskBar
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

test("the history button is only rendered when onOpenHistory is provided", async ({
  mount,
}) => {
  const withoutHistory = await mount(<MobileAskBar onSubmit={() => {}} />);
  await expect(
    withoutHistory.getByRole("button", { name: /open conversation history/i })
  ).toHaveCount(0);

  await withoutHistory.unmount();

  const withHistory = await mount(
    <MobileAskBar onSubmit={() => {}} onOpenHistory={() => {}} />
  );
  await expect(
    withHistory.getByRole("button", { name: /open conversation history/i })
  ).toBeVisible();
});

test("clicking the history button fires onOpenHistory", async ({
  mount,
  page,
}) => {
  let historyCount = 0;
  const c = await mount(
    <MobileAskBar
      onSubmit={() => {}}
      onOpenHistory={() => (historyCount += 1)}
    />
  );
  await c.getByRole("button", { name: /open conversation history/i }).click();
  expect(historyCount).toBe(1);

  await docScreenshot(page, "dkb--mobile--ask-bar-with-history");
});
