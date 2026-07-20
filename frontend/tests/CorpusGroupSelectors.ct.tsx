import React from "react";
import { test, expect } from "./utils/coverage";
import type { Page } from "@playwright/test";
// Split-import rule (CLAUDE.md pitfall #16): the two mounted wrappers get their
// own import statement, kept apart from the constant imports below.
import {
  CorpusMultiSelectTestWrapper,
  AgentConfigurationSelectTestWrapper,
} from "./CorpusGroupSelectorsTestWrapper";
import {
  CORPUS_INPUT_ID,
  AGENT_INPUT_ID,
  CORPUS_SELECTION_TESTID,
  CORPUS_CHANGE_COUNT_TESTID,
  AGENT_SELECTION_TESTID,
  AGENT_CHANGE_COUNT_TESTID,
} from "./CorpusGroupSelectorsTestWrapper";
import {
  CORPUS_ID_MSA,
  CORPUS_ID_NDA,
  CORPUS_ID_ARCHIVE,
  CORPUS_TITLE_MSA,
  CORPUS_TITLE_NDA,
  CORPUS_TITLE_LEASES,
  CORPUS_TITLE_ARCHIVE,
  CORPUS_SEARCH_TERM,
  AGENT_ID_REVIEWER,
  AGENT_ID_LEGACY,
  AGENT_NAME_ANALYST,
  AGENT_NAME_REVIEWER,
  AGENT_NAME_LEGACY,
  AGENT_SEARCH_TERM,
} from "./CorpusGroupPickerFixtures";

/**
 * Both pickers render react-select through the shared ``Select`` wrapper, which
 * pins ``classNamePrefix="react-select"``. Scoping every lookup to the widget's
 * own ``data-testid`` matters once these are driven inside the corpus-group
 * form modal, where two react-selects sit side by side.
 */
const CORPUS_ROOT = "corpus-multi-select";
const AGENT_ROOT = "agent-configuration-select";

const control = (page: Page, root: string) =>
  page.getByTestId(root).locator(".react-select__control");

const options = (page: Page, root: string) =>
  page.getByTestId(root).locator(".react-select__option");

/**
 * Open the menu and type a term.
 *
 * ``fill`` rather than a keystroke sequence: the widgets debounce on
 * ``input-change`` with a 400ms trailing timer, so a per-character sequence
 * would leave the fate of the intermediate terms up to typing speed. One fill
 * emits exactly one ``input-change`` carrying the whole term, which is the
 * thing the debounce is supposed to forward.
 */
const search = async (
  page: Page,
  root: string,
  inputId: string,
  term: string
) => {
  await control(page, root).click();
  await page.locator(`#${inputId}`).fill(term);
};

test.describe("CorpusGroupSelectors", () => {
  /* ------------------------------------------------------------------ */
  /* CorpusMultiSelect                                                   */
  /* ------------------------------------------------------------------ */

  test.describe("CorpusMultiSelect", () => {
    /**
     * The load-bearing seed guarantee. ``CORPUS_TITLE_ARCHIVE`` appears in NO
     * mocked search result, so a chip for it can only have come from the
     * ``value`` prop. Regressing this — deriving chips from the search results
     * — would silently drop membership the moment an edit form opened on a
     * corpus outside the first page of results.
     */
    test("renders seeded chips immediately without performing a search", async ({
      mount,
      page,
    }) => {
      await mount(
        <CorpusMultiSelectTestWrapper
          initialValue={[
            { id: CORPUS_ID_ARCHIVE, title: CORPUS_TITLE_ARCHIVE },
          ]}
        />
      );

      await expect(
        page.getByTestId(CORPUS_ROOT).getByText(CORPUS_TITLE_ARCHIVE)
      ).toBeVisible({ timeout: 20000 });
      // The seed reached the DOM without onChange ever firing, and the search
      // box is untouched.
      await expect(page.getByTestId(CORPUS_CHANGE_COUNT_TESTID)).toHaveText(
        "0"
      );
      await expect(page.locator(`#${CORPUS_INPUT_ID}`)).toHaveValue("");
      await expect(page.getByTestId(CORPUS_SELECTION_TESTID)).toHaveText(
        JSON.stringify([{ id: CORPUS_ID_ARCHIVE, title: CORPUS_TITLE_ARCHIVE }])
      );
    });

    test("typing runs a debounced server search and selecting emits {id, title}", async ({
      mount,
      page,
    }) => {
      await mount(<CorpusMultiSelectTestWrapper />);

      await search(page, CORPUS_ROOT, CORPUS_INPUT_ID, CORPUS_SEARCH_TERM);

      // Only the ``textSearch: "nda"`` mock returns this single-row set, so
      // seeing exactly one option proves the debounce forwarded the term into
      // the query variables.
      await expect(options(page, CORPUS_ROOT)).toHaveCount(1, {
        timeout: 20000,
      });
      await expect(options(page, CORPUS_ROOT)).toHaveText(CORPUS_TITLE_NDA);

      await options(page, CORPUS_ROOT).first().click();

      await expect(page.getByTestId(CORPUS_SELECTION_TESTID)).toHaveText(
        JSON.stringify([{ id: CORPUS_ID_NDA, title: CORPUS_TITLE_NDA }]),
        { timeout: 20000 }
      );
      await expect(page.getByTestId(CORPUS_CHANGE_COUNT_TESTID)).toHaveText(
        "1"
      );
    });

    /**
     * The search-reset contract. react-select clears its own (uncontrolled)
     * input on ``set-value``/``menu-close``; the widget mirrors that into
     * ``searchQuery``. Without it the box reads empty while the menu stays
     * filtered by the previous term, which looks like missing results.
     */
    test("reopening the menu after a selection shows the unfiltered list", async ({
      mount,
      page,
    }) => {
      await mount(<CorpusMultiSelectTestWrapper />);

      await search(page, CORPUS_ROOT, CORPUS_INPUT_ID, CORPUS_SEARCH_TERM);
      await expect(options(page, CORPUS_ROOT)).toHaveCount(1, {
        timeout: 20000,
      });
      await options(page, CORPUS_ROOT).first().click();
      await expect(page.getByTestId(CORPUS_SELECTION_TESTID)).toHaveText(
        JSON.stringify([{ id: CORPUS_ID_NDA, title: CORPUS_TITLE_NDA }]),
        { timeout: 20000 }
      );

      // Escape guarantees a closed menu regardless of react-select's
      // closeMenuOnSelect default, so the reopen below is unambiguous.
      await page.locator(`#${CORPUS_INPUT_ID}`).press("Escape");
      await control(page, CORPUS_ROOT).click();

      // Both of these were absent while "nda" was the active term. The already
      // selected NDA is hidden by react-select's hideSelectedOptions.
      await expect(
        options(page, CORPUS_ROOT).filter({ hasText: CORPUS_TITLE_MSA })
      ).toBeVisible({ timeout: 20000 });
      await expect(
        options(page, CORPUS_ROOT).filter({ hasText: CORPUS_TITLE_LEASES })
      ).toBeVisible({ timeout: 20000 });
    });

    test("removing a chip emits the remaining corpora", async ({
      mount,
      page,
    }) => {
      await mount(
        <CorpusMultiSelectTestWrapper
          initialValue={[
            { id: CORPUS_ID_MSA, title: CORPUS_TITLE_MSA },
            { id: CORPUS_ID_NDA, title: CORPUS_TITLE_NDA },
          ]}
        />
      );

      await expect(
        page.getByTestId(CORPUS_ROOT).locator(".react-select__multi-value")
      ).toHaveCount(2, { timeout: 20000 });

      await page
        .getByTestId(CORPUS_ROOT)
        .locator(".react-select__multi-value")
        .filter({ hasText: CORPUS_TITLE_NDA })
        .locator(".react-select__multi-value__remove")
        .click();

      // Membership is REPLACED by consumers, so the survivor set — not a delta
      // — is what has to come back out.
      await expect(page.getByTestId(CORPUS_SELECTION_TESTID)).toHaveText(
        JSON.stringify([{ id: CORPUS_ID_MSA, title: CORPUS_TITLE_MSA }]),
        { timeout: 20000 }
      );
      await expect(page.getByTestId(CORPUS_CHANGE_COUNT_TESTID)).toHaveText(
        "1"
      );
    });

    test("renders disabled when the disabled prop is set", async ({
      mount,
      page,
    }) => {
      await mount(<CorpusMultiSelectTestWrapper disabled />);

      await expect(page.locator(`#${CORPUS_INPUT_ID}`)).toBeDisabled({
        timeout: 20000,
      });
      await expect(
        page
          .getByTestId(CORPUS_ROOT)
          .locator(".react-select__control--is-disabled")
      ).toBeVisible();
    });
  });

  /* ------------------------------------------------------------------ */
  /* AgentConfigurationSelect                                            */
  /* ------------------------------------------------------------------ */

  test.describe("AgentConfigurationSelect", () => {
    /** Seed guarantee — see the CorpusMultiSelect equivalent. */
    test("renders a seeded agent immediately without performing a search", async ({
      mount,
      page,
    }) => {
      await mount(
        <AgentConfigurationSelectTestWrapper
          initialValue={{ id: AGENT_ID_LEGACY, name: AGENT_NAME_LEGACY }}
        />
      );

      await expect(
        page.getByTestId(AGENT_ROOT).getByText(AGENT_NAME_LEGACY)
      ).toBeVisible({ timeout: 20000 });
      await expect(page.getByTestId(AGENT_CHANGE_COUNT_TESTID)).toHaveText("0");
      await expect(page.locator(`#${AGENT_INPUT_ID}`)).toHaveValue("");
    });

    test("typing runs a debounced server search and selecting emits {id, name}", async ({
      mount,
      page,
    }) => {
      await mount(<AgentConfigurationSelectTestWrapper />);

      await search(page, AGENT_ROOT, AGENT_INPUT_ID, AGENT_SEARCH_TERM);

      await expect(options(page, AGENT_ROOT)).toHaveCount(1, {
        timeout: 20000,
      });
      await expect(options(page, AGENT_ROOT)).toHaveText(AGENT_NAME_REVIEWER);

      await options(page, AGENT_ROOT).first().click();

      await expect(page.getByTestId(AGENT_SELECTION_TESTID)).toHaveText(
        JSON.stringify({ id: AGENT_ID_REVIEWER, name: AGENT_NAME_REVIEWER }),
        { timeout: 20000 }
      );
      await expect(page.getByTestId(AGENT_CHANGE_COUNT_TESTID)).toHaveText("1");
    });

    /**
     * Clearing must emit ``null`` rather than simply leaving the previous
     * binding in place — ``CorpusGroupManagement`` translates exactly this into
     * ``clearDefaultAgent: true``, so a clear that emitted nothing would make
     * the unbind button a silent no-op.
     */
    test("clearing the selection emits null", async ({ mount, page }) => {
      await mount(
        <AgentConfigurationSelectTestWrapper
          initialValue={{ id: AGENT_ID_LEGACY, name: AGENT_NAME_LEGACY }}
        />
      );

      await page
        .getByTestId(AGENT_ROOT)
        .locator(".react-select__clear-indicator")
        .click();

      await expect(page.getByTestId(AGENT_SELECTION_TESTID)).toHaveText(
        "null",
        { timeout: 20000 }
      );
      // The counter is what separates "emitted null" from "never fired" — both
      // leave the same rendered value.
      await expect(page.getByTestId(AGENT_CHANGE_COUNT_TESTID)).toHaveText("1");
    });

    test("reopening the menu after a selection shows the unfiltered list", async ({
      mount,
      page,
    }) => {
      await mount(<AgentConfigurationSelectTestWrapper />);

      await search(page, AGENT_ROOT, AGENT_INPUT_ID, AGENT_SEARCH_TERM);
      await expect(options(page, AGENT_ROOT)).toHaveCount(1, {
        timeout: 20000,
      });
      await options(page, AGENT_ROOT).first().click();
      await expect(page.getByTestId(AGENT_SELECTION_TESTID)).toHaveText(
        JSON.stringify({ id: AGENT_ID_REVIEWER, name: AGENT_NAME_REVIEWER }),
        { timeout: 20000 }
      );

      await page.locator(`#${AGENT_INPUT_ID}`).press("Escape");
      await control(page, AGENT_ROOT).click();

      // Absent while "reviewer" was the active term.
      await expect(
        options(page, AGENT_ROOT).filter({ hasText: AGENT_NAME_ANALYST })
      ).toBeVisible({ timeout: 20000 });
    });

    test("renders disabled when the disabled prop is set", async ({
      mount,
      page,
    }) => {
      await mount(<AgentConfigurationSelectTestWrapper disabled />);

      await expect(page.locator(`#${AGENT_INPUT_ID}`)).toBeDisabled({
        timeout: 20000,
      });
      await expect(
        page
          .getByTestId(AGENT_ROOT)
          .locator(".react-select__control--is-disabled")
      ).toBeVisible();
    });
  });
});
