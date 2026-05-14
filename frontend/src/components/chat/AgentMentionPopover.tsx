import React, { useEffect } from "react";

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
 */

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
    <div
      role="listbox"
      data-testid="agent-mention-popover"
      style={{
        background: "white",
        border: "1px solid rgba(0,0,0,0.1)",
        borderRadius: 6,
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
        maxHeight: 240,
        overflowY: "auto",
        minWidth: 240,
      }}
    >
      {matches.length === 0 && (
        <div style={{ padding: "0.5rem 0.75rem", color: "#888" }}>
          No matching agents.
        </div>
      )}
      {matches.map((a) => (
        <button
          key={a.id}
          role="option"
          aria-selected={false}
          onClick={() => onSelect(a)}
          style={{
            display: "block",
            width: "100%",
            textAlign: "left",
            padding: "0.5rem 0.75rem",
            background: "transparent",
            border: "none",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          <strong>{a.name}</strong>{" "}
          <span style={{ color: "#888" }}>@{a.slug}</span>
          {a.scope === "CORPUS" && a.corpus && (
            <span style={{ color: "#888" }}> · {a.corpus.title}</span>
          )}
        </button>
      ))}
    </div>
  );
};
