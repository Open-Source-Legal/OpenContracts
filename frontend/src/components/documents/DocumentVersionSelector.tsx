import React, { useState, useCallback, useRef, useEffect } from "react";
import { useLazyQuery, useQuery, useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { ChevronUp, ChevronDown } from "lucide-react";
import { Spinner } from "@os-legal/ui";
import { selectedDocVersion } from "../../graphql/cache";
import { GET_CORPUS_VERSIONS } from "../../graphql/queries";
import { GET_ANNOTATION_REVIEW_STATUS } from "../../graphql/annotationVersionReview";
import { getDocumentVersionUrl } from "../../utils/navigationUtils";

interface CorpusVersion {
  versionNumber: number;
  documentId: string;
  documentSlug: string | null;
  created: string;
  /** Whether this is the latest (most recent) version in the corpus. */
  isCurrent: boolean;
}

const SelectorContainer = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  position: relative;
`;

const VersionPill = styled.button<{
  $isOutdated: boolean;
  $hasHistory: boolean;
}>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 12px;
  border: 1px solid;
  cursor: ${(props) => (props.$hasHistory ? "pointer" : "default")};
  user-select: none;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  line-height: 1.6;

  background: ${(props) => {
    if (props.$isOutdated) return "rgba(249, 115, 22, 0.12)";
    if (props.$hasHistory) return "rgba(59, 130, 246, 0.12)";
    return "rgba(100, 116, 139, 0.08)";
  }};

  color: ${(props) => {
    if (props.$isOutdated) return "#c2410c";
    if (props.$hasHistory) return OS_LEGAL_COLORS.primaryBlueHover;
    return OS_LEGAL_COLORS.textSecondary;
  }};

  border-color: ${(props) => {
    if (props.$isOutdated) return "rgba(249, 115, 22, 0.25)";
    if (props.$hasHistory) return "rgba(59, 130, 246, 0.25)";
    return "rgba(100, 116, 139, 0.15)";
  }};

  &:hover {
    ${(props) =>
      props.$hasHistory &&
      `
      transform: translateY(-1px);
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
      background: ${
        props.$isOutdated
          ? "rgba(249, 115, 22, 0.2)"
          : "rgba(59, 130, 246, 0.2)"
      };
    `}
  }

  &:active {
    ${(props) => props.$hasHistory && `transform: translateY(0);`}
  }
`;

const DropdownMenu = styled.div`
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 1000;
  min-width: 220px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  overflow: hidden;
`;

const DropdownItem = styled.button<{
  $isActive: boolean;
  $isFocused: boolean;
}>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 14px;
  border: none;
  background: ${(props) => {
    if (props.$isActive) return OS_LEGAL_COLORS.blueSurface;
    if (props.$isFocused) return OS_LEGAL_COLORS.surfaceHover;
    return "transparent";
  }};
  cursor: pointer;
  text-align: left;
  transition: background 0.15s ease;
  outline: ${(props) =>
    props.$isFocused ? `2px solid ${OS_LEGAL_COLORS.primaryBlue}` : "none"};
  outline-offset: -2px;

  &:hover {
    background: ${(props) =>
      props.$isActive
        ? OS_LEGAL_COLORS.blueBorder
        : OS_LEGAL_COLORS.surfaceHover};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
  }
`;

const VersionLabel = styled.span`
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const VersionDate = styled.span`
  font-size: 11px;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-left: 8px;
`;

const CurrentTag = styled.span`
  font-size: 10px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  background: ${OS_LEGAL_COLORS.blueSurface};
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
`;

const DropdownLoading = styled.div`
  padding: 16px;
  text-align: center;
`;

interface DocumentVersionSelectorProps {
  documentId: string;
  corpusId: string;
}

/**
 * DocumentVersionSelector - Inline version badge and dropdown for switching
 * between document versions.
 *
 * Renders in the document header's MetadataRow. Shows current version number
 * with visual indicators:
 * - Gray: Single version (no history)
 * - Blue: Multiple versions, viewing latest
 * - Orange: Viewing an older version (not latest)
 *
 * Clicking opens a dropdown to switch versions via the ?v=N URL parameter.
 *
 * Supports full keyboard navigation per WAI-ARIA listbox pattern:
 * - Arrow Up/Down: Move focus between options
 * - Home/End: Jump to first/last option
 * - Enter/Space: Select the focused option
 * - Escape: Close the dropdown
 */
export const DocumentVersionSelector: React.FC<
  DocumentVersionSelectorProps
> = ({ documentId, corpusId }) => {
  const { data: reviewStatus } = useQuery(GET_ANNOTATION_REVIEW_STATUS, {
    variables: { documentId, corpusId },
  });
  const reviewCount = reviewStatus?.document?.annotationsNeedingReview ?? 0;
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const location = useLocation();
  const navigate = useNavigate();
  const currentVersion = useReactiveVar(selectedDocVersion);

  const [fetchVersions, { loading, data: versionsData }] = useLazyQuery(
    GET_CORPUS_VERSIONS,
    { fetchPolicy: "cache-first" }
  );
  const versions: CorpusVersion[] =
    versionsData?.document?.corpusVersions ?? [];

  // Sort descending (newest first) once for consistent indexing
  const sortedVersions = [...versions].sort(
    (a, b) => b.versionNumber - a.versionNumber
  );

  const hasHistory = sortedVersions.length > 1;
  const latestVersion = versions.find((v) => v.isCurrent);
  const displayVersion = currentVersion ?? latestVersion?.versionNumber ?? null;
  const isOutdated =
    currentVersion !== null &&
    !versions.find((v) => v.versionNumber === currentVersion && v.isCurrent);

  const handleToggle = useCallback(() => {
    setIsOpen((prev) => {
      const opening = !prev;
      if (opening) {
        // Focus the currently active option when opening
        const activeIdx = sortedVersions.findIndex((v) =>
          currentVersion === null
            ? v.isCurrent
            : v.versionNumber === currentVersion
        );
        setFocusedIndex(activeIdx >= 0 ? activeIdx : 0);
      } else {
        setFocusedIndex(-1);
      }
      return opening;
    });
  }, [sortedVersions, currentVersion]);

  const handleVersionSelect = useCallback(
    (version: CorpusVersion) => {
      setIsOpen(false);
      setFocusedIndex(-1);
      const url = getDocumentVersionUrl(location, version);
      navigate(url, { replace: url === location.pathname + location.search });
    },
    [location, navigate]
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const pillRef = useRef<HTMLButtonElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
        setFocusedIndex(-1);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  // Keyboard navigation for listbox
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      switch (event.key) {
        case "Escape":
          setIsOpen(false);
          setFocusedIndex(-1);
          pillRef.current?.focus();
          event.preventDefault();
          break;
        case "ArrowDown":
          setFocusedIndex((prev) =>
            prev < sortedVersions.length - 1 ? prev + 1 : prev
          );
          event.preventDefault();
          break;
        case "ArrowUp":
          setFocusedIndex((prev) => (prev > 0 ? prev - 1 : prev));
          event.preventDefault();
          break;
        case "Home":
          setFocusedIndex(0);
          event.preventDefault();
          break;
        case "End":
          setFocusedIndex(sortedVersions.length - 1);
          event.preventDefault();
          break;
        case "Enter":
        case " ": {
          if (focusedIndex >= 0 && focusedIndex < sortedVersions.length) {
            const version = sortedVersions[focusedIndex];
            handleVersionSelect(version);
            pillRef.current?.focus();
          }
          event.preventDefault();
          break;
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, focusedIndex, sortedVersions, handleVersionSelect]);

  // Fetch versions on mount to know if there's history
  useEffect(() => {
    if (documentId && corpusId) {
      fetchVersions({ variables: { documentId, corpusId } });
    }
  }, [documentId, corpusId, fetchVersions]);

  // Don't render anything until we have data
  if (loading && versions.length === 0) {
    return null;
  }

  // Single version, no history - show simple badge
  if (!hasHistory) {
    return (
      <SelectorContainer>
        <VersionPill $isOutdated={false} $hasHistory={false}>
          {displayVersion !== null ? `v${displayVersion}` : "v?"}
        </VersionPill>
      </SelectorContainer>
    );
  }

  return (
    <SelectorContainer ref={containerRef}>
      <VersionPill
        ref={pillRef}
        $isOutdated={isOutdated}
        $hasHistory={hasHistory}
        onClick={handleToggle}
        aria-label={`Version ${displayVersion ?? "?"} of ${
          sortedVersions.length
        }, click to switch versions`}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-activedescendant={
          isOpen && focusedIndex >= 0
            ? `version-option-${sortedVersions[focusedIndex]?.versionNumber}`
            : undefined
        }
        title={
          isOpen
            ? undefined
            : isOutdated
            ? `Viewing version ${displayVersion ?? "?"} of ${
                sortedVersions.length
              }. A newer version is available.`
            : `Version ${displayVersion ?? "?"} of ${
                sortedVersions.length
              }. Click to switch versions.`
        }
      >
        v{displayVersion ?? "?"}
        {reviewCount > 0 && <span> · {reviewCount} to review</span>}
        <span style={{ fontSize: "9px", opacity: 0.7 }}>
          / {sortedVersions.length}
        </span>
        {isOpen ? (
          <ChevronUp size={9} style={{ margin: 0 }} />
        ) : (
          <ChevronDown size={9} style={{ margin: 0 }} />
        )}
      </VersionPill>

      {isOpen && (
        <DropdownMenu role="listbox" aria-label="Document versions">
          {loading ? (
            <DropdownLoading>
              <Spinner size="sm" />
            </DropdownLoading>
          ) : (
            sortedVersions.map((version, index) => {
              const isActive =
                currentVersion === null
                  ? version.isCurrent
                  : version.versionNumber === currentVersion;

              return (
                <DropdownItem
                  key={version.versionNumber}
                  id={`version-option-${version.versionNumber}`}
                  $isActive={isActive}
                  $isFocused={index === focusedIndex}
                  onClick={() => handleVersionSelect(version)}
                  onMouseEnter={() => setFocusedIndex(index)}
                  role="option"
                  aria-selected={isActive}
                  tabIndex={-1}
                >
                  <div>
                    <VersionLabel>Version {version.versionNumber}</VersionLabel>
                    <VersionDate>
                      {new Date(version.created).toLocaleDateString()}
                    </VersionDate>
                  </div>
                  {version.isCurrent && <CurrentTag>Latest</CurrentTag>}
                </DropdownItem>
              );
            })
          )}
        </DropdownMenu>
      )}
    </SelectorContainer>
  );
};

export default DocumentVersionSelector;
