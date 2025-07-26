import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
  useCallback,
} from "react";
import Fuse from "fuse.js";
import { Form, Segment, Button } from "semantic-ui-react";
import { AnalysisType } from "../../types/graphql-api";
import styled from "styled-components";
import {
  Tag,
  Edit3,
  PlayCircle,
  CheckCircle,
  Timer,
  ChartNetwork,
  BarChart3,
  ChevronDown,
  ChevronUp,
  FileText,
  Eye,
  EyeOff,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

import useWindowDimensions from "../hooks/WindowDimensionHook";
import { useCorpusState } from "../annotator/context/CorpusAtom";
import {
  useAnalysisManager,
  useAnalysisSelection,
} from "../annotator/hooks/AnalysisHooks";
import { usePdfAnnotations } from "../annotator/hooks/AnnotationHooks";

import { AnnotationList } from "../annotator/display/components/AnnotationList";

/**
 * Props for AnalysisTraySelector
 */
interface AnalysisTraySelectorProps {
  /** Determines if the selector should be read-only */
  read_only: boolean;
  /** The list of available analyses */
  analyses: AnalysisType[];
  /** View mode for the cards */
  viewMode?: "compact" | "expanded";
  /** External search term */
  searchTerm?: string;
}

const TrayContainer = styled(Segment.Group)`
  height: 100%;
  display: flex !important;
  flex-direction: column !important;
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
`;

const SearchSegment = styled(Segment)`
  padding: 1rem !important;
  background: white !important;
  border: 1px solid #e2e8f0 !important;
  border-bottom: none !important;
  border-radius: 12px 12px 0 0 !important;

  .input {
    width: 100%;

    input {
      border-radius: 8px !important;
      border: 1px solid #e2e8f0 !important;
      padding: 0.6rem 1rem !important;
      transition: all 0.2s ease-in-out !important;

      &:focus {
        border-color: #4a90e2 !important;
        box-shadow: 0 0 0 2px rgba(74, 144, 226, 0.1) !important;
      }
    }

    i.icon {
      opacity: 0.5;
      transition: opacity 0.2s ease-in-out;

      &:hover {
        opacity: 1;
      }
    }
  }
`;

const AnalysisListSegment = styled(Segment)`
  flex: 1 !important;
  overflow-y: auto !important;
  background: white !important;
  border: 1px solid #e2e8f0 !important;
  border-radius: 0 0 12px 12px !important;
  padding: 0.75rem !important;

  &::-webkit-scrollbar {
    width: 4px;
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(74, 144, 226, 0.15);
    border-radius: 2px;

    &:hover {
      background: rgba(74, 144, 226, 0.25);
    }
  }
`;

const AnalysisCard = styled.div<{ $selected?: boolean; $compact?: boolean }>`
  padding: ${(props) => (props.$compact ? "1rem" : "1.75rem")};
  margin-bottom: ${(props) => (props.$compact ? "0.75rem" : "1.5rem")};
  background: ${(props) =>
    props.$selected
      ? "linear-gradient(165deg, rgba(74, 144, 226, 0.03), rgba(255, 255, 255, 0.5))"
      : "#ffffff"};
  border: 1px solid ${(props) => (props.$selected ? "#4a90e2" : "#edf2f7")};
  border-radius: ${(props) => (props.$compact ? "12px" : "20px")};
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  cursor: pointer;
  position: relative;
  overflow: hidden;
  box-shadow: ${(props) =>
    props.$selected
      ? "0 8px 32px rgba(74, 144, 226, 0.06)"
      : "0 1px 3px rgba(0, 0, 0, 0.01)"};

  .timestamps {
    margin-top: ${(props) => (props.$compact ? "1rem" : "2rem")};
    display: ${(props) => (props.$compact ? "none" : "flex")};
    gap: 1.25rem;
    padding: 0.5rem;
    background: ${(props) =>
      props.$selected ? "rgba(74, 144, 226, 0.02)" : "#fafbfc"};
    border-radius: 16px;

    .timestamp-row {
      flex: 1;
      padding: 0.875rem;
      background: ${(props) =>
        props.$selected ? "rgba(255, 255, 255, 0.8)" : "#ffffff"};
      border-radius: 12px;
      border: 1px solid
        ${(props) => (props.$selected ? "rgba(74, 144, 226, 0.1)" : "#edf2f7")};

      .label {
        font-size: 0.7rem;
        letter-spacing: 0.03em;
        color: #94a3b8;
        margin-bottom: 0.5rem;

        svg {
          width: 12px;
          height: 12px;
          vertical-align: -1px;
        }
      }

      .value {
        font-size: 0.8125rem;
        color: ${(props) => (props.$selected ? "#2d3748" : "#4a5568")};
      }
    }
  }

  &:hover {
    transform: translateY(${(props) => (props.$compact ? "-1px" : "-2px")});
    box-shadow: ${(props) =>
      props.$selected
        ? "0 12px 32px rgba(74, 144, 226, 0.12)"
        : "0 8px 24px rgba(0, 0, 0, 0.04)"};
  }

  &:active {
    transform: translateY(0);
  }

  .annotations-section {
    margin-top: ${(props) => (props.$compact ? "0.75rem" : "1.5rem")};
    padding-top: ${(props) => (props.$compact ? "0.75rem" : "1.5rem")};
    border-top: 1px solid
      ${(props) => (props.$selected ? "rgba(74, 144, 226, 0.12)" : "#f1f5f9")};
  }

  .annotations-container {
    margin-top: 1rem;
    background: #f8fafc;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
`;

const AnalysisHeader = styled.div<{ $selected?: boolean; $compact?: boolean }>`
  margin: ${(props) =>
    props.$compact
      ? "-1rem -1rem 0.75rem -1rem"
      : "-1.75rem -1.75rem 1.5rem -1.75rem"};
  padding: ${(props) => (props.$compact ? "1rem" : "1.75rem")};
  background: ${(props) =>
    props.$selected
      ? "linear-gradient(165deg, rgba(74, 144, 226, 0.04), transparent)"
      : "transparent"};
`;

const AnalysisTitle = styled.div<{ $selected?: boolean; $compact?: boolean }>`
  display: flex;
  align-items: center;
  gap: ${(props) => (props.$compact ? "0.75rem" : "1rem")};
  margin-bottom: ${(props) => (props.$compact ? "0.5rem" : "1rem")};

  .icon-wrapper {
    width: ${(props) => (props.$compact ? "32px" : "38px")};
    height: ${(props) => (props.$compact ? "32px" : "38px")};
    display: flex;
    align-items: center;
    justify-content: center;
    background: ${(props) =>
      props.$selected
        ? "linear-gradient(135deg, rgba(74, 144, 226, 0.1), rgba(74, 144, 226, 0.05))"
        : "#f8fafc"};
    border-radius: ${(props) => (props.$compact ? "8px" : "10px")};
    transition: all 0.3s ease;

    svg {
      width: ${(props) => (props.$compact ? "16px" : "18px")};
      height: ${(props) => (props.$compact ? "16px" : "18px")};
      color: ${(props) => (props.$selected ? "#4a90e2" : "#94a3b8")};
    }
  }

  .text {
    h4 {
      font-size: ${(props) => (props.$compact ? "1rem" : "1.125rem")};
      font-weight: 600;
      color: #1a202c;
      margin-bottom: ${(props) => (props.$compact ? "0" : "0.25rem")};
    }

    .id {
      font-size: 0.75rem;
      color: #94a3b8;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
        monospace;
      display: ${(props) => (props.$compact ? "none" : "block")};
    }
  }
`;

const MetadataBadges = styled.div<{ $compact?: boolean }>`
  display: flex;
  gap: ${(props) => (props.$compact ? "0.5rem" : "0.75rem")};
  flex-wrap: wrap;
  margin-top: ${(props) => (props.$compact ? "0.75rem" : "1.25rem")};
`;

const Badge = styled.div<{
  $variant?: "primary" | "secondary";
  $compact?: boolean;
}>`
  display: inline-flex;
  align-items: center;
  gap: ${(props) => (props.$compact ? "0.375rem" : "0.5rem")};
  padding: ${(props) =>
    props.$compact ? "0.375rem 0.625rem" : "0.625rem 0.875rem"};
  background: ${(props) =>
    props.$variant === "primary"
      ? "rgba(74, 144, 226, 0.04)"
      : "rgba(255, 255, 255, 0.8)"};
  border: 1px solid
    ${(props) =>
      props.$variant === "primary"
        ? "rgba(74, 144, 226, 0.15)"
        : "rgba(226, 232, 240, 0.8)"};
  border-radius: ${(props) => (props.$compact ? "6px" : "10px")};
  font-size: ${(props) => (props.$compact ? "0.75rem" : "0.8125rem")};
  color: ${(props) => (props.$variant === "primary" ? "#4a90e2" : "#64748b")};
  backdrop-filter: blur(8px);

  svg {
    width: ${(props) => (props.$compact ? "12px" : "14px")};
    height: ${(props) => (props.$compact ? "12px" : "14px")};
    opacity: 0.8;
  }
`;

const NoAnalysesMessage = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
  background: linear-gradient(135deg, #f8fafc, #f1f5f9);
  border-radius: 12px;
  border: 1px dashed #e2e8f0;

  h4 {
    margin: 0 0 0.5rem 0;
    font-size: 1rem;
    color: #1a202c;
    font-weight: 600;
  }

  p {
    margin: 0;
    font-size: 0.875rem;
    color: #64748b;
    max-width: 280px;
    line-height: 1.5;
  }

  svg {
    color: #94a3b8;
    margin-bottom: 1rem;
  }
`;

const DescriptionContainer = styled.div<{
  $expanded?: boolean;
  $compact?: boolean;
}>`
  margin-top: 1rem;
  position: relative;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  max-height: ${(props) => (props.$expanded ? "400px" : "120px")};
  overflow-y: ${(props) => (props.$expanded ? "auto" : "hidden")};
  padding: 1rem;
  background: #f8fafc;
  border-radius: 12px;
  border: 1px solid #e8edf5;
  display: ${(props) => (props.$compact ? "none" : "block")};

  &::-webkit-scrollbar {
    width: 4px;
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: rgba(74, 144, 226, 0.15);
    border-radius: 4px;
    &:hover {
      background: rgba(74, 144, 226, 0.25);
    }
  }
`;

const AnalyzerDescriptionHeader = styled.div<{ $compact?: boolean }>`
  font-size: 0.8rem;
  font-weight: 500;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 1rem 0 0.5rem 0;
  padding: 0 0.5rem;
  display: ${(props) => (props.$compact ? "none" : "flex")};
  align-items: center;
  gap: 0.5rem;

  svg {
    width: 14px;
    height: 14px;
    color: #94a3b8;
  }
`;

const MarkdownContent = styled(ReactMarkdown)`
  font-size: 0.9rem;
  color: #475569;
  line-height: 1.6;
  height: 100%;

  p {
    margin: 0.5rem 0;
  }

  code {
    background: #f1f5f9;
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    font-size: 0.85em;
    font-family: "SF Mono", monospace;
  }

  ul,
  ol {
    padding-left: 1.5rem;
    margin: 0.5rem 0;
  }
`;

const ExpandButton = styled.button<{ $visible?: boolean }>`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 32px;
  background: linear-gradient(to top, white 40%, transparent);
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #4a90e2;
  font-size: 0.8rem;
  font-weight: 500;
  opacity: ${(props) => (props.$visible ? 1 : 0)};
  transition: opacity 0.2s ease;

  &:hover {
    color: #2563eb;
  }

  svg {
    margin-left: 0.25rem;
  }
`;

const EmptyDescription = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #94a3b8;
  font-size: 0.9rem;
  font-style: italic;
  padding: 0.75rem;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px dashed #e2e8f0;

  svg {
    color: #cbd5e1;
  }
`;

const AnnotationsToggle = styled.button<{
  $isVisible: boolean;
  $compact?: boolean;
}>`
  display: flex;
  align-items: center;
  gap: ${(props) => (props.$compact ? "0.5rem" : "0.75rem")};
  padding: ${(props) =>
    props.$compact ? "0.5rem 0.875rem" : "0.75rem 1.25rem"};
  background: ${(props) =>
    props.$isVisible
      ? "linear-gradient(135deg, rgba(74, 144, 226, 0.08), rgba(74, 144, 226, 0.04))"
      : "#ffffff"};
  border: 1px solid
    ${(props) => (props.$isVisible ? "rgba(74, 144, 226, 0.2)" : "#e2e8f0")};
  border-radius: ${(props) => (props.$compact ? "8px" : "12px")};
  color: ${(props) => (props.$isVisible ? "#4a90e2" : "#64748b")};
  font-size: ${(props) => (props.$compact ? "0.8125rem" : "0.875rem")};
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: ${(props) =>
      props.$isVisible
        ? "linear-gradient(135deg, rgba(74, 144, 226, 0.1), transparent)"
        : "linear-gradient(135deg, rgba(226, 232, 240, 0.5), transparent)"};
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  &:hover {
    transform: translateY(-1px);
    box-shadow: ${(props) =>
      props.$isVisible
        ? "0 4px 12px rgba(74, 144, 226, 0.1)"
        : "0 4px 12px rgba(0, 0, 0, 0.05)"};

    &::before {
      opacity: 1;
    }
  }

  &:active {
    transform: translateY(0px);
  }

  .icon-container {
    display: flex;
    align-items: center;
    justify-content: center;
    width: ${(props) => (props.$compact ? "20px" : "24px")};
    height: ${(props) => (props.$compact ? "20px" : "24px")};
    background: ${(props) =>
      props.$isVisible
        ? "rgba(74, 144, 226, 0.1)"
        : "rgba(226, 232, 240, 0.5)"};
    border-radius: ${(props) => (props.$compact ? "4px" : "6px")};
    transition: all 0.3s ease;

    svg {
      width: ${(props) => (props.$compact ? "12px" : "14px")};
      height: ${(props) => (props.$compact ? "12px" : "14px")};
      transition: all 0.3s ease;
      color: ${(props) => (props.$isVisible ? "#4a90e2" : "#94a3b8")};
    }
  }

  .count-badge {
    display: inline-flex;
    align-items: center;
    margin-left: auto;
    padding: ${(props) =>
      props.$compact ? "0.125rem 0.375rem" : "0.25rem 0.5rem"};
    background: ${(props) =>
      props.$isVisible
        ? "rgba(74, 144, 226, 0.1)"
        : "rgba(226, 232, 240, 0.5)"};
    border-radius: ${(props) => (props.$compact ? "4px" : "6px")};
    font-size: ${(props) => (props.$compact ? "0.7rem" : "0.75rem")};
    font-weight: 600;
    color: ${(props) => (props.$isVisible ? "#4a90e2" : "#64748b")};
  }
`;

// Helper function to format timestamps
const formatTimestamp = (timestamp: string): string => {
  const date = new Date(timestamp);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
};

// Helper function to calculate duration
const calculateDuration = (start: string, end: string): string => {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const durationSeconds = (endDate.getTime() - startDate.getTime()) / 1000;
  return `${durationSeconds.toFixed(1)}s`;
};

/**
 * A vertical tray selector for analyses, which now also displays
 * annotations for each analysis in a style similar to SingleDocumentExtractResults.
 */
const AnalysisTraySelector: React.FC<AnalysisTraySelectorProps> = ({
  read_only,
  analyses,
  viewMode = "expanded",
  searchTerm: externalSearchTerm,
}) => {
  const { width } = useWindowDimensions();
  const { selectedCorpus } = useCorpusState();
  const { selectedAnalysis } = useAnalysisSelection();
  const { onSelectAnalysis } = useAnalysisManager();
  const { pdfAnnotations } = usePdfAnnotations();

  const [internalSearchTerm, setInternalSearchTerm] = useState<string>("");
  const searchTerm =
    externalSearchTerm !== undefined ? externalSearchTerm : internalSearchTerm;
  const isCompact = viewMode === "compact";

  /**
   * Maintain open/closed state of annotation visibility for each analysis.
   * Keyed by Analysis ID.
   */
  const [annotationVisibility, setAnnotationVisibility] = useState<{
    [analysisId: string]: boolean;
  }>({});

  const toggleAnnotationsVisibility = (analysisId: string) => {
    setAnnotationVisibility((prev) => ({
      ...prev,
      [analysisId]: !prev[analysisId],
    }));
  };

  // Fuse configuration for fuzzy searching the analyses.
  const fuseOptions = useMemo(
    () => ({
      keys: ["name", "description"],
      threshold: 0.4,
    }),
    []
  );

  const analysesFuse = useMemo(
    () => new Fuse(analyses, fuseOptions),
    [analyses, fuseOptions]
  );

  const filteredItems = useMemo((): AnalysisType[] => {
    if (!searchTerm) return analyses;
    return fuseOptions
      ? analysesFuse.search(searchTerm).map((result) => result.item)
      : analyses;
  }, [analyses, searchTerm, analysesFuse, fuseOptions]);

  const handleSearchChange = (value: string) => {
    if (externalSearchTerm === undefined) {
      setInternalSearchTerm(value);
    }
  };

  const mountedRef = useRef<boolean>(false);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Memoized calculation of unique labels for each analysis
  const analysisLabelsCount = useMemo(() => {
    return analyses.reduce((acc, item) => {
      const uniqueLabels =
        item.fullAnnotationList?.reduce(
          (labelAcc: string[], curr) =>
            curr.annotationLabel?.text
              ? [...new Set([...labelAcc, curr.annotationLabel.text])]
              : labelAcc,
          []
        ) || [];

      return {
        ...acc,
        [item.id]: uniqueLabels.length,
      };
    }, {} as Record<string, number>);
  }, [analyses]);

  return (
    <TrayContainer>
      {externalSearchTerm === undefined && (
        <SearchSegment attached="top">
          <Form>
            <Form.Input
              icon={{
                name: searchTerm ? "cancel" : "search",
                link: true,
                onClick: searchTerm ? () => handleSearchChange("") : undefined,
              }}
              placeholder="Search analyses..."
              onChange={(e) => handleSearchChange(e.target.value)}
              value={searchTerm}
            />
          </Form>
        </SearchSegment>
      )}

      <AnalysisListSegment
        attached={externalSearchTerm === undefined ? "bottom" : undefined}
      >
        {mountedRef.current && filteredItems.length === 0 ? (
          <NoAnalysesMessage>
            <ChartNetwork size={32} />
            <h4>No Analyses Available</h4>
            <p>
              If you have sufficient privileges, try creating a new analysis
              from the corpus page.
            </p>
          </NoAnalysesMessage>
        ) : (
          filteredItems.map((item) => {
            const isSelected = Boolean(
              selectedAnalysis && item.id === selectedAnalysis.id
            );
            const itemId = item.id;

            // Get the annotations from the store that match this analysis (assuming .analysisId is a valid field)
            const relevantAnnotations = pdfAnnotations.annotations.filter(
              (ann) => ann.id === item.id
            );

            const isVisible = annotationVisibility[itemId];

            return (
              <AnalysisCard
                key={itemId}
                $selected={isSelected}
                $compact={isCompact}
                onClick={(e) => {
                  // Cast e.target as HTMLElement to use closest()
                  if (
                    (e.target as HTMLElement).closest(".annotations-container")
                  ) {
                    e.stopPropagation();
                    return;
                  }
                  // Don't trigger if clicking the show/hide button
                  if ((e.target as HTMLElement).closest("button")) {
                    return;
                  }
                  onSelectAnalysis(isSelected ? null : item);
                }}
              >
                <AnalysisHeader $selected={isSelected} $compact={isCompact}>
                  <AnalysisTitle $selected={isSelected} $compact={isCompact}>
                    <div className="icon-wrapper">
                      <ChartNetwork />
                    </div>
                    <div className="text">
                      <h4>{item.analyzer.id || "Untitled Analysis"}</h4>
                      <div className="id">{itemId}</div>
                    </div>
                  </AnalysisTitle>
                  <MetadataBadges $compact={isCompact}>
                    <Badge $variant="primary" $compact={isCompact}>
                      <Tag />
                      {analysisLabelsCount[item.id]} Labels
                    </Badge>
                    <Badge $compact={isCompact}>
                      <Edit3 />
                      {item.annotations?.totalCount || 0} Annotations
                    </Badge>
                    {!isCompact && (
                      <Badge $compact={isCompact}>
                        <BarChart3 />
                        Analysis
                      </Badge>
                    )}
                  </MetadataBadges>
                </AnalysisHeader>
                <div className="timestamps">
                  <div className="timestamp-row">
                    <div className="label">
                      <PlayCircle />
                      Started
                    </div>
                    <div className="value">
                      {formatTimestamp(item.analysisStarted)}
                    </div>
                  </div>
                  <div className="timestamp-row">
                    <div className="label">
                      <CheckCircle />
                      Completed
                    </div>
                    <div className="value">
                      {formatTimestamp(item.analysisCompleted)}
                    </div>
                  </div>
                  {item.analysisStarted && item.analysisCompleted && (
                    <div className="timestamp-row">
                      <div className="label">
                        <Timer />
                        Duration
                      </div>
                      <div className="value">
                        {calculateDuration(
                          item.analysisStarted,
                          item.analysisCompleted
                        )}
                      </div>
                    </div>
                  )}
                </div>
                {item.analyzer.description && !isCompact && (
                  <DescriptionExpander
                    description={item.analyzer.description}
                    selected={isSelected}
                    isCompact={isCompact}
                  />
                )}
                <div className="annotations-section">
                  <AnnotationsToggle
                    $isVisible={isVisible}
                    $compact={isCompact}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleAnnotationsVisibility(itemId);
                    }}
                  >
                    <span className="icon-container">
                      {isVisible ? <EyeOff /> : <Eye />}
                    </span>
                    {isVisible ? "Hide Annotations" : "Show Annotations"}
                    <span className="count-badge">
                      {item.annotations?.totalCount || 0}
                    </span>
                  </AnnotationsToggle>

                  {isVisible && (
                    <div className="annotations-container">
                      {/* Pass through the read_only prop from AnalysisTraySelector to ensure read-only mode cascades correctly */}
                      <AnnotationList read_only={read_only} />
                    </div>
                  )}
                </div>
              </AnalysisCard>
            );
          })
        )}
      </AnalysisListSegment>
    </TrayContainer>
  );
};

interface DescriptionExpanderProps {
  description: string;
  selected?: boolean;
  isCompact?: boolean;
}

const DescriptionExpander: React.FC<DescriptionExpanderProps> = ({
  description,
  selected,
  isCompact = false,
}) => {
  const [expanded, setExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const [needsExpansion, setNeedsExpansion] = useState(false);

  useEffect(() => {
    if (contentRef.current) {
      setNeedsExpansion(contentRef.current.scrollHeight > 100);
    }
  }, [description]);

  if (isCompact) return null;

  return (
    <>
      <AnalyzerDescriptionHeader $compact={isCompact}>
        <FileText size={14} />
        Analyzer Description
      </AnalyzerDescriptionHeader>
      {description?.trim() ? (
        <DescriptionContainer
          $expanded={expanded}
          $compact={isCompact}
          ref={contentRef}
        >
          <MarkdownContent>{description}</MarkdownContent>
          {needsExpansion && (
            <ExpandButton
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(!expanded);
              }}
              $visible={needsExpansion}
            >
              {expanded ? (
                <>
                  Show Less <ChevronUp size={14} />
                </>
              ) : (
                <>
                  Show More <ChevronDown size={14} />
                </>
              )}
            </ExpandButton>
          )}
        </DescriptionContainer>
      ) : (
        <EmptyDescription>
          <FileText size={16} />
          No analyzer description provided
        </EmptyDescription>
      )}
    </>
  );
};

export default AnalysisTraySelector;
