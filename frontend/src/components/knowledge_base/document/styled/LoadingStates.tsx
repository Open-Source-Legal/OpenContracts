import React from "react";
import { motion } from "framer-motion";
import styled, { keyframes } from "styled-components";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

const shimmerAnimation = keyframes`
  0% {
    background-position: -1000px 0;
  }
  50% {
    background-position: 0 0;
  }
  100% {
    background-position: 1000px 0;
  }
`;

export const PlaceholderBase = styled.div`
  background: linear-gradient(
    90deg,
    #f0f0f0 0%,
    ${OS_LEGAL_COLORS.gray50} 20%,
    ${OS_LEGAL_COLORS.gray200} 40%,
    ${OS_LEGAL_COLORS.gray50} 60%,
    #f0f0f0 80%
  );
  background-size: 1000px 100%;
  animation: ${shimmerAnimation} 2.5s infinite ease-in-out;
  border-radius: 8px;
  position: relative;
  overflow: hidden;

  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(255, 255, 255, 0.4),
      transparent
    );
    transform: translateX(-100%);
    animation: shimmerOverlay 2.5s infinite;
  }
`;

const fadeIn = keyframes`
  from { opacity: 0; }
  to { opacity: 1; }
`;

export const PlaceholderItem = styled(PlaceholderBase)<{ delay: number }>`
  opacity: 0;
  animation: ${shimmerAnimation} 2.5s infinite ease-in-out,
    ${fadeIn} 0.5s forwards;
  animation-delay: ${(props) => props.delay}s;
`;

export const SummaryPlaceholder = styled.div`
  padding: 2rem;
  max-width: 800px;
  margin: 0 auto;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.02);

  ${PlaceholderBase} {
    height: 24px;
    margin-bottom: 1.25rem;
    opacity: 0;
    animation: ${shimmerAnimation} 2.5s infinite ease-in-out,
      fadeIn 0.5s forwards;

    &:nth-child(1) {
      width: 60%;
      animation-delay: 0.1s;
    }
    &:nth-child(2) {
      width: 95%;
      animation-delay: 0.2s;
    }
    &:nth-child(3) {
      width: 85%;
      animation-delay: 0.3s;
    }
    &:nth-child(4) {
      width: 90%;
      animation-delay: 0.4s;
    }
    &:nth-child(5) {
      width: 75%;
      animation-delay: 0.5s;
    }
  }
`;

export const NotePlaceholder = styled(motion.div)`
  padding: 2rem;
  background: white;
  border-radius: 16px;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(231, 234, 237, 0.7);
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;

  ${PlaceholderBase} {
    &.header {
      height: 24px;
      width: 40%;
      margin-bottom: 1.5rem;
    }

    &.content {
      height: 20px;
      margin-bottom: 1rem;

      &:last-child {
        margin-bottom: 0;
      }
      &:nth-child(2) {
        width: 95%;
      }
      &:nth-child(3) {
        width: 85%;
      }
    }
  }
`;

export const RelationshipPlaceholder = styled(motion.div)`
  padding: 2rem;
  background: white;
  border-radius: 16px;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(231, 234, 237, 0.7);
  max-width: 700px;
  margin-left: auto;
  margin-right: auto;

  ${PlaceholderBase} {
    &.type {
      height: 22px;
      width: 120px;
      margin-bottom: 1.5rem;
    }

    &.title {
      height: 24px;
      width: 80%;
      margin-bottom: 1rem;
    }

    &.meta {
      height: 18px;
      width: 50%;
    }
  }
`;

export const LoadingPlaceholders: React.FC<{
  type: "summary" | "notes" | "relationships";
}> = ({ type }) => {
  if (type === "summary") {
    return (
      <SummaryPlaceholder>
        {[...Array(5)].map((_, i) => (
          <PlaceholderItem key={i} delay={i * 0.1} />
        ))}
      </SummaryPlaceholder>
    );
  }

  return (
    <>
      {[...Array(3)].map((_, i) => {
        const Placeholder =
          type === "notes" ? NotePlaceholder : RelationshipPlaceholder;
        return (
          <Placeholder
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.4,
              delay: i * 0.15,
              ease: [0.4, 0, 0.2, 1],
            }}
          >
            <PlaceholderBase
              className={type === "notes" ? "header" : "type"}
              style={{ animationDelay: `${i * 0.1}s` }}
            />
            {type === "notes" ? (
              <>
                <PlaceholderBase
                  className="content"
                  style={{ animationDelay: `${i * 0.1 + 0.1}s` }}
                />
                <PlaceholderBase
                  className="content"
                  style={{ animationDelay: `${i * 0.1 + 0.2}s` }}
                />
              </>
            ) : (
              <>
                <PlaceholderBase
                  className="title"
                  style={{ animationDelay: `${i * 0.1 + 0.1}s` }}
                />
                <PlaceholderBase
                  className="meta"
                  style={{ animationDelay: `${i * 0.1 + 0.2}s` }}
                />
              </>
            )}
          </Placeholder>
        );
      })}
    </>
  );
};
