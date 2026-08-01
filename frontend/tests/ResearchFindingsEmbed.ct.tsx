/**
 * Component tests for ResearchFindingsEmbed — the CAML embed that renders a
 * deep-research report's structured finding cards
 * (`[component:research-findings reportId=<global id>]`).
 *
 * Unlike its sibling embeds in this directory (AskAcrossDocsEmbed,
 * DocumentGraphEmbed, InsightPanelEmbed, CollectionDataStoryEmbed), this
 * component does NOT read CamlEmbedContext — `reportId` arrives as a plain
 * marker prop (see camlComponentRegistry.ts / camlComponents.ts), so no
 * CamlEmbedProvider is needed here.
 *
 * NOTE: the JSX-component import is kept in its own statement, separate from
 * helper/type imports from other modules, per the Playwright CT split-import
 * rule (mixing a component import with helpers in one statement leaves the
 * component unrewritten by Playwright's babel transform and mount() throws).
 */
import { test, expect } from "./utils/coverage";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { ResearchFindingsEmbed } from "../src/components/corpuses/CorpusHome/intelligence/embeds/ResearchFindingsEmbed";
import { GET_RESEARCH_REPORT } from "../src/graphql/queries";
import { toGlobalId } from "../src/utils/idValidation";
import { docScreenshot } from "./utils/docScreenshot";

const REPORT_ID = toGlobalId("ResearchReportType", 1);

/**
 * Builds a full `researchReport` payload matching GET_RESEARCH_REPORT's
 * selection set, with the given `findings` array substituted in. The embed
 * only reads `findings`, but MockedProvider responses mirror the real query
 * shape for realism (same convention as ResearchReportDetailTestWrapper's
 * buildMockReport).
 */
function buildReport(findings: unknown[]): Record<string, unknown> {
  return {
    id: REPORT_ID,
    status: "COMPLETED",
    prompt: "What interconnection regime governs this project over time?",
    title: "Interconnection Regime Review",
    slug: "interconnection-regime-review",
    content: "## Summary\n\nSee findings above.",
    findings,
    citations: [],
    toolCallLog: [],
    modelUsage: {},
    warnings: [],
    durationSeconds: 42,
    stepCount: 5,
    maxSteps: 30,
    cancelRequested: false,
    errorMessage: "",
    created: "2026-07-11T12:00:00Z",
    modified: "2026-07-11T12:05:00Z",
    startedAt: "2026-07-11T12:00:05Z",
    completedAt: "2026-07-11T12:05:00Z",
    lastProgressAt: "2026-07-11T12:05:00Z",
    myPermissions: ["read_researchreport"],
    corpus: null,
    fullSourceAnnotationList: [],
    fullSourceDocumentList: [],
  };
}

function reportMock(findings: unknown[]): MockedResponse {
  return {
    request: { query: GET_RESEARCH_REPORT, variables: { id: REPORT_ID } },
    result: { data: { researchReport: buildReport(findings) } },
  };
}

test.describe("ResearchFindingsEmbed", () => {
  test("renders nothing without a reportId", async ({ mount, page }) => {
    const component = await mount(
      <MockedProvider mocks={[]} addTypename={false}>
        <ResearchFindingsEmbed />
      </MockedProvider>
    );

    // No reportId -> the query is skipped and the embed short-circuits to
    // null before ever reading `data`.
    await expect(page.locator('[data-testid="research-findings"]')).toHaveCount(
      0
    );

    await component.unmount();
  });

  test("renders nothing when the report has no qualifying findings", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[
          reportMock([
            // Scratchpad entries without a `card` (or an empty card) are not
            // findings cards and must be filtered out.
            {
              section: "Background",
              claim: "Some context claim.",
              citations: [1],
            },
            {
              section: "Aside",
              claim: "Unstructured note.",
              citations: [],
              card: null,
            },
          ]),
        ]}
        addTypename={false}
      >
        <ResearchFindingsEmbed reportId={REPORT_ID} />
      </MockedProvider>
    );

    // Give the query a chance to resolve before asserting absence, so this
    // proves the empty-cards path (not just an unresolved query).
    await page.waitForTimeout(700);
    await expect(page.locator('[data-testid="research-findings"]')).toHaveCount(
      0
    );

    await component.unmount();
  });

  test("renders REGIME finding cards with open/closed intervals and qualifications", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[
          reportMock([
            {
              section: "Solar Interconnection",
              claim: "The current SGIP regime governs as of the report date.",
              citations: [1, 2],
              card: {
                kind: "REGIME",
                as_of_date: "2026-07-11",
                applicable_process: "Small Generator Interconnection Procedure",
                authority_status: "In effect",
                effective_interval_start: "2026-07-11",
                effective_interval_end: null,
                primary_authority_effective_from: "2026-07-01",
                confidence: "HIGH",
                unresolved_qualifications: [
                  "Awaiting PUC docket confirmation",
                  "Local ordinance pending",
                ],
              },
            },
            {
              section: "Prior Regime",
              claim: "The prior procedure governed through the 10th.",
              citations: [3],
              card: {
                kind: "REGIME",
                as_of_date: "2026-07-10",
                applicable_process: "Prior Interconnection Procedure",
                authority_status: "Superseded",
                effective_interval_start: null,
                effective_interval_end: "2026-07-11",
                primary_authority_effective_from: null,
                confidence: "MEDIUM",
                unresolved_qualifications: [],
              },
            },
          ]),
        ]}
        addTypename={false}
      >
        <ResearchFindingsEmbed reportId={REPORT_ID} />
      </MockedProvider>
    );

    const wrap = page.locator('[data-testid="research-findings"]');
    await expect(wrap).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="finding-card"]')).toHaveCount(2);

    // Card A: open interval (no end), qualifications present, and the
    // authority-effective-from row rendered.
    await expect(wrap).toContainText(
      "Small Generator Interconnection Procedure"
    );
    await expect(
      page.locator('[data-testid="finding-interval"]').first()
    ).toHaveText("[2026-07-11, …)");
    await expect(wrap).toContainText("Awaiting PUC docket confirmation");
    await expect(wrap).toContainText("2026-07-01");

    // Card B: unestablished start, closed end, no qualifications -> "None
    // stated", and no authority-effective-from row (field is null).
    await expect(wrap).toContainText("Prior Interconnection Procedure");
    await expect(
      page.locator('[data-testid="finding-interval"]').nth(1)
    ).toHaveText("[unestablished, 2026-07-11)");
    await expect(wrap).toContainText("None stated.");

    await docScreenshot(page, "caml--research-findings-embed--regime-cards");

    await component.unmount();
  });

  test("renders OBLIGATION finding cards with and without optional fields", async ({
    mount,
    page,
  }) => {
    const component = await mount(
      <MockedProvider
        mocks={[
          reportMock([
            {
              section: "Reporting",
              claim: "Annual compliance filing is owed by the grid operator.",
              citations: [4],
              card: {
                kind: "OBLIGATION",
                obligation: "File annual interconnection compliance report",
                owed_by: "Grid Operator",
                form_reference: "Form IC-7",
                deadline: "Annually by March 31",
                confidence: "HIGH",
                unresolved_qualifications: ["Pending confirmation from ERCOT"],
              },
            },
            {
              section: "Insurance",
              claim: "Ongoing insurance coverage is owed by the developer.",
              citations: [5],
              card: {
                // No `kind` field — isObligation must fall back to
                // `!!card.obligation`. `unresolved_qualifications` is also
                // omitted entirely (not just empty) to exercise the `??`
                // fallback to `[]`, as distinct from card A/B's
                // explicit-empty-array case.
                obligation: "Maintain interconnection insurance",
                owed_by: "Developer",
                form_reference: null,
                deadline: null,
                confidence: "LOW",
              },
            },
          ]),
        ]}
        addTypename={false}
      >
        <ResearchFindingsEmbed reportId={REPORT_ID} />
      </MockedProvider>
    );

    const wrap = page.locator('[data-testid="research-findings"]');
    await expect(wrap).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="finding-card"]')).toHaveCount(2);

    // Card C: form reference + deadline both present.
    await expect(
      page.locator('[data-testid="finding-obligation"]').first()
    ).toHaveText("File annual interconnection compliance report");
    await expect(
      page.locator('[data-testid="finding-form"]').first()
    ).toHaveText("Form IC-7");
    await expect(
      page.locator('[data-testid="finding-deadline"]').first()
    ).toHaveText("Annually by March 31");
    await expect(wrap).toContainText("Pending confirmation from ERCOT");

    // Card D: no `kind`, no form reference, no deadline, no qualifications.
    await expect(
      page.locator('[data-testid="finding-obligation"]').nth(1)
    ).toHaveText("Maintain interconnection insurance");
    await expect(page.locator('[data-testid="finding-form"]')).toHaveCount(1); // only card C's
    await expect(page.locator('[data-testid="finding-deadline"]')).toHaveCount(
      1
    ); // only card C's

    await docScreenshot(
      page,
      "caml--research-findings-embed--obligation-cards"
    );

    await component.unmount();
  });
});
