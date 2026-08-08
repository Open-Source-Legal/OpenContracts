/**
 * ResearchFindingsEmbed — CAML embed for a deep-research report's finding cards.
 *
 * Marker: ``[component:research-findings reportId=<global id>]``, emitted by
 * ``ResearchReportService.finalize`` when the run recorded any structured
 * finding. It renders above the prose, so the article opens with the
 * high-level takeaway and the written report follows.
 *
 * Reads the report's own ``findings`` through the existing report query — a
 * card does not serialise into marker props, which are strings only.
 *
 * Intervals render half-open: `[2026-07-11, …)`. The end is EXCLUSIVE, which
 * is load-bearing — a rule superseded on the 11th governed all of the 10th,
 * and an inclusive end lets both regimes claim the boundary day.
 */
import React from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";

import {
  GET_RESEARCH_REPORT,
  GetResearchReportInput,
  GetResearchReportOutput,
} from "../../../../../graphql/queries";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

/** The structured half of a finding, written by ``record_finding``.
 *
 * Two shapes share this payload — a REGIME card answers "what governed when"
 * and is built around a half-open interval; an OBLIGATION card answers "what
 * must this project do" and has no interval at all. ``kind`` discriminates.
 */
interface FindingCardData {
  kind?: "REGIME" | "OBLIGATION";
  // Obligation shape. Field names mirror `ObligationCard` /`RegimeCard` in
  // opencontractserver/enrichment/finding_cards.py EXACTLY — the stored card
  // is that model's `model_dump()`, so a name that drifts from it reads
  // `undefined` in production while a hand-authored mock keeps the tests
  // green. `test_finding_cards.py` pins the field sets against this list.
  obligation?: string;
  responsible_party?: string;
  obligor_grounded?: boolean;
  form_reference?: string | null;
  deadline?: string | null;
  // Regime shape
  as_of_date?: string;
  applicable_process?: string;
  authority_status?: string;
  effective_interval_start?: string | null;
  effective_interval_end?: string | null;
  primary_authority_effective_from?: string | null;
  confidence?: string;
  unresolved_qualifications?: string[];
}

interface FindingEntry {
  claim?: string;
  section?: string;
  citations?: number[];
  card?: FindingCardData;
}

const Wrap = styled.section`
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  margin: 0 0 1.5rem;
`;

const Heading = styled.h3`
  margin: 0;
  font-size: 0.78rem;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--oc-fg-tertiary, #6b7280);
`;

const Cards = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 0.85rem;
`;

const Card = styled.article`
  border: 1px solid var(--oc-border-default, #d4d9df);
  border-left: 3px solid ${OS_LEGAL_COLORS.accent};
  border-radius: 6px;
  padding: 0.9rem 1.05rem;
  background: var(--oc-bg-surface, #fff);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;

  h4 {
    margin: 0;
    font-size: 0.98rem;
    font-variant-numeric: tabular-nums;
  }

  dl {
    margin: 0;
    display: grid;
    grid-template-columns: minmax(8rem, max-content) 1fr;
    gap: 0.28rem 0.9rem;
    font-size: 0.85rem;
  }
  dt {
    color: var(--oc-fg-secondary, #5a6674);
  }
  dd {
    margin: 0;
  }

  code {
    font-size: 0.79rem;
  }

  ul {
    margin: 0.1rem 0 0;
    padding-left: 1.05rem;
    font-size: 0.84rem;
  }
`;

const InferredTag = styled.span`
  margin-left: 0.5rem;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  vertical-align: middle;
  color: var(--oc-fg-secondary, #5a6674);
  background: var(--oc-bg-subtle, #f1f3f5);
  border: 1px solid var(--oc-border-default, #d4d9df);
`;

/** Half-open notation. `unestablished` is deliberate, not a placeholder. */
function renderInterval(card: FindingCardData): string {
  const start = card.effective_interval_start || "unestablished";
  const end = card.effective_interval_end || "…";
  return `[${start}, ${end})`;
}

export const ResearchFindingsEmbed: React.FC<
  Record<string, string | undefined>
> = ({ reportId }) => {
  const { data } = useQuery<GetResearchReportOutput, GetResearchReportInput>(
    GET_RESEARCH_REPORT,
    { variables: { id: reportId as string }, skip: !reportId }
  );

  if (!reportId) return null;

  const findings = (data?.researchReport?.findings ??
    []) as unknown as FindingEntry[];
  // A card is anything carrying either shape's required field, so an
  // obligation card is not silently dropped by a regime-only test.
  const cards = findings.filter(
    (f) => f?.card?.as_of_date || f?.card?.obligation
  );
  if (cards.length === 0) return null;

  return (
    <Wrap data-testid="research-findings">
      <Heading>Findings</Heading>
      <Cards>
        {cards.map((entry, i) => {
          const card = entry.card as FindingCardData;
          const isObligation = card.kind === "OBLIGATION" || !!card.obligation;
          const qualifications = card.unresolved_qualifications ?? [];
          return (
            <Card
              key={`${card.as_of_date ?? card.obligation}-${i}`}
              data-testid="finding-card"
            >
              <h4 data-testid="finding-heading">
                {isObligation ? card.responsible_party : card.as_of_date}
                {/* An obligor the cited passages never NAME is an attribution
                    carried in from elsewhere. The backend marks it rather than
                    refusing the card; rendering the two identically would put
                    the distinction back where the card exists to take it. */}
                {isObligation && card.obligor_grounded === false && (
                  <InferredTag data-testid="finding-obligor-inferred">
                    obligor inferred
                  </InferredTag>
                )}
              </h4>
              <dl>
                {isObligation ? (
                  <>
                    <dt>Obligation</dt>
                    <dd data-testid="finding-obligation">{card.obligation}</dd>

                    {card.form_reference && (
                      <>
                        <dt>Form</dt>
                        <dd>
                          <code data-testid="finding-form">
                            {card.form_reference}
                          </code>
                        </dd>
                      </>
                    )}

                    {card.deadline && (
                      <>
                        <dt>Deadline</dt>
                        <dd>
                          <code data-testid="finding-deadline">
                            {card.deadline}
                          </code>
                        </dd>
                      </>
                    )}
                  </>
                ) : (
                  <>
                    <dt>Applicable process</dt>
                    <dd>{card.applicable_process}</dd>

                    <dt>Authority status</dt>
                    <dd>{card.authority_status}</dd>

                    <dt>Effective interval</dt>
                    <dd>
                      <code data-testid="finding-interval">
                        {renderInterval(card)}
                      </code>
                    </dd>

                    {card.primary_authority_effective_from && (
                      <>
                        <dt>Authority effective</dt>
                        <dd>
                          <code>{card.primary_authority_effective_from}</code>
                        </dd>
                      </>
                    )}
                  </>
                )}

                <dt>Confidence</dt>
                <dd>{card.confidence}</dd>
              </dl>
              <div>
                <strong style={{ fontSize: "0.84rem" }}>
                  Unresolved qualifications
                </strong>
                {qualifications.length > 0 ? (
                  <ul>
                    {qualifications.map((q) => (
                      <li key={q}>{q}</li>
                    ))}
                  </ul>
                ) : (
                  // Silence and "nothing unresolved" are different claims.
                  <p style={{ margin: 0, fontSize: "0.84rem" }}>None stated.</p>
                )}
              </div>
            </Card>
          );
        })}
      </Cards>
    </Wrap>
  );
};
