/**
 * Component tests for SuggestedQuestions — the cross-document question chip
 * card. This is a purely presentational component: no GraphQL, no providers
 * needed. It takes a single required prop ``onAskQuestion`` and renders one
 * clickable chip per entry in ``SUGGESTED_QUESTIONS``.
 *
 * NOTE: the JSX component import and the constant import are kept in SEPARATE
 * statements per the Playwright CT split-import rule (mixing a component with
 * helpers in one statement leaves the component unrewritten by Playwright CT's
 * babel transform, causing ``mount()`` to throw).
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { SuggestedQuestions } from "../src/components/corpuses/CorpusHome/intelligence/SuggestedQuestions";
import { SUGGESTED_QUESTIONS } from "../src/components/corpuses/CorpusHome/intelligence/SuggestedQuestions";

test.describe("SuggestedQuestions", () => {
  test("renders all chips and invokes the callback when one is clicked", async ({
    mount,
    page,
  }) => {
    const submitted: string[] = [];

    const component = await mount(
      <SuggestedQuestions
        onAskQuestion={(q) => {
          submitted.push(q);
        }}
      />
    );

    // At least the first question must be visible as a clickable chip.
    const firstQuestion = SUGGESTED_QUESTIONS[0];
    const chips = page.locator('[data-testid="ask-across-docs-suggestion"]');
    await expect(chips.first()).toBeVisible({ timeout: 10000 });

    // All chips are rendered — one per entry in SUGGESTED_QUESTIONS.
    await expect(chips).toHaveCount(SUGGESTED_QUESTIONS.length);

    // The chip text matches the exported constant.
    await expect(chips.first()).toContainText(firstQuestion);

    // Click the first chip and verify the callback fires with the right question.
    await chips.first().click();
    await expect.poll(() => submitted.length).toBeGreaterThan(0);
    expect(submitted[0]).toBe(firstQuestion);

    await docScreenshot(page, "corpus--suggested-questions--default");

    await component.unmount();
  });

  test("does not render the card when the callback is a no-op stub", async ({
    mount,
    page,
  }) => {
    // Smoke-test: the container renders even if the handler does nothing.
    const component = await mount(
      <SuggestedQuestions onAskQuestion={() => {}} />
    );

    await expect(
      page.locator('[data-testid="ask-across-docs-suggestions"]')
    ).toBeVisible({ timeout: 10000 });

    await component.unmount();
  });
});
