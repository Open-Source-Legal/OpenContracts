import React from "react";
import styled, { keyframes } from "styled-components";
import { Loader2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

const spin = keyframes`
  to {
    transform: rotate(360deg);
  }
`;

const Footer = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px 0 24px;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-size: 0.875rem;

  svg {
    animation: ${spin} 0.8s linear infinite;
  }
`;

interface FetchMoreFooterProps {
  /** Render the footer when true (i.e. a `fetchMore` is in flight and there is a next page). */
  visible: boolean;
  /** Visible label and accessible status text, e.g. "Loading more documents…". */
  message: string;
  /** Optional override for `data-testid`. Default: `fetch-more-spinner`. */
  "data-testid"?: string;
}

/** Footer-pinned spinner shown beneath an infinite-scroll list during fetchMore. */
export const FetchMoreFooter: React.FC<FetchMoreFooterProps> = ({
  visible,
  message,
  "data-testid": dataTestId = "fetch-more-spinner",
}) => {
  if (!visible) return null;
  return (
    <Footer role="status" aria-live="polite" data-testid={dataTestId}>
      <Loader2 size={16} aria-hidden="true" />
      <span>{message}</span>
    </Footer>
  );
};
