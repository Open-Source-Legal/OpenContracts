import { motion } from "framer-motion";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export const KnowledgeLayerContainer = styled.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  background: ${OS_LEGAL_COLORS.surfaceHover};

  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

export const VersionHistorySidebar = styled.div<{
  collapsed?: boolean;
  $mobileVisible?: boolean;
}>`
  width: ${(props) => (props.collapsed ? "60px" : "320px")};
  background: white;
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.04);

  @media (max-width: 768px) {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    width: 100% !important;
    z-index: 10;
    display: ${(props) => (props.$mobileVisible ? "flex" : "none")};
    border-right: none;
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

export const VersionHistoryHeader = styled.div`
  padding: 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.surfaceHover} 0%,
    ${OS_LEGAL_COLORS.surfaceLight} 100%
  );
  position: relative;

  @media (max-width: 768px) {
    padding-top: 3.5rem;
  }

  h3 {
    margin: 0;
    font-size: 1.125rem;
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
    display: flex;
    align-items: center;
    gap: 0.5rem;

    svg {
      color: ${OS_LEGAL_COLORS.primaryBlue};
    }
  }

  .version-count {
    margin-top: 0.375rem;
    font-size: 0.875rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

export const MobileBackButton = styled.button`
  display: none;

  @media (max-width: 768px) {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    position: absolute;
    top: 1rem;
    right: 1rem;
    padding: 0.5rem 1rem;
    background: ${OS_LEGAL_COLORS.blueSurface};
    border: 1px solid ${OS_LEGAL_COLORS.primaryBlue};
    border-radius: 8px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;

    &:hover {
      background: ${OS_LEGAL_COLORS.primaryBlue};
      color: white;
    }

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

export const VersionList = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 0.75rem;

  @media (max-width: 768px) {
    padding: 1rem;
  }

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }

  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 3px;

    &:hover {
      background: ${OS_LEGAL_COLORS.textMuted};
    }
  }
`;

export const VersionItem = styled(motion.button)<{
  $isActive?: boolean;
  $isCurrent?: boolean;
}>`
  width: 100%;
  padding: 1rem;
  margin-bottom: 0.5rem;
  background: ${(props) =>
    props.$isActive
      ? OS_LEGAL_COLORS.blueSurface
      : props.$isCurrent
        ? OS_LEGAL_COLORS.successSurface
        : "white"};
  border: 1px solid
    ${(props) =>
      props.$isActive
        ? OS_LEGAL_COLORS.primaryBlue
        : props.$isCurrent
          ? OS_LEGAL_COLORS.greenMedium
          : OS_LEGAL_COLORS.border};
  border-radius: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: translateX(4px);
    border-color: ${(props) =>
      props.$isActive ? OS_LEGAL_COLORS.primaryBlue : "#93c5fd"};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  }

  .version-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;

    .version-number {
      font-weight: 600;
      font-size: 0.875rem;
      color: ${(props) =>
        props.$isActive
          ? OS_LEGAL_COLORS.primaryBlue
          : props.$isCurrent
            ? OS_LEGAL_COLORS.greenMedium
            : OS_LEGAL_COLORS.textPrimary};
    }

    .version-badge {
      padding: 0.125rem 0.5rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
      background: ${(props) =>
        props.$isActive
          ? OS_LEGAL_COLORS.primaryBlue
          : props.$isCurrent
            ? OS_LEGAL_COLORS.greenMedium
            : OS_LEGAL_COLORS.border};
      color: ${(props) =>
        props.$isActive || props.$isCurrent
          ? "white"
          : OS_LEGAL_COLORS.textSecondary};
    }
  }

  .version-meta {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8125rem;
    color: ${OS_LEGAL_COLORS.textSecondary};

    .meta-row {
      display: flex;
      align-items: center;
      gap: 0.375rem;

      svg {
        width: 12px;
        height: 12px;
      }
    }
  }
`;

export const KnowledgeContent = styled.div<{ $mobileVisible?: boolean }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  margin: 1rem;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  overflow: hidden;

  @media (max-width: 768px) {
    margin: 0;
    border-radius: 0;
    display: ${(props) => (props.$mobileVisible !== false ? "flex" : "none")};
  }
`;

export const KnowledgeHeader = styled.div`
  padding: 1.5rem 2rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: linear-gradient(
    135deg,
    #ffffff 0%,
    ${OS_LEGAL_COLORS.surfaceHover} 100%
  );

  @media (max-width: 768px) {
    padding: 1rem;
  }

  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;

    @media (max-width: 768px) {
      flex-direction: column;
      align-items: stretch;
      gap: 1rem;
    }

    h2 {
      margin: 0;
      font-size: 1.5rem;
      font-weight: 600;
      color: ${OS_LEGAL_COLORS.textPrimary};
      display: flex;
      align-items: center;
      gap: 0.75rem;

      @media (max-width: 768px) {
        font-size: 1.25rem;
      }

      svg {
        color: ${OS_LEGAL_COLORS.primaryBlue};
      }
    }

    .header-actions {
      display: flex;
      gap: 0.75rem;

      @media (max-width: 768px) {
        justify-content: stretch;

        button {
          flex: 1;
          white-space: nowrap;
        }
      }
    }
  }

  .version-info {
    margin-top: 0.5rem;
    font-size: 0.875rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
    display: flex;
    align-items: center;
    gap: 1rem;

    @media (max-width: 768px) {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
      font-size: 0.8125rem;
    }

    .info-item {
      display: flex;
      align-items: center;
      gap: 0.375rem;

      svg {
        width: 14px;
        height: 14px;
      }
    }
  }
`;

export const KnowledgeBody = styled.div<{ $isEditing?: boolean }>`
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
  background: ${(props) =>
    props.$isEditing ? OS_LEGAL_COLORS.surfaceHover : "white"};

  @media (max-width: 768px) {
    padding: 1rem;
  }

  .prose {
    max-width: 65ch;
    margin: 0 auto;

    @media (max-width: 768px) {
      max-width: 100%;
    }
  }
`;

export const EditModeToolbar = styled(motion.div)`
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 1rem 2rem;
  margin: -2rem -2rem 2rem -2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 10;

  @media (max-width: 768px) {
    padding: 0.75rem 1rem;
    margin: -1rem -1rem 1rem -1rem;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 1rem;

    .edit-indicator {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.375rem 0.75rem;
      background: #fef3c7;
      color: ${OS_LEGAL_COLORS.folderIcon};
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 500;

      @media (max-width: 768px) {
        font-size: 0.8125rem;
        padding: 0.25rem 0.5rem;
      }

      svg {
        width: 16px;
        height: 16px;
      }
    }
  }

  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
`;

export const EditToolbarCloseButton = styled.button`
  display: none; /* Hidden on desktop */

  @media (max-width: 768px) {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: 1px solid ${OS_LEGAL_COLORS.border};
    background: white;
    cursor: pointer;
    transition: all 0.2s ease;
    flex-shrink: 0;

    svg {
      width: 16px;
      height: 16px;
      color: ${OS_LEGAL_COLORS.textSecondary};
    }

    &:hover {
      background: ${OS_LEGAL_COLORS.surfaceHover};
      border-color: ${OS_LEGAL_COLORS.borderHover};

      svg {
        color: ${OS_LEGAL_COLORS.textTertiary};
      }
    }

    &:active {
      transform: scale(0.95);
    }
  }
`;

export const MarkdownEditor = styled.textarea`
  width: 100%;
  min-height: 500px;
  padding: 1.5rem;
  background: white;
  border: 2px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", monospace;
  font-size: 0.875rem;
  line-height: 1.6;
  resize: vertical;
  transition: border-color 0.2s;

  @media (max-width: 768px) {
    min-height: 300px;
    padding: 1rem;
    font-size: 0.8125rem;
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
`;

export const CollapseSidebarButton = styled(motion.button)`
  position: absolute;
  top: 1rem;
  right: -12px;
  width: 24px;
  height: 24px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: all 0.2s;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    transform: scale(1.1);
  }

  svg {
    width: 14px;
    height: 14px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  @media (max-width: 768px) {
    display: none;
  }
`;
