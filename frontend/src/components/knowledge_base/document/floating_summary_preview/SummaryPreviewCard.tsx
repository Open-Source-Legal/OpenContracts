import React from "react";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { motion } from "framer-motion";
import { format } from "date-fns";
import { User, Clock, GitBranch, Crown } from "lucide-react";
import { SafeMarkdown } from "../../markdown/SafeMarkdown";
import { DocumentSummaryRevision } from "./graphql/documentSummaryQueries";
import { useReactiveVar } from "@apollo/client";
import { backendUserObj } from "../../../../graphql/cache";
import { getCreatorDisplay } from "../../../../utils/userDisplay";

interface SummaryPreviewCardProps {
  version: DocumentSummaryRevision;
  index: number;
  totalCards: number;
  isFanned: boolean;
  isHovered: boolean;
  isActive?: boolean;
  activeIndex?: number;
  isLatest?: boolean;
  onClick?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  currentContent?: string;
}

const CardWrapper = styled(motion.div)`
  position: absolute;
  cursor: pointer;
  transform-style: preserve-3d;
  transform-origin: center bottom;
  pointer-events: auto;
`;

const CardContainer = styled(motion.div)<{ $isHovered: boolean }>`
  width: ${(props) => (props.$isHovered ? "310px" : "280px")};
  height: ${(props) => (props.$isHovered ? "190px" : "180px")};
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(12px);
  border: 1px solid
    ${(props) =>
      props.$isHovered ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 16px;
  padding: 16px;
  box-shadow: ${(props) =>
    props.$isHovered
      ? "0 12px 40px rgba(59, 130, 246, 0.25), 0 4px 12px rgba(0, 0, 0, 0.08)"
      : "0 4px 24px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04)"};
  overflow: hidden;
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);

  @media (max-width: 768px) {
    width: ${(props) => (props.$isHovered ? "290px" : "260px")};
    height: ${(props) => (props.$isHovered ? "180px" : "170px")};
  }
`;

const CardHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
`;

const VersionBadge = styled.div<{ $isCurrent?: boolean }>`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: ${(props) =>
    props.$isCurrent ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  color: ${(props) =>
    props.$isCurrent ? "white" : OS_LEGAL_COLORS.textSecondary};
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
`;

const AuthorInfo = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 11px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  gap: 2px;
`;

const ContentPreview = styled(motion.div)<{ $isHovered: boolean }>`
  flex: 1;
  overflow: hidden;
  position: relative;
  font-size: ${(props) => (props.$isHovered ? "13px" : "12px")};
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textTertiary};
  max-height: ${(props) => (props.$isHovered ? "160px" : "120px")};
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);

  /* Fade overlay for non-hovered state */
  &::after {
    content: "";
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: ${(props) => (props.$isHovered ? "20px" : "40px")};
    background: linear-gradient(
      to bottom,
      transparent,
      rgba(255, 255, 255, ${(props) => (props.$isHovered ? "0.8" : "0.98")})
    );
    transition: all 0.4s ease;
  }

  /* Scrollbar for hovered state */
  ${(props) =>
    props.$isHovered &&
    `
    overflow-y: auto;
    padding-right: 6px;
    
    &::-webkit-scrollbar {
      width: 4px;
    }
    
    &::-webkit-scrollbar-track {
      background: rgba(226, 232, 240, 0.3);
      border-radius: 2px;
    }
    
    &::-webkit-scrollbar-thumb {
      background: rgba(148, 163, 184, 0.5);
      border-radius: 2px;
      
      &:hover {
        background: rgba(148, 163, 184, 0.7);
      }
    }
  `}

  /* Markdown styling adjustments */
  h1, h2, h3, h4, h5, h6 {
    font-size: ${(props) => (props.$isHovered ? "15px" : "14px")};
    margin: 4px 0;
  }

  p {
    margin: 4px 0;
  }

  ul,
  ol {
    margin: 4px 0;
    padding-left: 16px;
  }

  code {
    font-size: ${(props) => (props.$isHovered ? "11px" : "10px")};
    padding: 1px 3px;
  }

  pre {
    font-size: ${(props) => (props.$isHovered ? "11px" : "10px")};
    padding: 4px;
    margin: 4px 0;
  }

  blockquote {
    margin: 4px 0;
    padding-left: 8px;
    border-left: 2px solid ${OS_LEGAL_COLORS.border};
  }
`;

const CardDate = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 8px;
`;

export const SummaryPreviewCard: React.FC<SummaryPreviewCardProps> = ({
  version,
  index,
  totalCards,
  isFanned,
  isHovered,
  isActive,
  activeIndex,
  isLatest = false,
  onClick,
  onMouseEnter,
  onMouseLeave,
  currentContent,
}) => {
  const currentUser = useReactiveVar(backendUserObj);
  const isMyVersion = currentUser?.id === version.author.id;

  // Calculate positions for carousel effect
  const getCardPosition = () => {
    const centerX = 0;
    const baseSpacing = isFanned ? 75 : 15;
    const hoverOffset = isHovered ? 40 : 0;

    if (isFanned && activeIndex !== undefined) {
      // Centered carousel mode - active card is always in center
      const relativeIndex = index - activeIndex;
      let x = centerX + relativeIndex * baseSpacing;
      let y = Math.abs(relativeIndex) * 5; // Cards further from center are slightly lower
      let z = 100 - Math.abs(relativeIndex) * 20; // Active card is closest
      let rotateY = relativeIndex * 15; // Cards rotate away from center
      let rotateZ = 0;
      let scale = 1 - Math.abs(relativeIndex) * 0.1; // Cards get smaller away from center

      // Active card gets special treatment
      if (index === activeIndex) {
        y = -5; // Raise it up slightly less
        z = 150; // Bring it forward
        scale = 1.02; // Make it only slightly larger
      }

      if (isHovered && index !== activeIndex) {
        // Non-active cards still respond to hover
        y -= 10;
        z += 20;
        scale += 0.05;
      }

      return { x, y, z, rotateY, rotateZ, scale };
    } else {
      // Original stacked mode
      const offset = ((totalCards - 1) * baseSpacing) / 2;
      let x = centerX + index * baseSpacing - offset;
      let y = isFanned ? 0 : -index * 8;
      let z = (totalCards - index) * 10;
      let rotateY = 0;
      let rotateZ = isFanned ? 0 : -index * 2;
      let scale = 1;

      if (isHovered) {
        // Move card forward and up when hovered
        x += hoverOffset;
        y -= 20;
        z += 50;
        rotateY = 5; // Slight 3D rotation
        rotateZ = 0; // Remove tilt when hovered
        scale = 1.05;
      }

      return { x, y, z, rotateY, rotateZ, scale };
    }
  };

  const position = getCardPosition();

  return (
    <CardWrapper
      animate={{
        x: position.x,
        y: position.y,
        z: position.z,
        rotateY: position.rotateY,
        rotateZ: position.rotateZ,
        scale: position.scale,
      }}
      transition={{
        type: "spring",
        stiffness: 100,
        damping: 20,
        mass: 1,
      }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      onClick={onClick}
      style={{
        zIndex: isActive
          ? 100
          : isHovered
          ? 50
          : 30 - Math.abs(index - (activeIndex || 0)),
      }}
      data-testid={`summary-card-${version.version}`}
    >
      <CardContainer $isHovered={isHovered || !!isActive}>
        <CardHeader>
          <VersionBadge $isCurrent={isLatest}>
            <GitBranch size={12} />v{version.version}
            {isLatest && " (Latest)"}
          </VersionBadge>
          <AuthorInfo>
            <div style={{ display: "flex", alignItems: "center", gap: "3px" }}>
              {isMyVersion ? (
                <>
                  <Crown
                    size={10}
                    style={{ color: OS_LEGAL_COLORS.folderIcon }}
                  />
                  <span
                    style={{
                      color: OS_LEGAL_COLORS.folderIcon,
                      fontWeight: 600,
                    }}
                  >
                    You
                  </span>
                </>
              ) : (
                <>
                  <User size={10} />
                  {getCreatorDisplay(version.author)}
                </>
              )}
            </div>
          </AuthorInfo>
        </CardHeader>

        <ContentPreview $isHovered={isHovered || !!isActive}>
          <SafeMarkdown>
            {(() => {
              const text = isLatest ? currentContent : version.snapshot;
              if (!text)
                return `Summary preview for version ${version.version}`;

              // Show more content when hovered
              const maxLength = isHovered ? 500 : 200;
              const truncated = text.slice(0, maxLength);
              return truncated + (text.length > maxLength ? "..." : "");
            })()}
          </SafeMarkdown>
        </ContentPreview>

        <CardDate>
          <Clock size={10} />
          {format(new Date(version.created), "MMM d, yyyy")}
        </CardDate>
      </CardContainer>
    </CardWrapper>
  );
};
