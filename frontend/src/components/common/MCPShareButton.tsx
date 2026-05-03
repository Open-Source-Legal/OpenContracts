import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useLayoutEffect,
} from "react";
import { createPortal } from "react-dom";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { Cable, Copy, Check, ExternalLink, Info, Lock } from "lucide-react";
import { toast } from "react-toastify";
import { Button, Input } from "@os-legal/ui";

// Popover sizing constants (kept local since they are tightly coupled to the
// styled component below and the responsive breakpoint).
const POPOVER_WIDTH = 340;
const POPOVER_VIEWPORT_MARGIN = 16;
const POPOVER_TRIGGER_GAP = 8;
const POPOVER_MOBILE_BREAKPOINT = 480;

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// Note: Using custom popover since @os-legal/ui doesn't have a Popover component.
// Button and Input components use the design system.
// ═══════════════════════════════════════════════════════════════════════════════

const Container = styled.div`
  position: relative;
  display: inline-flex;
`;

// Portaled to document.body and positioned via inline `top`/`left`/`width`
// computed from the trigger's bounding rect so the popover escapes ancestor
// `overflow: hidden` (e.g. the corpus list `PageContainer`) and isn't subject
// to sibling card stacking contexts.
const Popover = styled.div<{ $visible: boolean }>`
  position: fixed;
  z-index: 10000;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.12);
  opacity: ${(props) => (props.$visible ? 1 : 0)};
  visibility: ${(props) => (props.$visible ? "visible" : "hidden")};
  transform: ${(props) =>
    props.$visible ? "translateY(0) scale(1)" : "translateY(-8px) scale(0.95)"};
  transition: opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    transform 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    visibility 0.2s cubic-bezier(0.4, 0, 0.2, 1);
`;

const PopoverHeader = styled.div`
  padding: 16px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
`;

const PopoverTitle = styled.h4`
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: flex;
  align-items: center;
  gap: 8px;

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const PopoverDescription = styled.p`
  margin: 0;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.4;
`;

const PopoverContent = styled.div`
  padding: 16px;
`;

const UrlLabel = styled.label`
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-bottom: 6px;
`;

const UrlContainer = styled.div`
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  align-items: stretch;

  /* Style the Input component wrapper */
  & > div:first-child {
    flex: 1;
    min-width: 0;
  }

  /* Style the input inside */
  input {
    font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
    font-size: 13px;
  }
`;

const CopyButtonWrapper = styled.div`
  flex-shrink: 0;

  /* Override Button sizing for square copy button */
  button {
    width: 40px;
    height: 40px;
    padding: 0;
    min-width: unset;
  }
`;

const SetupHint = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px;
  background: #f0fdfa;
  border-radius: 8px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.accent};
  line-height: 1.5;

  svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    margin-top: 2px;
  }
`;

const SetupLink = styled.a`
  color: ${OS_LEGAL_COLORS.accent};
  font-weight: 500;
  text-decoration: underline;
  text-underline-offset: 2px;

  &:hover {
    color: ${OS_LEGAL_COLORS.accentHover};
  }
`;

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export interface MCPShareButtonProps {
  /** Corpus slug used to construct the MCP endpoint URL */
  corpusSlug: string;
  /**
   * Whether the corpus is publicly accessible. When false, the popover
   * explains that the corpus must be made public to expose an MCP endpoint
   * (the backend MCP server only serves public corpora).
   */
  isPublic?: boolean;
  /** Whether to show the button label (default: true) */
  showLabel?: boolean;
  /** Button size variant */
  size?: "sm" | "md";
  /** Test ID for the component */
  testId?: string;
}

/**
 * MCPShareButton - Button with popover for sharing corpus MCP endpoint
 *
 * Displays a button that, when clicked, shows a popover with:
 * - For public corpora: the MCP endpoint URL with copy-to-clipboard and
 *   brief setup instructions
 * - For private corpora: an explanation that the corpus must be made public
 *   before an MCP endpoint is exposed
 *
 * Always rendered so users can discover MCP regardless of corpus visibility.
 */
export const MCPShareButton: React.FC<MCPShareButtonProps> = ({
  corpusSlug,
  isPublic = true,
  showLabel = true,
  size = "md",
  testId = "mcp-share-button",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [coords, setCoords] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Construct the MCP endpoint URL
  const mcpUrl = `${window.location.origin}/mcp/corpus/${corpusSlug}`;

  // Compute popover position from the trigger's viewport rect, clamped so it
  // never overflows the viewport horizontally (responsive mode fix).
  const updatePosition = useCallback(() => {
    if (!containerRef.current) return;
    const trigger = containerRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const isMobile = viewportWidth <= POPOVER_MOBILE_BREAKPOINT;
    const width = isMobile
      ? Math.max(0, viewportWidth - POPOVER_VIEWPORT_MARGIN * 2)
      : POPOVER_WIDTH;

    let left = trigger.left;
    if (left + width > viewportWidth - POPOVER_VIEWPORT_MARGIN) {
      left = viewportWidth - width - POPOVER_VIEWPORT_MARGIN;
    }
    if (left < POPOVER_VIEWPORT_MARGIN) left = POPOVER_VIEWPORT_MARGIN;

    setCoords({
      top: trigger.bottom + POPOVER_TRIGGER_GAP,
      left,
      width,
    });
  }, []);

  // Re-position synchronously on open and on scroll/resize while open.
  useLayoutEffect(() => {
    if (!isOpen) return;
    updatePosition();
    const handler = () => updatePosition();
    // `true` (capture) catches scrolls in any nested scroll container.
    window.addEventListener("scroll", handler, true);
    window.addEventListener("resize", handler);
    return () => {
      window.removeEventListener("scroll", handler, true);
      window.removeEventListener("resize", handler);
    };
  }, [isOpen, updatePosition]);

  // Handle click outside to close popover. The popover is portaled to
  // document.body, so it isn't a descendant of containerRef — check both refs.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        containerRef.current?.contains(target) ||
        popoverRef.current?.contains(target)
      ) {
        return;
      }
      setIsOpen(false);
    };

    if (isOpen) {
      // Delay to prevent immediate close from the click that opened it
      const timer = setTimeout(() => {
        document.addEventListener("click", handleClickOutside);
      }, 100);
      return () => {
        clearTimeout(timer);
        document.removeEventListener("click", handleClickOutside);
      };
    }
  }, [isOpen]);

  // Handle escape key to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
    }
  }, [isOpen]);

  // Reset copied state when popover closes
  useEffect(() => {
    if (!isOpen) {
      setCopied(false);
    }
  }, [isOpen]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(mcpUrl);
      setCopied(true);
      toast.success("MCP endpoint URL copied to clipboard");

      // Reset copied state after 2 seconds
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      if (inputRef.current) {
        inputRef.current.select();
        document.execCommand("copy");
        setCopied(true);
        toast.success("MCP endpoint URL copied to clipboard");
        setTimeout(() => setCopied(false), 2000);
      }
    }
  }, [mcpUrl]);

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setIsOpen((prev) => !prev);
  }, []);

  return (
    <Container ref={containerRef} data-testid={testId}>
      <Button
        variant="secondary"
        size={size}
        leftIcon={
          isPublic ? (
            <Cable size={size === "sm" ? 14 : 16} />
          ) : (
            <Lock size={size === "sm" ? 14 : 16} />
          )
        }
        onClick={handleToggle}
        aria-label={
          isPublic ? "Share MCP endpoint" : "MCP endpoint (corpus is private)"
        }
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        data-testid={`${testId}-trigger`}
      >
        {showLabel ? "MCP" : undefined}
      </Button>

      {createPortal(
        <Popover
          ref={popoverRef}
          $visible={isOpen}
          role="dialog"
          aria-label="MCP endpoint sharing"
          data-testid={`${testId}-popover`}
          style={
            coords
              ? { top: coords.top, left: coords.left, width: coords.width }
              : undefined
          }
        >
          <PopoverHeader>
            <PopoverTitle>
              {isPublic ? <Cable /> : <Lock />}
              MCP Endpoint
            </PopoverTitle>
            <PopoverDescription>
              {isPublic
                ? "Connect AI assistants to this corpus using the Model Context Protocol."
                : "MCP endpoints are only exposed for public corpora. Make this corpus public from its settings to share it via the Model Context Protocol."}
            </PopoverDescription>
          </PopoverHeader>

          <PopoverContent>
            {isPublic ? (
              <>
                <UrlLabel htmlFor={`${testId}-url-input`}>
                  Endpoint URL
                </UrlLabel>
                <UrlContainer>
                  <Input
                    id={`${testId}-url-input`}
                    ref={inputRef}
                    type="text"
                    value={mcpUrl}
                    readOnly
                    onClick={(e) => (e.target as HTMLInputElement).select()}
                    data-testid={`${testId}-url-input`}
                  />
                  <CopyButtonWrapper>
                    <Button
                      variant="primary"
                      onClick={handleCopy}
                      aria-label={copied ? "Copied" : "Copy URL"}
                      data-testid={`${testId}-copy-button`}
                    >
                      {copied ? <Check size={18} /> : <Copy size={18} />}
                    </Button>
                  </CopyButtonWrapper>
                </UrlContainer>

                <SetupHint>
                  <ExternalLink />
                  <span>
                    Add this URL to your MCP client configuration.{" "}
                    <SetupLink
                      href="https://modelcontextprotocol.io/docs"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Learn more about MCP
                    </SetupLink>
                  </span>
                </SetupHint>
              </>
            ) : (
              <SetupHint>
                <Info size={16} />
                <span>
                  Once public, the endpoint will appear here for AI assistants
                  to connect.{" "}
                  <SetupLink
                    href="https://modelcontextprotocol.io/docs"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Learn more about MCP
                  </SetupLink>
                </span>
              </SetupHint>
            )}
          </PopoverContent>
        </Popover>,
        document.body
      )}
    </Container>
  );
};

export default MCPShareButton;
