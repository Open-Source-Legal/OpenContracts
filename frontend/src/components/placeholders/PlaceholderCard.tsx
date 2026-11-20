import React from "react";
import styled from "styled-components";
import { FileQuestion } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

interface PlaceholderCardProps {
  title?: string;
  description?: string;
  style?: React.CSSProperties;
  image?: React.ReactNode;
  compact?: boolean;
}

const CardContainer = styled.div<{ $compact?: boolean }>`
  background: white;
  border-radius: 12px;
  padding: ${(props) => (props.$compact ? "2rem" : "3rem")};
  text-align: center;
  box-shadow:
    0 1px 3px 0 rgba(0, 0, 0, 0.1),
    0 1px 2px 0 rgba(0, 0, 0, 0.06);
  transition: all 0.2s ease;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: ${(props) => (props.$compact ? "240px" : "320px")};

  &:hover {
    transform: translateY(-4px);
    box-shadow:
      0 20px 25px -5px rgba(0, 0, 0, 0.1),
      0 10px 10px -5px rgba(0, 0, 0, 0.04);
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }
`;

const IconWrapper = styled.div`
  width: 56px;
  height: 56px;
  margin: 0 auto 1.5rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
  border: 1px solid ${OS_LEGAL_COLORS.border};

  svg {
    width: 28px;
    height: 28px;
    stroke-width: 1.5px;
  }
`;

const ImageWrapper = styled.div<{ $compact?: boolean }>`
  margin: 0 auto 1.5rem;
  opacity: 1;
  transition: opacity 0.2s ease;
  width: ${(props) => (props.$compact ? "60%" : "75%")};
  max-width: 300px;
  display: flex;
  align-items: center;
  justify-content: center;

  &:hover {
    opacity: 0.85;
  }

  img {
    max-width: 100%;
    height: auto;
    max-height: 180px;
    object-fit: contain;
  }
`;

const Title = styled.h3<{ $compact?: boolean }>`
  color: #0f172a;
  font-size: ${(props) => (props.$compact ? "1rem" : "1.125rem")};
  font-weight: 600;
  margin: 0 0 0.75rem;
  position: relative;
  z-index: 1;
  letter-spacing: -0.01em;
`;

const Description = styled.p<{ $compact?: boolean }>`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: ${(props) => (props.$compact ? "0.875rem" : "0.9375rem")};
  line-height: 1.5;
  margin: 0;
  max-width: ${(props) => (props.$compact ? "20rem" : "24rem")};
  margin: 0 auto;
  position: relative;
  z-index: 1;
  font-weight: 400;
`;

const Wave = styled.div`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 80px;
  background: linear-gradient(
    180deg,
    transparent 0%,
    ${OS_LEGAL_COLORS.surfaceHover} 100%
  );
  border-radius: 0 0 12px 12px;
  z-index: 0;
  opacity: 0.5;
`;

export const PlaceholderCard: React.FC<PlaceholderCardProps> = ({
  title = "No Results Found",
  description = "We couldn't find any items matching your current filters or search criteria.",
  style,
  image,
  compact = false,
}) => (
  <CardContainer style={style} $compact={compact}>
    {image ? (
      <ImageWrapper $compact={compact}>{image}</ImageWrapper>
    ) : (
      <IconWrapper>
        <FileQuestion />
      </IconWrapper>
    )}
    <Title $compact={compact}>{title}</Title>
    {description && <Description $compact={compact}>{description}</Description>}
    <Wave />
  </CardContainer>
);
