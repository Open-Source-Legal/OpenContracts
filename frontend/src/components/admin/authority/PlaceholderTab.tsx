/**
 * Transitional tab body for an Authority Console concern that has not yet been
 * absorbed into the console (it still lives in a standalone admin panel). Each
 * later phase replaces one PlaceholderTab usage with the real absorbed tab and
 * deletes the corresponding standalone route.
 */
import React from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

const Card = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  align-items: flex-start;
  padding: 1.75rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
`;

const Title = styled.h2`
  margin: 0;
  font-size: 1.1rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const Body = styled.p`
  margin: 0;
  max-width: 44rem;
  font-size: 0.875rem;
  line-height: 1.55;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

interface PlaceholderTabProps {
  title: string;
  description: string;
  action?: React.ReactNode;
}

export const PlaceholderTab: React.FC<PlaceholderTabProps> = ({
  title,
  description,
  action,
}) => (
  <Card data-testid="authority-placeholder-tab">
    <Title>{title}</Title>
    <Body>{description}</Body>
    {action}
  </Card>
);
