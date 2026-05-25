/**
 * RequestingAgentAttribution
 *
 * Attribution chip surfaced inside the approval modal when an approval was
 * raised inside a sub-agent invocation (rich-mention agent delegation,
 * Task 14). Rendered inside the shared ``ApprovalDialog`` (used by both the
 * document right-tray ChatTray and CorpusChat) so the visual treatment — and
 * the testid Playwright assertions key off of — stays in lock-step across
 * surfaces.
 *
 * The violet/indigo palette intentionally mirrors:
 *   - The inline ``@agent`` mention chip in ``MarkdownMessageRenderer``
 *   - The bubble-header sub-agent chip in ``ChatMessage.styles.ts``
 *   - The timeline ``@<slug>`` chip in ``ChatMessageTimeline.styles.ts``
 * so users see one consistent "agent identity" cue across attribution
 * surfaces.
 */

import React from "react";
import styled from "styled-components";
import type { PendingApproval } from "./types";
import { agentChipPaletteCss } from "./agentChipStyles";

const AgentChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border-radius: 0.625rem;
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.2;
  ${agentChipPaletteCss};
  letter-spacing: -0.01em;
  white-space: nowrap;

  & > [aria-hidden="true"] {
    opacity: 0.75;
    font-weight: 600;
  }
`;

const RequestingAgentLine = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
  font-weight: 600;
`;

export interface RequestingAgentAttributionProps {
  requestingAgent: NonNullable<PendingApproval["requestingAgent"]>;
  toolName: string;
}

export const RequestingAgentAttribution: React.FC<
  RequestingAgentAttributionProps
> = ({ requestingAgent, toolName }) => (
  <RequestingAgentLine data-testid="approval-requesting-agent">
    <AgentChip
      role="note"
      aria-label={`Requested by agent ${requestingAgent.name}`}
      title={`Requested by agent ${requestingAgent.name}`}
    >
      <span aria-hidden="true">@</span>
      {requestingAgent.slug}
    </AgentChip>
    <span>is asking to run</span>
    <span>{toolName}</span>
  </RequestingAgentLine>
);
