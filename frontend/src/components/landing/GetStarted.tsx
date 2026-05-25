/**
 * GetStarted Component — cite rebrand.
 *
 * Displays the Get Started action list shown on the landing page. Each row
 * uses the `[•]` icon mark per the brand spec (`04_landing/landing_spec.md`).
 * Authenticated users can dismiss the card; preference is persisted to the
 * backend. Anonymous users have their dismissal stored in localStorage.
 */
import React from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@apollo/client";
import { gql } from "@apollo/client";
import { X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { CiteMark } from "../brand/CiteMark";
import {
  useLandingContent,
  type GetStartedAction,
} from "../../config/landingContent";

// GraphQL mutation to dismiss Getting Started
export const DISMISS_GETTING_STARTED = gql`
  mutation DismissGettingStarted {
    dismissGettingStarted {
      ok
      message
    }
  }
`;

interface GetStartedProps {
  isAuthenticated: boolean;
  isDismissed: boolean;
  onDismiss: () => void;
}

const Container = styled.div`
  position: relative;
`;

const Title = styled.h3`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 16px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 16px 0;
`;

const Card = styled.div`
  background: ${OS_LEGAL_COLORS.surface};
  border-radius: 8px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 18px 6px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
`;

const DismissButton = styled.button`
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

const ActionList = styled.div`
  display: flex;
  flex-direction: column;
`;

const ActionItem = styled.button`
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 18px;
  background: transparent;
  border: none;
  border-radius: 6px;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

const ActionLabel = styled.span`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.accent};
`;

/**
 * Action items and section title come from the active landingContent
 * variant. The aria-label on the dismiss button mirrors the configured
 * title so screen readers stay in sync when a deployer renames the
 * section.
 */
export const GetStarted: React.FC<GetStartedProps> = ({
  isAuthenticated,
  isDismissed,
  onDismiss,
}) => {
  const navigate = useNavigate();
  const [dismissMutation] = useMutation(DISMISS_GETTING_STARTED);
  const { getStarted } = useLandingContent();

  const handleDismiss = async () => {
    if (isAuthenticated) {
      try {
        await dismissMutation();
      } catch (error) {
        console.error("Failed to dismiss Getting Started:", error);
      }
    }
    onDismiss();
  };

  const handleActionClick = (action: GetStartedAction) => {
    if (action.external) {
      window.open(action.path, "_blank", "noopener,noreferrer");
    } else {
      navigate(action.path);
    }
  };

  if (isDismissed) {
    return null;
  }

  return (
    <Container>
      <Title>{getStarted.title}</Title>
      <DismissButton
        onClick={handleDismiss}
        aria-label={`Dismiss ${getStarted.title}`}
      >
        <X size={16} />
      </DismissButton>
      <Card>
        <ActionList>
          {getStarted.actions.map((action) => (
            <ActionItem
              key={action.id}
              onClick={() => handleActionClick(action)}
            >
              <CiteMark size={16} ariaLabel="" />
              <ActionLabel>{action.label}</ActionLabel>
            </ActionItem>
          ))}
        </ActionList>
      </Card>
    </Container>
  );
};
