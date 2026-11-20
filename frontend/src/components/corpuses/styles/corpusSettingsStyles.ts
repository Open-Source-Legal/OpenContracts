/**
 * Shared styled-components for CorpusSettings and its sub-components.
 * Uses OS Legal design system tokens for consistent styling.
 */
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  OS_LEGAL_SPACING,
  OS_LEGAL_SHADOWS,
} from "../../../assets/configurations/osLegalStyles";

// ============================================================================
// Page Layout
// ============================================================================

/** Main container wrapper for settings page */
export const SettingsContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  position: relative;
`;

/** Scrollable page container with max-width constraint */
export const SettingsPageContainer = styled.div`
  padding: 2rem;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  background: ${OS_LEGAL_COLORS.background};

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-radius: 8px;
  }

  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 8px;

    &:hover {
      background: ${OS_LEGAL_COLORS.textMuted};
    }
  }

  @media (max-width: 768px) {
    padding: 1.25rem;
  }
`;

// ============================================================================
// Section Cards
// ============================================================================

/** Card container for each settings section */
export const SettingsCard = styled.section`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  box-shadow: ${OS_LEGAL_SHADOWS.card};
  margin-bottom: 1.5rem;
  overflow: hidden;
  transition: box-shadow 0.2s ease;

  &:hover {
    box-shadow: ${OS_LEGAL_SHADOWS.cardHover};
  }

  @media (max-width: 768px) {
    border-radius: 10px;
  }
`;

/** Header area for settings card */
export const SettingsCardHeader = styled.div`
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard}
    ${OS_LEGAL_SPACING.borderRadiusCard} 0 0;

  @media (max-width: 768px) {
    border-radius: 10px 10px 0 0;
  }
`;

/** Section title with teal accent bar */
export const SettingsCardTitle = styled.h2`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  letter-spacing: -0.02em;

  &::before {
    content: "";
    width: 3px;
    height: 1.25rem;
    background: ${OS_LEGAL_COLORS.accent};
    border-radius: 2px;
  }
`;

/** Content area for settings card */
export const SettingsCardContent = styled.div`
  padding: 1.5rem;

  @media (max-width: 768px) {
    padding: 1.25rem;
  }
`;

// ============================================================================
// Header Section
// ============================================================================

/** Main header container with title and edit button */
export const CorpusHeaderContainer = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 2rem;
  padding: 1.5rem;
  background: ${OS_LEGAL_COLORS.surface};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: ${OS_LEGAL_SHADOWS.card};
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 1rem;
    padding: 1.25rem;
  }
`;

/** Container for title and description */
export const TitleArea = styled.div`
  flex: 1;
`;

/** Main corpus title */
export const CorpusTitle = styled.h1`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.75rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;
  letter-spacing: -0.02em;
  line-height: 1.2;

  @media (max-width: 768px) {
    font-size: 1.5rem;
  }
`;

/** Corpus description text */
export const CorpusDescription = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 1rem;
  margin: 0;
  max-width: 600px;
  line-height: 1.6;
`;

// ============================================================================
// Metadata Grid
// ============================================================================

/** Grid layout for metadata items */
export const MetadataGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2rem;

  @media (max-width: 768px) {
    grid-template-columns: repeat(2, 1fr);
    gap: 1.5rem;
  }

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
    gap: 1.25rem;
  }
`;

/** Individual metadata item with label and value */
export const MetadataItem = styled.div`
  .label {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: ${OS_LEGAL_COLORS.textMuted};
    margin-bottom: 0.5rem;
    font-weight: 600;
  }

  .value {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 1rem;
    color: ${OS_LEGAL_COLORS.textPrimary};
    font-weight: 500;
    overflow-wrap: break-word;
    word-break: break-word;
    min-width: 0;
  }
`;

/** Badge for public/private/neutral status */
export const StatusBadge = styled.span<{
  variant: "public" | "private" | "neutral";
}>`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: 100px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  font-weight: 500;
  background: ${(props) =>
    props.variant === "public"
      ? OS_LEGAL_COLORS.successLight
      : OS_LEGAL_COLORS.surfaceHover};
  color: ${(props) =>
    props.variant === "public"
      ? OS_LEGAL_COLORS.success
      : OS_LEGAL_COLORS.textSecondary};
  border: 1px solid
    ${(props) =>
      props.variant === "public"
        ? "rgba(22, 163, 74, 0.2)"
        : OS_LEGAL_COLORS.border};
`;

// ============================================================================
// Form Elements
// ============================================================================

/** Two-column grid for form fields */
export const FormGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
  align-items: end;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

/** Form field wrapper with label */
export const FormField = styled.div<{ disabled?: boolean }>`
  .field-label {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: ${(props) =>
      props.disabled
        ? OS_LEGAL_COLORS.borderHover
        : OS_LEGAL_COLORS.textSecondary};
    margin-bottom: 0.5rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .no-permission {
    font-size: 0.6875rem;
    background: ${OS_LEGAL_COLORS.surfaceHover};
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    font-weight: 500;
    text-transform: none;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

/** Styled checkbox container */
export const CheckboxContainer = styled.div<{ disabled?: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.875rem 1rem;
  background: ${(props) =>
    props.disabled ? OS_LEGAL_COLORS.surfaceHover : OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  cursor: ${(props) => (props.disabled ? "not-allowed" : "pointer")};
  transition: border-color 0.2s ease;

  &:hover {
    border-color: ${(props) =>
      props.disabled ? OS_LEGAL_COLORS.border : OS_LEGAL_COLORS.borderHover};
  }

  input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: ${(props) => (props.disabled ? "not-allowed" : "pointer")};
    accent-color: ${OS_LEGAL_COLORS.accent};
  }

  .checkbox-label {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 0.9375rem;
    font-weight: 500;
    color: ${(props) =>
      props.disabled ? OS_LEGAL_COLORS.textMuted : OS_LEGAL_COLORS.textPrimary};
  }
`;

/** Styled text input */
export const StyledInput = styled.input<{ disabled?: boolean }>`
  width: 100%;
  padding: 0.875rem 1rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  background: ${(props) =>
    props.disabled ? OS_LEGAL_COLORS.surfaceHover : OS_LEGAL_COLORS.surface};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.9375rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: ${(props) => (props.disabled ? "not-allowed" : "text")};
  opacity: ${(props) => (props.disabled ? 0.7 : 1)};
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
  outline: none;

  &:focus {
    border-color: ${(props) =>
      props.disabled ? OS_LEGAL_COLORS.border : OS_LEGAL_COLORS.accent};
    box-shadow: ${(props) =>
      props.disabled ? "none" : `0 0 0 3px ${OS_LEGAL_COLORS.accentLight}`};
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

// ============================================================================
// Banners and Notes
// ============================================================================

/** Warning/info banner with icon */
export const PermissionBanner = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: rgba(217, 119, 6, 0.1);
  border: 1px solid rgba(217, 119, 6, 0.3);
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  margin-bottom: 1.5rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.9375rem;
  color: #92400e;
`;

/** Info note with highlighted content */
export const InfoNote = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.6;
  padding: 1rem 1.25rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  margin-bottom: 1.5rem;

  strong {
    color: ${OS_LEGAL_COLORS.accent};
    font-weight: 600;
  }

  .highlight {
    color: ${OS_LEGAL_COLORS.accent};
    font-weight: 500;
  }
`;

// ============================================================================
// Action Cards (for corpus actions list)
// ============================================================================

/** Container for action flow/list */
export const ActionFlow = styled.div`
  margin-top: 1rem;
`;

/** Individual action card */
export const ActionCard = styled.div`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  padding: 1.25rem;
  margin-bottom: 1rem;
  transition:
    box-shadow 0.2s ease,
    border-color 0.2s ease;

  &:hover {
    box-shadow: ${OS_LEGAL_SHADOWS.cardHover};
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  &:last-child {
    margin-bottom: 0;
  }

  @media (max-width: 768px) {
    padding: 1rem;
  }
`;

/** Badge indicating trigger type (add/edit/chat) */
export const TriggerBadge = styled.span<{
  type: "add" | "edit" | "chat";
}>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  border-radius: 100px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  font-weight: 600;
  background: ${(props) =>
    props.type === "add"
      ? OS_LEGAL_COLORS.successLight
      : props.type === "chat"
        ? OS_LEGAL_COLORS.infoSurface
        : OS_LEGAL_COLORS.accentLight};
  color: ${(props) =>
    props.type === "add"
      ? OS_LEGAL_COLORS.success
      : props.type === "chat"
        ? OS_LEGAL_COLORS.infoText
        : OS_LEGAL_COLORS.accent};
`;

/** Status badge for active/disabled */
export const ActionStatusBadge = styled.div<{ active: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: 6px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  font-weight: 600;
  background: ${(props) =>
    props.active ? OS_LEGAL_COLORS.successLight : OS_LEGAL_COLORS.dangerLight};
  color: ${(props) =>
    props.active ? OS_LEGAL_COLORS.success : OS_LEGAL_COLORS.danger};
`;

/** Agent prompt display box */
export const AgentPromptBox = styled.div`
  margin-top: 0.75rem;
  padding: 0.75rem;
  background: ${OS_LEGAL_COLORS.accentLight};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  border-left: 3px solid ${OS_LEGAL_COLORS.accent};

  .prompt-label {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 0.8rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
    margin-bottom: 0.25rem;
    font-weight: 600;
  }

  .prompt-text {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 0.9rem;
    color: ${OS_LEGAL_COLORS.textPrimary};
    font-style: italic;
  }

  .pre-auth-tools {
    margin-top: 0.5rem;
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-size: 0.8rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

// ============================================================================
// Buttons (styled wrappers for @os-legal/ui Button)
// ============================================================================

/** Primary action button container styles */
export const PrimaryButtonStyles = `
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  border: none;
  padding: 0.875rem 1.5rem;
  font-weight: 600;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  box-shadow: 0 2px 8px ${OS_LEGAL_COLORS.accentLight};
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: ${OS_LEGAL_COLORS.accentHover};
    box-shadow: 0 4px 12px ${OS_LEGAL_COLORS.accentLight};
  }

  &:disabled {
    background: ${OS_LEGAL_COLORS.border};
    color: ${OS_LEGAL_COLORS.textMuted};
    box-shadow: none;
    cursor: not-allowed;
  }
`;

/** Success action button container styles */
export const SuccessButtonStyles = `
  background: ${OS_LEGAL_COLORS.success};
  color: white;
  border: none;
  padding: 0.75rem 1.25rem;
  font-weight: 600;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  box-shadow: 0 2px 8px ${OS_LEGAL_COLORS.successLight};
  transition: all 0.2s ease;
  cursor: pointer;

  &:hover:not(:disabled) {
    background: ${OS_LEGAL_COLORS.successHover};
  }

  &:disabled {
    background: ${OS_LEGAL_COLORS.border};
    color: ${OS_LEGAL_COLORS.textMuted};
    box-shadow: none;
    cursor: not-allowed;
  }
`;

/** Helper text under form fields */
export const HelperText = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.5rem;
`;
