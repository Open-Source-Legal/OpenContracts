import styled from "styled-components";
import { motion } from "framer-motion";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery,
} from "../styles/corpusDesignTokens";

export const AboutCard = styled(motion.div)<{ $minimal?: boolean }>`
  background: ${(props) =>
    props.$minimal ? "transparent" : CORPUS_COLORS.white};
  border-radius: ${(props) => (props.$minimal ? "0" : CORPUS_RADII.lg)};
  box-shadow: ${(props) => (props.$minimal ? "none" : CORPUS_SHADOWS.card)};
  overflow: ${(props) => (props.$minimal ? "visible" : "hidden")};
  border: ${(props) =>
    props.$minimal ? "none" : `1px solid ${CORPUS_COLORS.slate[200]}`};
  display: flex;
  flex-direction: column;
  position: relative;
  flex: 1;
  min-height: ${(props) => (props.$minimal ? "100%" : "0")};
  height: ${(props) => (props.$minimal ? "auto" : "100%")};
  max-height: ${(props) => (props.$minimal ? "none" : "100%")};
`;

export const AboutHeader = styled.div`
  padding: 1.5rem 2rem;
  border-bottom: 1px solid ${CORPUS_COLORS.slate[100]};
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: ${CORPUS_COLORS.slate[50]};
  flex-shrink: 0;

  ${mediaQuery.tablet} {
    padding: 1rem 1.25rem;
  }
`;

export const AboutTitle = styled.h2`
  margin: 0;
  font-family: ${CORPUS_FONTS.serif};
  font-size: 1.5rem;
  font-weight: 400;
  color: ${CORPUS_COLORS.slate[800]};
  display: flex;
  align-items: center;
  gap: 0.75rem;
  letter-spacing: -0.01em;

  svg {
    color: ${CORPUS_COLORS.teal[700]};
    opacity: 0.9;
  }

  ${mediaQuery.tablet} {
    font-size: 1.125rem;
    gap: 0.5rem;

    svg {
      width: 18px;
      height: 18px;
    }
  }
`;

export const ActionButtons = styled.div`
  display: flex;
  gap: 0.5rem;
  align-items: center;
`;

export const HistoryButton = styled.button`
  background: transparent;
  color: ${CORPUS_COLORS.slate[500]};
  border: none;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.375rem;
  cursor: pointer;
  border-radius: ${CORPUS_RADII.sm};
  transition: all ${CORPUS_TRANSITIONS.fast};

  &:hover {
    background: ${CORPUS_COLORS.slate[100]};
    color: ${CORPUS_COLORS.teal[700]};
  }

  &:active {
    transform: scale(0.98);
  }

  ${mediaQuery.tablet} {
    padding: 0.375rem 0.5rem;
    font-size: 0.75rem;
  }
`;

export const EditButton = styled.button`
  background: ${CORPUS_COLORS.teal[700]};
  color: ${CORPUS_COLORS.white};
  border: none;
  border-radius: ${CORPUS_RADII.md};
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 0.375rem;
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};

  &:hover {
    background: ${CORPUS_COLORS.teal[600]};
  }

  &:active {
    transform: scale(0.98);
  }

  ${mediaQuery.tablet} {
    padding: 0.375rem 0.75rem;
    font-size: 0.75rem;
  }
`;

export const AboutContent = styled.div<{ $minimal?: boolean }>`
  padding: ${(props) => (props.$minimal ? "0" : "2rem")};
  padding-bottom: ${(props) => (props.$minimal ? "0" : "4rem")};
  color: ${CORPUS_COLORS.slate[600]};
  line-height: 1.8;
  font-size: 1.0625rem;
  flex: 1;
  overflow-y: ${(props) => (props.$minimal ? "visible" : "auto")};
  overflow-x: hidden;
  position: relative;
  min-height: 0;
  max-height: 100%;

  ${mediaQuery.tablet} {
    padding: ${(props) => (props.$minimal ? "1rem 1.5rem" : "1.25rem")};
    padding-bottom: ${(props) => (props.$minimal ? "1.5rem" : "3rem")};
    font-size: 0.9375rem;
    line-height: 1.65;
  }

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: ${CORPUS_COLORS.slate[50]};
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: ${CORPUS_COLORS.slate[200]};
    border-radius: 4px;

    &:hover {
      background: ${CORPUS_COLORS.slate[300]};
    }
  }

  &.empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 3rem 2rem;
    color: ${CORPUS_COLORS.slate[400]};
    min-height: 200px;
    overflow-y: visible;

    ${mediaQuery.tablet} {
      padding: 2rem 1rem;
      min-height: 150px;
    }
  }

  /* Enhanced Markdown styling with OS-Legal design system */
  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    font-family: ${CORPUS_FONTS.serif};
    margin-top: 2rem;
    margin-bottom: 1rem;
    color: ${CORPUS_COLORS.teal[700]};
    font-weight: 400;
    letter-spacing: -0.01em;
    line-height: 1.3;

    &:first-child {
      margin-top: 0;
    }
  }

  h1 {
    font-size: 2rem;
    color: ${CORPUS_COLORS.slate[800]};
    padding-bottom: 0.75rem;
    border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
    margin-bottom: 1.5rem;
  }

  h2 {
    font-size: 1.5rem;
    color: ${CORPUS_COLORS.slate[800]};
  }

  h3 {
    font-size: 1.25rem;
    color: ${CORPUS_COLORS.teal[700]};
  }

  h4,
  h5,
  h6 {
    font-size: 1.125rem;
    color: ${CORPUS_COLORS.teal[700]};
  }

  p {
    margin-bottom: 1.125rem;
    color: ${CORPUS_COLORS.slate[600]};
  }

  ul,
  ol {
    margin-bottom: 1.125rem;
    padding-left: 1.5rem;
    color: ${CORPUS_COLORS.slate[600]};
  }

  li {
    margin-bottom: 0.5rem;
  }

  strong {
    color: ${CORPUS_COLORS.slate[800]};
    font-weight: 600;
  }

  code {
    background: ${CORPUS_COLORS.slate[50]};
    border: 1px solid ${CORPUS_COLORS.slate[200]};
    padding: 0.125rem 0.375rem;
    border-radius: 4px;
    font-size: 0.875em;
    font-family: ${CORPUS_FONTS.mono};
    color: ${CORPUS_COLORS.teal[700]};
  }

  pre {
    background: ${CORPUS_COLORS.slate[50]};
    border: 1px solid ${CORPUS_COLORS.slate[200]};
    padding: 1rem;
    border-radius: ${CORPUS_RADII.md};
    overflow-x: auto;
    margin-bottom: 1.125rem;

    code {
      border: none;
      padding: 0;
      background: transparent;
    }
  }

  blockquote {
    border-left: 3px solid ${CORPUS_COLORS.teal[700]};
    padding-left: 1rem;
    margin: 1.25rem 0;
    color: ${CORPUS_COLORS.slate[600]};
    font-style: italic;
  }

  a {
    color: ${CORPUS_COLORS.teal[700]};
    text-decoration: none;
    font-weight: 500;
    transition: color ${CORPUS_TRANSITIONS.fast};

    &:hover {
      color: ${CORPUS_COLORS.teal[600]};
      text-decoration: underline;
    }
  }

  hr {
    border: none;
    height: 1px;
    background: ${CORPUS_COLORS.slate[200]};
    margin: 2rem 0;
  }
`;

export const AddDescriptionButton = styled.button`
  background: ${CORPUS_COLORS.white};
  color: ${CORPUS_COLORS.teal[700]};
  border: 2px dashed ${CORPUS_COLORS.slate[300]};
  border-radius: ${CORPUS_RADII.md};
  padding: 1rem 1.5rem;
  font-weight: 500;
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;

  &:hover {
    border-color: ${CORPUS_COLORS.teal[700]};
    background: ${CORPUS_COLORS.teal[50]};
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
  }
`;

export const LoadingPlaceholder = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
  animation: pulse 1.5s ease-in-out infinite;

  @keyframes pulse {
    0%,
    100% {
      opacity: 0.5;
    }
    50% {
      opacity: 0.8;
    }
  }

  .title-skeleton {
    width: 200px;
    height: 24px;
    background: linear-gradient(
      90deg,
      ${CORPUS_COLORS.slate[200]} 0%,
      ${CORPUS_COLORS.slate[100]} 50%,
      ${CORPUS_COLORS.slate[200]} 100%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
    border-radius: 6px;
  }

  .line-skeleton {
    height: 16px;
    background: linear-gradient(
      90deg,
      ${CORPUS_COLORS.slate[200]} 0%,
      ${CORPUS_COLORS.slate[100]} 50%,
      ${CORPUS_COLORS.slate[200]} 100%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
    border-radius: 4px;

    &.short {
      width: 60%;
    }
    &.medium {
      width: 80%;
    }
    &.long {
      width: 100%;
    }
  }

  .paragraph-skeleton {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  @keyframes shimmer {
    0% {
      background-position: -200% 0;
    }
    100% {
      background-position: 200% 0;
    }
  }
`;
