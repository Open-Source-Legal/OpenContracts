import React, { useEffect } from "react";
import styled from "styled-components";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

/**
 * Slim popover for selecting an agent to @mention in chat input.
 *
 * Design choice (Task 9): we considered wrapping
 * `frontend/src/components/threads/UnifiedMentionPicker.tsx` since CLAUDE.md
 * says "Re-use, don't fork". However, UnifiedMentionPicker:
 *   - Requires the caller to manage `selectedIndex` and to forward keyboard
 *     events through an imperative ref (`useImperativeHandle`).
 *   - Operates on the richer `UnifiedMentionResource` shape with cross-type
 *     categorization (users/corpuses/documents/annotations/agents).
 *   - Triggers GraphQL searches via `useUnifiedMentionSearch` for multi-type
 *     auto-suggest.
 *
 * Phase 1 of the rich-mention agent delegation feature only needs an
 * agent-only picker driven by a fragment string and a pre-fetched agent
 * list (the agents are fetched once at chat-open time and filtered locally).
 * Wrapping UnifiedMentionPicker would require either adapting that local
 * list into `UnifiedMentionResource` plus re-implementing keyboard state
 * locally, or threading new "agent-only" props through it — both of which
 * are heavier than this slim component. We will revisit consolidation in
 * a later phase once both pickers share more behavior.
 *
 * Styling mirrors UnifiedMentionPicker's theme-token usage (no hex literals)
 * so visual treatment stays consistent across mention surfaces.
 */

const Container = styled.div`
  background: ${color.N1};
  border: 1px solid ${color.N4};
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  max-height: 240px;
  overflow-y: auto;
  min-width: 240px;
`;

const NoResults = styled.div`
  padding: ${spacing.xs} ${spacing.sm};
  color: ${color.N7};
  font-size: 13px;
`;

const OptionButton = styled.button`
  display: block;
  width: 100%;
  text-align: left;
  padding: ${spacing.xs} ${spacing.sm};
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: ${color.N10};
  transition: background 0.15s;

  &:hover {
    background: ${color.N2};
  }
`;

const OptionName = styled.strong`
  font-weight: 600;
  color: ${color.N10};
`;

const OptionMeta = styled.span`
  color: ${color.N7};
`;

export interface AgentItem {
  id: string;
  slug: string;
  name: string;
  scope: "GLOBAL" | "CORPUS";
  corpus?: { slug: string; title: string } | null;
}

interface Props {
  fragment: string;
  agents: AgentItem[];
  onSelect: (agent: AgentItem) => void;
  onDismiss: () => void;
}

export const AgentMentionPopover: React.FC<Props> = ({
  fragment,
  agents,
  onSelect,
  onDismiss,
}) => {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onDismiss();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onDismiss]);

  const lower = fragment.toLowerCase();
  const matches = agents.filter(
    (a) =>
      a.slug.toLowerCase().includes(lower) ||
      a.name.toLowerCase().includes(lower)
  );

  return (
    <Container role="listbox" data-testid="agent-mention-popover">
      {matches.length === 0 && <NoResults>No matching agents.</NoResults>}
      {matches.map((a) => (
        <OptionButton
          key={a.id}
          role="option"
          aria-selected={false}
          onClick={() => onSelect(a)}
        >
          <OptionName>{a.name}</OptionName> <OptionMeta>@{a.slug}</OptionMeta>
          {a.scope === "CORPUS" && a.corpus && (
            <OptionMeta> · {a.corpus.title}</OptionMeta>
          )}
        </OptionButton>
      ))}
    </Container>
  );
};
