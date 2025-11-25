import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import { color } from "../../theme/colors";

const MarkdownContainer = styled.div`
  p {
    margin: 0 0 8px 0;
  }

  code {
    background: ${color.N3};
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
    font-family: monospace;
  }

  pre {
    background: ${color.N3};
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
  }

  ul,
  ol {
    padding-left: 24px;
    margin: 8px 0;
  }

  strong {
    font-weight: 600;
  }

  em {
    font-style: italic;
  }

  blockquote {
    border-left: 3px solid ${color.B5};
    padding-left: 12px;
    margin: 8px 0;
    color: ${color.N7};
  }
`;

const MentionLink = styled.a<{ $type: string }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  text-decoration: none;
  vertical-align: middle;
  margin: 0 2px;

  background: ${(props) => {
    if (props.$type === "user")
      return "linear-gradient(135deg, #06b6d415 0%, #10b98115 100%)";
    if (props.$type === "corpus")
      return "linear-gradient(135deg, #667eea15 0%, #764ba215 100%)";
    if (props.$type === "document")
      return "linear-gradient(135deg, #f093fb15 0%, #f5576c15 100%)";
    if (props.$type === "annotation")
      return "linear-gradient(135deg, #fbc2eb15 0%, #a6c1ee15 100%)";
    return "linear-gradient(135deg, #e0e0e015 0%, #c0c0c015 100%)";
  }};

  border: 1px solid
    ${(props) => {
      if (props.$type === "user") return "#10b98160";
      if (props.$type === "corpus") return color.P4;
      if (props.$type === "document") return "#f5576c40";
      if (props.$type === "annotation") return "#a6c1ee80";
      return color.N4;
    }};

  color: ${(props) => {
    if (props.$type === "user") return "#0d9488";
    if (props.$type === "corpus") return color.P8;
    if (props.$type === "document") return "#c41e3a";
    if (props.$type === "annotation") return "#4a5baf";
    return color.N8;
  }};

  &:hover {
    background: ${(props) => {
      if (props.$type === "user")
        return "linear-gradient(135deg, #06b6d425 0%, #10b98125 100%)";
      if (props.$type === "corpus")
        return "linear-gradient(135deg, #667eea25 0%, #764ba225 100%)";
      if (props.$type === "document")
        return "linear-gradient(135deg, #f093fb25 0%, #f5576c25 100%)";
      if (props.$type === "annotation")
        return "linear-gradient(135deg, #fbc2eb25 0%, #a6c1ee25 100%)";
      return "linear-gradient(135deg, #e0e0e025 0%, #c0c0c025 100%)";
    }};

    border-color: ${(props) => {
      if (props.$type === "user") return "#10b981";
      if (props.$type === "corpus") return color.P6;
      if (props.$type === "document") return "#f5576c80";
      if (props.$type === "annotation") return "#a6c1ee";
      return color.N6;
    }};

    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  }

  &:active {
    transform: translateY(0);
  }
`;

const RegularLink = styled.a`
  color: ${color.B7};
  text-decoration: underline;

  &:hover {
    color: ${color.B8};
  }
`;

interface MarkdownMessageRendererProps {
  content: string;
}

/**
 * Render markdown message content with styled mentions
 * Detects mention links by their URL pattern and styles them differently
 *
 * Part of Issue #623 - @ Mentions Feature (Extended)
 */
export function MarkdownMessageRenderer({
  content,
}: MarkdownMessageRendererProps) {
  const navigate = useNavigate();

  /**
   * Detect mention type from URL pattern
   */
  const detectMentionType = (href: string): string | null => {
    if (!href) return null;

    // User: /users/{slug}
    if (href.startsWith("/users/")) return "user";

    // Corpus: /c/{creator}/{slug}
    if (href.startsWith("/c/")) return "corpus";

    // Document: /d/{creator}/{corpus}/{doc}
    if (href.startsWith("/d/")) {
      // Annotation has query param ?ann=
      if (href.includes("?ann=") || href.includes("&ann=")) {
        return "annotation";
      }
      return "document";
    }

    return null;
  };

  return (
    <MarkdownContainer>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          // Custom link renderer to style mentions
          a: ({ node, href, children, ...props }) => {
            const mentionType = detectMentionType(href || "");

            if (mentionType) {
              // This is a mention link - style it specially
              return (
                <MentionLink
                  href={href}
                  $type={mentionType}
                  onClick={(e) => {
                    e.preventDefault();
                    if (href) {
                      navigate(href);
                    }
                  }}
                  {...props}
                >
                  {children}
                </MentionLink>
              );
            }

            // Regular link
            return (
              <RegularLink
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              >
                {children}
              </RegularLink>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </MarkdownContainer>
  );
}
