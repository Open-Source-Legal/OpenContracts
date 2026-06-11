import React from "react";
import styled from "styled-components";
import { Landmark } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS,
  GOVERNANCE_GRAPH_COLORS,
  WANTED_AUTHORITIES_MAX_ROWS,
} from "../../../../assets/configurations/constants";
import { WantedAuthority } from "../../../../graphql/queries";
import { formatCanonicalLawKey } from "../../../../utils/formatters";
import {
  GraphCard,
  GraphHeader,
  GraphMeta,
  GraphTitle,
} from "./graphCardChrome";

/**
 * WantedAuthoritiesCard — the missing-law backlog, made visible.
 *
 * The governance graph renders citations without an in-system target as
 * dashed "ghost" nodes; this card is the actionable side of those ghosts:
 * which bodies of law the collection cites that aren't in the library yet,
 * ranked by citation demand, with the hottest sections called out. It speaks
 * the graph's visual vocabulary — shelf-style authority captions, dashed
 * ghost chips — so the two surfaces clearly describe the same thing.
 *
 * Purely presentational; ``WantedAuthoritiesLive`` owns the query and renders
 * nothing at all when the backlog is empty (no card, no empty state — an
 * empty backlog is simply not news).
 */

interface WantedAuthoritiesCardProps {
  authorities: WantedAuthority[];
  testId?: string;
}

const Rows = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
`;

const Row = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
`;

const RowHead = styled.div`
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
`;

// Echoes the governance graph's shelf captions: small, letter-spaced, gold.
const AuthorityCaption = styled.span`
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  color: ${GOVERNANCE_GRAPH_COLORS.LAW_CAPTION};
`;

const RowMeta = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
`;

const KeyChips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
`;

// Dashed outline mirrors the graph's "cited, not yet ingested" ghost nodes.
const KeyChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.5rem;
  border: 1px dashed ${GOVERNANCE_GRAPH_COLORS.EXTERNAL};
  border-radius: 999px;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  white-space: nowrap;
`;

const ChipCount = styled.span`
  font-size: 0.6875rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
`;

const MoreNote = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const FooterHint = styled.p`
  margin: 0;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

/** Row caption: registered authorities use the graph's shelf caption; the
 * rest fall back to the canonical-key display form, upper-cased to match. */
function authorityCaption(authority: string): string {
  return (
    GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS[authority] ||
    formatCanonicalLawKey(authority).toUpperCase()
  );
}

export const WantedAuthoritiesCard: React.FC<WantedAuthoritiesCardProps> = ({
  authorities,
  testId = "wanted-authorities",
}) => {
  if (authorities.length === 0) return null;

  const shown = authorities.slice(0, WANTED_AUTHORITIES_MAX_ROWS);
  const hiddenCount = authorities.length - shown.length;
  const totalMentions = authorities.reduce((s, a) => s + a.mentionCount, 0);

  return (
    <GraphCard data-testid={testId}>
      <GraphHeader>
        <GraphTitle $iconColor={GOVERNANCE_GRAPH_COLORS.EXTERNAL}>
          <Landmark size={16} />
          Cited law not yet in the library
        </GraphTitle>
        <GraphMeta data-testid={`${testId}-meta`}>
          {totalMentions} unresolved{" "}
          {totalMentions === 1 ? "reference" : "references"}
        </GraphMeta>
      </GraphHeader>

      <Rows data-testid={`${testId}-rows`}>
        {shown.map((a) => (
          <Row key={a.authority} data-testid={`${testId}-row`}>
            <RowHead>
              <AuthorityCaption>
                {authorityCaption(a.authority)}
              </AuthorityCaption>
              <RowMeta>
                {a.mentionCount}{" "}
                {a.mentionCount === 1 ? "reference" : "references"}
                {" · "}
                {a.keyCount} {a.keyCount === 1 ? "section" : "sections"}
              </RowMeta>
            </RowHead>
            {a.topKeys.length > 0 && (
              <KeyChips>
                {a.topKeys.map((k) => (
                  <KeyChip key={k.canonicalKey}>
                    {formatCanonicalLawKey(k.canonicalKey)}
                    <ChipCount>×{k.mentionCount}</ChipCount>
                  </KeyChip>
                ))}
              </KeyChips>
            )}
          </Row>
        ))}
        {hiddenCount > 0 && (
          <MoreNote data-testid={`${testId}-more`}>
            …and {hiddenCount} more{" "}
            {hiddenCount === 1 ? "authority" : "authorities"}
          </MoreNote>
        )}
      </Rows>

      <FooterHint>
        These are the dashed nodes in the governance graph — bodies of law this
        collection cites that aren't in the library yet. Ingesting them resolves
        the citations down to the exact section.
      </FooterHint>
    </GraphCard>
  );
};
