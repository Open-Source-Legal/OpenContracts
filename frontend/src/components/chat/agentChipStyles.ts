/**
 * Shared visual tokens for "this came from agent @X" chips.
 *
 * One source of truth for the violet/indigo palette used by every agent
 * attribution surface so the visual cue stays in lock-step across:
 *   - The bubble-header ``SubAgentAttributionChip`` (ChatMessage.styles.ts)
 *   - The timeline ``TimelineAgentChip`` (ChatMessageTimeline.styles.ts)
 *   - The approval modal ``AgentChip`` (RequestingAgentAttribution.tsx)
 *   - The inline markdown ``@agent`` chip (MarkdownMessageRenderer.tsx,
 *     where the gradient stops are colocated with the other mention types)
 *
 * Each chip composes ``agentChipPaletteCss`` and then layers its own
 * typography / sizing on top so palette tweaks only need to happen here.
 */

import { css } from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

/**
 * Background / border / text palette for the agent attribution chip.
 *
 * Composes the violet/indigo gradient (agentChipViolet → navIndigo at 15%
 * alpha) with the violet-700 text colour. Borders use the violet base at
 * 60% alpha. Consumers add their own padding / font-size / radius.
 */
export const agentChipPaletteCss = css`
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.agentChipViolet}15 0%,
    ${OS_LEGAL_COLORS.navIndigo}15 100%
  );
  border: 1px solid ${OS_LEGAL_COLORS.agentChipViolet}60;
  color: ${OS_LEGAL_COLORS.agentChipText};
`;
