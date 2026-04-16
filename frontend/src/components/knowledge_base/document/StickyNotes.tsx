import { motion } from "framer-motion";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

export const PostItNote = styled(motion.button)<{ $readOnly?: boolean }>`
  background: #fff7b1;
  padding: 1.25rem;
  border-radius: 2px;
  box-shadow: 0 1px 1px rgba(0, 0, 0, 0.05), 0 10px 15px -8px rgba(0, 0, 0, 0.1);
  position: relative;
  border: none;
  width: 100%;
  text-align: left;
  cursor: ${(props) => (props.$readOnly ? "default" : "pointer")};
  transform-origin: center;
  transition: all 0.2s ease;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 28px;
    background: rgba(0, 0, 0, 0.02);
    border-radius: 2px 2px 0 0;
  }
  &::after {
    content: "";
    position: absolute;
    top: -4px;
    left: 50%;
    transform: translateX(-50%);
    width: 40%;
    height: 8px;
    background: rgba(0, 0, 0, 0.03);
    border-radius: 0 0 3px 3px;
  }

  .edit-indicator {
    position: absolute;
    top: 8px;
    right: 8px;
    opacity: 0;
    transition: opacity 0.2s ease;
    color: ${OS_LEGAL_COLORS.textSecondary};
    background: rgba(255, 255, 255, 0.8);
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  &:hover .edit-indicator {
    opacity: ${(props) => (props.$readOnly ? 0 : 1)};
  }

  .title {
    font-family: "Kalam", cursive;
    font-size: 1rem;
    font-weight: 600;
    color: #1a365d;
    margin-bottom: 0.75rem;
    line-height: 1.3;
    word-wrap: break-word;
    overflow-wrap: break-word;
    max-height: 60px;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .content {
    max-height: 200px;
    overflow: hidden;
    position: relative;
    font-family: "Kalam", cursive;
    line-height: 1.6;
    color: #2c3e50;
    padding-right: 24px; /* Make room for edit indicator */
    &::after {
      content: "";
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 40px;
      background: linear-gradient(transparent, #fff7b1);
    }
  }
  .meta {
    margin-top: 1rem;
    font-size: 0.75rem;
    color: ${OS_LEGAL_COLORS.textSecondary};
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
  }
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 1px 1px rgba(0, 0, 0, 0.05),
      0 15px 25px -12px rgba(0, 0, 0, 0.15);
  }
`;
