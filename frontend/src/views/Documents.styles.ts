import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../assets/configurations/osLegalStyles";

// ═══════════════════════════════════════════════════════════════════════════════
// HERO / FILTER STYLES
// ═══════════════════════════════════════════════════════════════════════════════

export const SearchContainer = styled.div`
  margin-bottom: 16px;
`;

export const FilterTabsRow = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;

  /* On narrow screens the status tabs wrap to multiple lines; a centered
     flex row leaves the Filters button floating beside the wrapped block.
     Stack instead so the button sits cleanly below the tabs. */
  @media (max-width: 640px) {
    flex-direction: column;
    align-items: flex-start;
  }
`;

export const FilterButton = styled.button<{
  $active?: boolean;
  $hasFilters?: boolean;
}>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.surfaceLight : "white"};
  border: 1px solid
    ${(props) =>
      props.$hasFilters ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  border-radius: 8px;
  color: ${(props) =>
    props.$hasFilters ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textSecondary};
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${(props) =>
      props.$hasFilters ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.borderHover};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

export const FilterBadge = styled.span`
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
`;

export const FilterPopupContainer = styled.div`
  position: relative;
`;

export const FilterPopup = styled.div`
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 50;
  min-width: 320px;
  padding: 16px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.12);

  /* Override the harsh gradient labels from filter components */
  .ui.label {
    background: ${OS_LEGAL_COLORS.surfaceLight} !important;
    color: ${OS_LEGAL_COLORS.textTertiary} !important;
    box-shadow: none !important;
    font-size: 0.6875rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
  }

  @media (max-width: 640px) {
    left: 50%;
    transform: translateX(-50%);
    min-width: calc(100vw - 48px);
    max-width: 400px;
  }
`;

export const FilterPopupHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

export const FilterPopupTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const FilterPopupClose = styled.button`
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

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

export const FilterPopupContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;

  /* Give each child descending z-index so earlier dropdowns appear above later ones */
  & > *:nth-child(1) {
    position: relative;
    z-index: 30;
  }
  & > *:nth-child(2) {
    position: relative;
    z-index: 20;
  }
  & > *:nth-child(3) {
    position: relative;
    z-index: 10;
  }
  & > *:nth-child(4) {
    position: relative;
    z-index: 5;
  }
`;

export const ClearFiltersButton = styled.button`
  margin-top: 8px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    background: ${OS_LEGAL_COLORS.dangerSurface};
    border-color: ${OS_LEGAL_COLORS.dangerBorder};
    color: ${OS_LEGAL_COLORS.danger};
  }
`;

export const ActionButtons = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

export const ViewToggle = styled.div`
  display: flex;
  align-items: center;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 3px;
`;

export const ViewToggleButton = styled.button<{ $active?: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.surfaceLight : "transparent"};
  border: none;
  border-radius: 6px;
  color: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.textPrimary : OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

// Outer wrapper for the entire documents section (header + view + fetch-more).
export const DocumentsSection = styled.section`
  position: relative;
  min-height: 200px;
`;

// ═══════════════════════════════════════════════════════════════════════════════
// DOCUMENT GRID STYLES
// ═══════════════════════════════════════════════════════════════════════════════

export const DocumentsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
`;

export const DocumentCardWrapper = styled.div<{ $selected?: boolean }>`
  position: relative;
  display: flex;
  flex-direction: column;
  background: white;
  border: 1px solid
    ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.15s;
  cursor: pointer;
  box-shadow: ${(props) =>
    props.$selected ? `0 0 0 2px ${accentAlpha(0.2)}` : "none"};

  &:hover {
    border-color: ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.borderHover};
    box-shadow: ${(props) =>
      props.$selected
        ? `0 0 0 2px ${accentAlpha(0.2)}`
        : "0 4px 6px rgba(15, 23, 42, 0.04)"};
    transform: translateY(-2px);
  }
`;

export const CardCheckbox = styled.div<{ $visible?: boolean }>`
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 10;
  opacity: ${(props) => (props.$visible ? 1 : 0)};
  transition: opacity 0.15s;

  ${DocumentCardWrapper}:hover & {
    opacity: 1;
  }
`;

export const CardPreview = styled.div`
  position: relative;
  height: 160px;
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.surfaceHover} 0%,
    ${OS_LEGAL_COLORS.surfaceLight} 100%
  );
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
`;

export const CardThumbnail = styled.img`
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center top;
`;

export const CardPreviewPlaceholder = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

export const PreviewLines = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 80%;
  max-width: 180px;
`;

export const PreviewLine = styled.div<{ $width?: string }>`
  height: 6px;
  background: ${OS_LEGAL_COLORS.border};
  border-radius: 3px;
  width: ${(props) => props.$width || "100%"};
`;

export const TypeBadge = styled.div`
  position: absolute;
  top: 12px;
  right: 12px;
`;

export const ProcessingOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(248, 250, 252, 0.9);
  backdrop-filter: blur(2px);
`;

export const ProcessingText = styled.span`
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

export const CardBody = styled.div`
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

export const CardTitle = styled.h4`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.4;
  word-break: break-word;
`;

export const CardMeta = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

export const CardFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.background};
`;

export const CardUploader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

export const CardMenuButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;

  ${DocumentCardWrapper}:hover & {
    opacity: 1;
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// DOCUMENT LIST STYLES
// ═══════════════════════════════════════════════════════════════════════════════

// Inner wrapper for the list view (table-shaped grid).
export const DocumentsListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
`;

export const ListHeader = styled.div`
  display: grid;
  grid-template-columns: 40px 1fr 100px 100px 120px 150px 48px;
  gap: 16px;
  padding: 12px 16px;
  background: ${OS_LEGAL_COLORS.background};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};

  @media (max-width: 768px) {
    grid-template-columns: 32px 1fr 80px 48px;

    & > :nth-child(3),
    & > :nth-child(5),
    & > :nth-child(6) {
      display: none;
    }
  }
`;

export const ListItem = styled.div<{ $selected?: boolean }>`
  display: grid;
  grid-template-columns: 40px 1fr 100px 100px 120px 150px 48px;
  gap: 16px;
  padding: 12px 16px;
  align-items: center;
  cursor: pointer;
  transition: background 0.1s;
  background: ${(props) =>
    props.$selected ? accentAlpha(0.04) : "transparent"};

  &:hover {
    background: ${(props) =>
      props.$selected ? accentAlpha(0.06) : OS_LEGAL_COLORS.surfaceHover};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }

  @media (max-width: 768px) {
    grid-template-columns: 32px 1fr 80px 48px;

    & > :nth-child(3),
    & > :nth-child(5),
    & > :nth-child(6) {
      display: none;
    }
  }
`;

export const ListItemIcon = styled.div`
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

export const ListItemName = styled.span`
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const ListItemType = styled.span`
  font-size: 12px;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

export const ListItemSize = styled.span`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

export const ListItemUploader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

export const ListItemActions = styled.div`
  display: flex;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.1s;

  ${ListItem}:hover & {
    opacity: 1;
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// COMPACT VIEW STYLES
// ═══════════════════════════════════════════════════════════════════════════════

// Inner wrapper for the compact view.
export const DocumentsCompactContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
`;

export const CompactItem = styled.div<{ $selected?: boolean }>`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.1s;
  background: ${(props) =>
    props.$selected ? accentAlpha(0.04) : "transparent"};

  &:hover {
    background: ${(props) =>
      props.$selected ? accentAlpha(0.06) : OS_LEGAL_COLORS.surfaceHover};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

export const CompactItemName = styled.span`
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

export const CompactItemMeta = styled.span`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  flex-shrink: 0;
`;
