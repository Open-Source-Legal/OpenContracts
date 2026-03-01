import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
  OS_LEGAL_SPACING,
} from "../../../assets/configurations/osLegalStyles";
import { PIPELINE_UI } from "../../../assets/configurations/constants";

// ============================================================================
// Layout Styled Components
// ============================================================================

export const PipelineContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
`;

export const PipelineDescription = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.9375rem;
  margin: 0 0 0.5rem 0;
  line-height: 1.5;
`;

export const LastModified = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.8125rem;
  margin-bottom: 0.25rem;

  svg {
    width: 14px;
    height: 14px;
  }
`;

// ============================================================================
// Stage Card Styled Components
// ============================================================================

export const StageCardContainer = styled.div<{ $active?: boolean }>`
  background: ${OS_LEGAL_COLORS.surface};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  border: 1px solid
    ${(props) =>
      props.$active ? OS_LEGAL_COLORS.selectedBorder : OS_LEGAL_COLORS.border};
  box-shadow: ${(props) =>
    props.$active
      ? OS_LEGAL_SPACING.shadowCardHover
      : OS_LEGAL_SPACING.shadowCard};
  position: relative;
  transition: all 0.2s ease;
  overflow: hidden;
`;

export const StageCardHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

export const StageNumberBadge = styled.span<{ $active?: boolean }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.accentLight : OS_LEGAL_COLORS.surfaceHover};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  font-weight: 700;
  color: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textMuted};
  transition: all 0.2s;
`;

export const StageHeaderInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

export const StageTitle = styled.h3`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
`;

export const StageSubtitle = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin: 0.125rem 0 0 0;
`;

export const MimeSelector = styled.div`
  display: flex;
  gap: 0.25rem;
`;

export const MimeButton = styled.button<{ $active: boolean }>`
  padding: 0.25rem 0.625rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  border: 1px solid
    ${(props) =>
      props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.surface};
  color: ${(props) => (props.$active ? "#fff" : OS_LEGAL_COLORS.textMuted)};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.accentHover
        : OS_LEGAL_COLORS.surfaceHover};
    color: ${(props) =>
      props.$active ? "#fff" : OS_LEGAL_COLORS.textSecondary};
    border-color: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.accentHover
        : OS_LEGAL_COLORS.borderHover};
  }
`;

export const StageCardContent = styled.div`
  padding: 1rem 1.25rem 1.25rem;
`;

// ============================================================================
// Component Grid Styled Components
// ============================================================================

export const ComponentGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(
    auto-fill,
    minmax(${PIPELINE_UI.COMPONENT_GRID_MIN_WIDTH}px, 1fr)
  );
  gap: 0.75rem;

  @media (max-width: 480px) {
    grid-template-columns: repeat(2, 1fr);
  }
`;

export const ComponentCard = styled.button<{
  $selected: boolean;
  $color: string;
}>`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.25rem 1rem;
  background: ${(props) =>
    props.$selected ? `${props.$color}10` : OS_LEGAL_COLORS.surfaceHover};
  border: 2px solid
    ${(props) => (props.$selected ? props.$color : OS_LEGAL_COLORS.border)};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  min-height: ${PIPELINE_UI.COMPONENT_CARD_MIN_HEIGHT_PX}px;

  &:hover {
    border-color: ${(props) => props.$color};
    transform: translateY(-1px);
    box-shadow: ${OS_LEGAL_SPACING.shadowCardHover};
  }

  ${(props) =>
    props.$selected &&
    `
    box-shadow: 0 0 0 3px ${props.$color}20;
  `}
`;

export const SelectedBadge = styled.div<{ $color: string }>`
  position: absolute;
  top: 8px;
  right: 8px;
  width: 20px;
  height: 20px;
  background: ${(props) => props.$color};
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;

  svg {
    width: 12px;
    height: 12px;
    color: white;
  }
`;

export const ComponentIconWrapper = styled.div`
  margin-bottom: 0.5rem;
`;

export const ComponentName = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  text-align: center;
  line-height: 1.3;
`;

export const VectorBadge = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.625rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.25rem;
`;

export const NoComponents = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  font-style: italic;
`;

// ============================================================================
// Collapsible Settings Styled Components
// ============================================================================

export const AdvancedSettingsToggle = styled.button<{ $expanded: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.75rem;
  margin-top: 1rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.background};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 16px;
    height: 16px;
    transition: transform 0.2s ease;
    transform: rotate(${(props) => (props.$expanded ? "90deg" : "0deg")});
  }
`;

export const AdvancedSettingsContent = styled.div<{ $expanded: boolean }>`
  display: ${(props) => (props.$expanded ? "block" : "none")};
  margin-top: 0.75rem;
  padding: 1rem;
  background: ${OS_LEGAL_COLORS.background};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
`;

export const RequiredBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  background: #fef3c7;
  color: #92400e;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.625rem;
  font-weight: 500;
  border-radius: 4px;
  margin-left: auto;

  svg {
    width: 10px;
    height: 10px;
  }
`;

// ============================================================================
// Bottom Sections
// ============================================================================

export const Section = styled.div<{ $marginTop?: string }>`
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
  padding: 1.25rem;
  box-shadow: ${OS_LEGAL_SPACING.shadowCard};
  ${(props) => props.$marginTop && `margin-top: ${props.$marginTop};`}
`;

export const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
`;

export const SectionTitle = styled.h3`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;

  svg {
    width: 18px;
    height: 18px;
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

export const SectionDescription = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8125rem;
  margin: 0 0 0.75rem 0;
`;

export const SecretKeyList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

export const SecretKeyRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  font-size: 0.8125rem;
`;

export const SecretKeyName = styled.span`
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-family: monospace;
  font-size: 0.75rem;
`;

export const SecretStatusIndicator = styled.span<{ $populated: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.6875rem;
  font-weight: 500;
  margin-left: auto;
  background: ${(props) =>
    props.$populated ? OS_LEGAL_COLORS.successLight : "#fef3c7"};
  color: ${(props) => (props.$populated ? "#065f46" : "#92400e")};

  svg {
    width: 10px;
    height: 10px;
  }
`;

export const EmptyValue = styled.span`
  color: ${OS_LEGAL_COLORS.textMuted};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-style: italic;
  font-size: 0.875rem;
`;

export const DefaultEmbedderDisplay = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
`;

export const DefaultEmbedderInfo = styled.div`
  flex: 1;
`;

export const DefaultEmbedderPath = styled.code`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  word-break: break-all;
`;

export const ActionButtons = styled.div`
  display: flex;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
`;

// ============================================================================
// Loading / Error / Warning States
// ============================================================================

export const LoadingContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 1rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
`;

export const ErrorContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  gap: 1rem;
  padding: 2rem;
  text-align: center;

  svg {
    width: 48px;
    height: 48px;
    color: ${OS_LEGAL_COLORS.danger};
  }
`;

export const ErrorMessage = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.875rem;
  margin: 0;
`;

export const WarningBanner = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  margin-bottom: 1rem;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};

  svg {
    width: 18px;
    height: 18px;
    color: #d97706;
    flex-shrink: 0;
    margin-top: 0.125rem;
  }
`;

export const WarningText = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.8125rem;
  color: #92400e;
  line-height: 1.5;

  strong {
    font-weight: 600;
  }
`;

// ============================================================================
// Form / Secret Field Styled Components
// ============================================================================

export const SecretFieldGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

export const SecretFieldRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

export const SecretFieldHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

export const FormField = styled.div`
  margin-bottom: 1rem;

  &:last-child {
    margin-bottom: 0;
  }
`;

export const FormLabel = styled.label`
  display: block;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin-bottom: 0.375rem;
`;

export const FormHelperText = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0.375rem 0 0 0;
`;

// ============================================================================
// Embedder Selection List (for Default Embedder Modal)
// ============================================================================

export const EmbedderOption = styled.div<{ $selected: boolean }>`
  padding: 0.75rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  cursor: pointer;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  margin-bottom: 0.5rem;
  background: ${(props) =>
    props.$selected
      ? OS_LEGAL_COLORS.accentLight
      : OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid
    ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  transition: all 0.15s ease;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    background: ${(props) =>
      props.$selected
        ? OS_LEGAL_COLORS.accentLight
        : OS_LEGAL_COLORS.background};
  }
`;

export const EmbedderOptionTitle = styled.strong`
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const EmbedderOptionMeta = styled.span`
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-left: 0.5rem;
`;

export const EmbedderOptionPath = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-family: monospace;
  margin-top: 0.25rem;
`;
