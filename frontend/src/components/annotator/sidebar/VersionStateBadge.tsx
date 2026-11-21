import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  AnnotationVersionState,
  PENDING_VERSION_STATES,
  VERSION_STATE_LABELS,
} from "../../../graphql/annotationVersionReview";

const Badge = styled.span<{ $pending: boolean }>`
  display: inline-block;
  padding: 0.05rem 0.45rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: ${({ $pending }) => ($pending ? 600 : 500)};
  white-space: nowrap;
  color: ${({ $pending }) =>
    $pending ? OS_LEGAL_COLORS.awaitingText : OS_LEGAL_COLORS.textSecondary};
  background: ${({ $pending }) =>
    $pending ? OS_LEGAL_COLORS.awaitingSurface : OS_LEGAL_COLORS.surfaceLight};
`;

/** Pending (machine-carried or unplaced) states stand out; human decisions recede. */
export function VersionStateBadge({
  state,
}: {
  state?: AnnotationVersionState | null;
}) {
  if (!state) return null;
  const pending = PENDING_VERSION_STATES.has(state);
  return (
    <Badge
      $pending={pending}
      data-version-state={state}
      title={
        pending
          ? "Carried from the previous version; needs a person to check it"
          : "Checked by a person after a document update"
      }
    >
      {VERSION_STATE_LABELS[state]}
    </Badge>
  );
}
