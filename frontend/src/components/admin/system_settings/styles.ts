import styled from "styled-components";
import { PIPELINE_UI } from "../../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { mediaQuery } from "../../corpuses/styles/corpusDesignTokens";

// ============================================================================
// Layout Styled Components
// ============================================================================

export const Container = styled.div`
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  min-height: 100%;
  overflow-y: auto;
  overflow-x: clip;

  ${mediaQuery.tablet} {
    padding: 2rem 1rem 3rem;
  }
`;

export const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: none;
  border: none;
  color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  padding: 0.5rem 0;
  margin-bottom: 1rem;
  transition: color 0.15s ease;

  &:hover {
    color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

export const PageHeader = styled.div`
  margin-bottom: 2rem;
`;

export const PageTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 1.75rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;

  svg {
    width: 28px;
    height: 28px;
    color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
  }

  ${mediaQuery.tablet} {
    font-size: 1.5rem;
  }
`;

export const PageDescription = styled.p`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 1rem;
  margin: 0;
  line-height: 1.5;
`;

export const LastModified = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-size: 0.875rem;
  margin-top: 0.75rem;

  svg {
    width: 14px;
    height: 14px;
  }
`;

// ============================================================================
// Component Name (shared)
// ============================================================================

export const ComponentName = styled.span`
  font-size: 0.75rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  text-align: center;
  line-height: 1.3;
`;

export const NoComponents = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  color: ${OS_LEGAL_COLORS.textMuted};
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
  border-radius: 8px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textTertiary};
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
  border-radius: 8px;
`;

export const RequiredBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  background: #fef3c7;
  color: #92400e;
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
// Section Styled Components
// ============================================================================

export const Section = styled.div`
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
`;

export const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
`;

export const SectionTitle = styled.h2`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;

  svg {
    width: 18px;
    height: 18px;
    color: #6366f1;
  }
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
  border-radius: 8px;
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
  font-size: 0.6875rem;
  font-weight: 500;
  margin-left: auto;
  background: ${(props) => (props.$populated ? "#ecfdf5" : "#fef3c7")};
  color: ${(props) => (props.$populated ? "#065f46" : "#92400e")};

  svg {
    width: 10px;
    height: 10px;
  }
`;

export const EmptyValue = styled.span`
  color: ${OS_LEGAL_COLORS.textMuted};
  font-style: italic;
  font-size: 0.875rem;
`;

export const DefaultEmbedderDisplay = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
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
  padding-top: 1.5rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
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
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.875rem;
  margin: 0;
`;

export const WarningBanner = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  margin-bottom: 1.5rem;

  svg {
    width: 20px;
    height: 20px;
    color: ${OS_LEGAL_COLORS.folderIcon};
    flex-shrink: 0;
    margin-top: 0.125rem;
  }
`;

export const WarningText = styled.div`
  font-size: 0.875rem;
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
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
  margin-bottom: 0.375rem;
`;

export const FormHelperText = styled.p`
  font-size: 0.75rem;
  color: #6b7280;
  margin: 0.375rem 0 0 0;
`;

// ============================================================================
// Component Library Styled Components
// ============================================================================

export const LibraryContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

export const FilterBar = styled.div`
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
`;

export const FilterChip = styled.button<{ $active: boolean }>`
  padding: 0.375rem 0.875rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border: 1px solid
    ${(props) =>
      props.$active
        ? PIPELINE_UI.PRIMARY_ACCENT_COLOR
        : OS_LEGAL_COLORS.border};
  background: ${(props) =>
    props.$active ? `${PIPELINE_UI.PRIMARY_ACCENT_COLOR}10` : "white"};
  color: ${(props) =>
    props.$active
      ? PIPELINE_UI.PRIMARY_ACCENT_COLOR
      : OS_LEGAL_COLORS.textSecondary};
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover {
    border-color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
    color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
  }
`;

export const SearchInputWrapper = styled.div`
  flex: 1;
  min-width: 200px;
`;

export const ComponentListItem = styled.div<{ $disabled: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  background: white;
  transition: all 0.2s ease;
  opacity: ${(props) => (props.$disabled ? 0.5 : 1)};

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  }
`;

export const ComponentInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

export const ComponentTitle = styled.span`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const ComponentDescription = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.4;
`;

export const BadgeRow = styled.div`
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
  margin-top: 0.375rem;
`;

export const StageBadge = styled.span<{ $color: string }>`
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-radius: 9999px;
  background: ${(props) => `${props.$color}15`};
  color: ${(props) => props.$color};
`;

export const FileTypeBadge = styled.span`
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 500;
  border-radius: 9999px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

// ============================================================================
// Filetype Defaults Styled Components
// ============================================================================

export const DefaultsContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

export const DefaultsHeaderRow = styled.div`
  display: grid;
  grid-template-columns: 120px 1fr 1fr 1fr;
  gap: 0.75rem;
  padding: 0 0.75rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};

  ${mediaQuery.tablet} {
    display: none;
  }
`;

export const FiletypeRow = styled.div`
  display: grid;
  grid-template-columns: 120px 1fr 1fr 1fr;
  gap: 0.75rem;
  align-items: center;
  padding: 0.75rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;

  ${mediaQuery.tablet} {
    grid-template-columns: 1fr;
    gap: 0.5rem;
  }
`;

export const FiletypeLabel = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

export const StageDropdownLabel = styled.label`
  display: none;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-bottom: 0.25rem;

  ${mediaQuery.tablet} {
    display: block;
  }
`;

export const StyledSelect = styled.select<{ $warning?: boolean }>`
  width: 100%;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: white;
  border: 1px solid
    ${(props) =>
      props.$warning ? OS_LEGAL_COLORS.folderIcon : OS_LEGAL_COLORS.border};
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s ease;
  appearance: auto;

  &:hover {
    border-color: ${(props) =>
      props.$warning
        ? OS_LEGAL_COLORS.folderIcon
        : PIPELINE_UI.PRIMARY_ACCENT_COLOR};
  }

  &:focus {
    outline: none;
    border-color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
    box-shadow: 0 0 0 2px ${PIPELINE_UI.PRIMARY_ACCENT_COLOR}20;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

// ============================================================================
// Two-Column Layout (Desktop) + Mobile Tab Fallback
// ============================================================================

export const SettingsTwoColumnLayout = styled.div`
  display: flex;
  gap: 1.5rem;
`;

export const SettingsLeftColumn = styled.div`
  flex: 1;
  min-width: 0;
`;

export const SettingsRightColumn = styled.div`
  flex: 1;
  min-width: 0;
`;

export const MobileSettingsTabContainer = styled.div`
  display: block;
`;

export const MobileSettingsTabList = styled.div`
  display: flex;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  margin-bottom: 1rem;
`;

export const MobileSettingsTabPanel = styled.div`
  margin-top: 0.5rem;
`;

export const MobileSettingsTab = styled.button<{ $active: boolean }>`
  flex: 1;
  padding: 0.75rem 1rem;
  border: none;
  background: transparent;
  font-size: 0.875rem;
  font-weight: ${(props) => (props.$active ? "600" : "500")};
  color: ${(props) =>
    props.$active
      ? PIPELINE_UI.PRIMARY_ACCENT_COLOR
      : OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;

  ${(props) =>
    props.$active &&
    `
    &::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
    }
  `}

  &:hover {
    color: ${PIPELINE_UI.PRIMARY_ACCENT_COLOR};
  }
`;
