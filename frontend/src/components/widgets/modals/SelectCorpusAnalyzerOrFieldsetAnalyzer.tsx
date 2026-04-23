import React, { useState, useEffect, useMemo, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  gql,
  Reference,
  StoreObject,
  useMutation,
  useQuery,
} from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  BarChart3,
  Database,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Info,
  Loader2,
  Search,
  Settings,
  Play,
  Code,
  Tag,
  Hash,
  Cpu,
  FileJson,
} from "lucide-react";
import { debounce } from "lodash";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import Form from "@rjsf/core";
import { RJSFSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import {
  GET_ANALYZERS,
  GetAnalyzersInputs,
  GetAnalyzersOutputs,
} from "../../../graphql/queries";
import {
  REQUEST_CREATE_EXTRACT,
  REQUEST_START_EXTRACT,
  START_ANALYSIS,
  START_DOCUMENT_EXTRACT,
  RequestCreateExtractInputType,
  RequestCreateExtractOutputType,
  RequestStartExtractInputType,
  RequestStartExtractOutputType,
  StartAnalysisInput,
  StartAnalysisOutput,
  StartDocumentExtractInput,
  StartDocumentExtractOutput,
} from "../../../graphql/mutations";
import {
  CorpusType,
  DocumentType,
  FieldsetType,
  AnalyzerType,
} from "../../../types/graphql-api";
import { UnifiedFieldsetSelector } from "../selectors/UnifiedFieldsetSelector";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

// Styled Components
const ModalOverlay = styled(motion.div)`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999999;
  padding: 1rem;
`;

const ModalContainer = styled(motion.div)`
  background: white;
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  max-width: 900px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const ModalHeader = styled.div`
  padding: 2rem 2rem 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: linear-gradient(180deg, #fafbfc 0%, rgba(250, 251, 252, 0) 100%);
`;

const HeaderTitle = styled.h2`
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

const HeaderSubtitle = styled.p`
  margin: 0.5rem 0 0;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.9375rem;
  line-height: 1.5;
`;

const CloseButton = styled(motion.button)`
  position: absolute;
  top: 1.5rem;
  right: 1.5rem;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    width: 20px;
    height: 20px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.borderHover};
    svg {
      color: ${OS_LEGAL_COLORS.textTertiary};
    }
  }
`;

const TabContainer = styled.div`
  display: flex;
  gap: 0.5rem;
  padding: 1.5rem 2rem 0;
`;

const TabButton = styled(motion.button)<{ $active: boolean }>`
  flex: 1;
  padding: 1rem 1.5rem;
  border: 2px solid
    ${(props) =>
      props.$active ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.blueSurface : "white"};
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.9375rem;
  color: ${(props) =>
    props.$active
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;

  svg {
    width: 20px;
    height: 20px;
  }

  &:hover:not(:disabled) {
    background: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.blueSurface
        : OS_LEGAL_COLORS.surfaceHover};
    border-color: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.borderHover};
  }
`;

const ModalContent = styled.div`
  flex: 1;
  overflow-y: auto;
  min-height: 400px;
`;

// Search Section
const SearchSection = styled.div`
  padding: 1.5rem 2rem;
  background: linear-gradient(to bottom, #ffffff 90%, rgba(255, 255, 255, 0.9));
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  position: sticky;
  top: 0;
  z-index: 10;
`;

const SearchWrapper = styled.div`
  position: relative;
  max-width: 600px;
  margin: 0 auto;
`;

const SearchInput = styled.input`
  width: 100%;
  padding: 0.75rem 1rem 0.75rem 3rem;
  border: 2px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  font-size: 0.9375rem;
  transition: all 0.2s ease;
  background: white;

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const SearchIcon = styled(Search)`
  position: absolute;
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ResultCount = styled.span`
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  padding: 0.25rem 0.75rem;
  border-radius: 8px;
`;

// Analyzer Grid
const AnalyzerGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
  padding: 1.5rem 2rem;
`;

const AnalyzerCard = styled(motion.div)<{ $selected?: boolean }>`
  background: ${(props) =>
    props.$selected
      ? "linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%)"
      : "white"};
  border: 2px solid
    ${(props) =>
      props.$selected ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;

  ${(props) =>
    props.$selected &&
    `
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  `}

  &:hover {
    border-color: ${(props) =>
      props.$selected
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.borderHover};
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: ${(props) =>
      props.$selected
        ? `linear-gradient(90deg, ${OS_LEGAL_COLORS.primaryBlue} 0%, ${OS_LEGAL_COLORS.primaryBlueHover} 100%)`
        : `linear-gradient(90deg, ${OS_LEGAL_COLORS.border} 0%, ${OS_LEGAL_COLORS.borderHover} 100%)`};
  }
`;

const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 0.75rem;
`;

const CardTitle = styled.h3`
  font-size: 0.95rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  line-height: 1.3;
  flex: 1;
  padding-right: 0.5rem;
`;

const TaskName = styled.div`
  font-family: "SF Mono", "Monaco", "Inconsolata", monospace;
  font-size: 0.7rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceHover};
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  margin-top: 0.25rem;
  word-break: break-all;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
`;

const BadgeContainer = styled.div`
  display: flex;
  gap: 0.25rem;
  align-items: center;
  flex-shrink: 0;
`;

const StatusBadge = styled.div<{ $type: "configurable" | "ready" | "public" }>`
  display: flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0.2rem 0.4rem;
  border-radius: 6px;
  font-size: 0.65rem;
  font-weight: 600;
  white-space: nowrap;

  ${(props) => {
    switch (props.$type) {
      case "configurable":
        return `
          background: #fef3c7;
          color: #92400e;
        `;
      case "ready":
        return `
          background: #d1fae5;
          color: #065f46;
        `;
      case "public":
        return `
          background: ${OS_LEGAL_COLORS.blueBorder};
          color: ${OS_LEGAL_COLORS.blueDark};
        `;
    }
  }}

  svg {
    width: 10px;
    height: 10px;
  }
`;

const CardDescription = styled.div`
  font-size: 0.8rem;
  color: ${OS_LEGAL_COLORS.textTertiary};
  line-height: 1.4;
  max-height: 60px;
  overflow: hidden;
  position: relative;

  &::after {
    content: "";
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 20px;
    background: linear-gradient(to bottom, transparent, white);
  }
`;

const SchemaToggle = styled.button`
  background: none;
  border: none;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  margin-top: 0.5rem;

  &:hover {
    color: ${OS_LEGAL_COLORS.primaryBlueHover};
  }

  svg {
    width: 12px;
    height: 12px;
  }
`;

const SchemaPreview = styled(motion.pre)`
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 6px;
  padding: 0.5rem;
  font-size: 0.65rem;
  margin-top: 0.5rem;
  max-height: 100px;
  overflow-y: auto;
  font-family: "SF Mono", "Monaco", monospace;

  &::-webkit-scrollbar {
    width: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 2px;
  }
`;

// Pagination
const PaginationContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 1rem 2rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  gap: 0.5rem;
`;

const PageButton = styled.button<{ $active?: boolean }>`
  padding: 0.5rem 0.75rem;
  border: 1px solid
    ${(props) =>
      props.$active ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.primaryBlue : "white"};
  color: ${(props) =>
    props.$active ? "white" : OS_LEGAL_COLORS.textSecondary};
  border-radius: 8px;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    background: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.primaryBlueHover
        : OS_LEGAL_COLORS.surfaceHover};
    border-color: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.primaryBlueHover
        : OS_LEGAL_COLORS.borderHover};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

// Empty State
const EmptyState = styled.div`
  text-align: center;
  padding: 4rem 2rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const EmptyStateIcon = styled.div`
  width: 80px;
  height: 80px;
  margin: 0 auto 1.5rem;
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.surfaceLight} 0%,
    ${OS_LEGAL_COLORS.border} 100%
  );
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;

  svg {
    width: 40px;
    height: 40px;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const RjsfFormContainer = styled.div`
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 12px;
  padding: 1.5rem;
  border: 2px solid ${OS_LEGAL_COLORS.border};

  /* Style RJSF core form fields */
  .rjsf .form-group.field {
    margin-bottom: var(--oc-spacing-sm, 0.5rem);
  }

  .rjsf .form-control {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 4px;
    font-size: 0.875rem;
  }

  .rjsf .control-label {
    display: block;
    font-size: 0.875rem;
    font-weight: 600;
    margin-bottom: 0.25rem;
  }
`;

// Other existing styled components
const FormField = styled.div`
  margin-bottom: 1.5rem;
  padding: 0 2rem;

  &:last-child {
    margin-bottom: 0;
  }
`;

const Label = styled.label`
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin-bottom: 0.5rem;
`;

const Input = styled.input`
  width: 100%;
  padding: 0.875rem 1rem;
  border: 2px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  font-size: 0.9375rem;
  transition: all 0.2s ease;
  background: white;

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &:disabled {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    cursor: not-allowed;
  }
`;

const InfoBox = styled(motion.div)`
  background: ${OS_LEGAL_COLORS.infoSurface};
  border: 1px solid ${OS_LEGAL_COLORS.infoBorder};
  border-radius: 12px;
  padding: 1.25rem;
  margin: 1.5rem 2rem;
  display: flex;
  gap: 1rem;

  svg {
    width: 20px;
    height: 20px;
    color: ${OS_LEGAL_COLORS.infoText};
    flex-shrink: 0;
    margin-top: 0.125rem;
  }
`;

const InfoContent = styled.div`
  flex: 1;
`;

const InfoTitle = styled.h4`
  margin: 0 0 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.infoText};
`;

const InfoDescription = styled.div`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.infoText};
  line-height: 1.5;

  h1,
  h2,
  h3,
  h4,
  h5,
  h6 {
    font-size: 1em;
    margin: 0.5em 0;
  }

  p {
    margin: 0.5em 0;
  }

  ul,
  ol {
    margin: 0.5em 0;
    padding-left: 1.5em;
  }

  code {
    background: rgba(0, 0, 0, 0.05);
    padding: 0.125em 0.25em;
    border-radius: 3px;
    font-size: 0.9em;
  }
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surfaceHover};
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
`;

const Button = styled(motion.button)<{ $variant?: "primary" | "secondary" }>`
  padding: 0.75rem 1.5rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;

  ${(props) =>
    props.$variant === "primary"
      ? `
    background: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;
    border: 2px solid ${OS_LEGAL_COLORS.primaryBlue};

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.primaryBlueHover};
      border-color: ${OS_LEGAL_COLORS.primaryBlueHover};
    }

    &:disabled {
      background: ${OS_LEGAL_COLORS.textMuted};
      border-color: ${OS_LEGAL_COLORS.textMuted};
      cursor: not-allowed;
    }
  `
      : `
    background: white;
    color: ${OS_LEGAL_COLORS.textSecondary};
    border: 2px solid ${OS_LEGAL_COLORS.border};

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.surfaceHover};
      border-color: ${OS_LEGAL_COLORS.borderHover};
      color: ${OS_LEGAL_COLORS.textTertiary};
    }
  `}
`;

const LoadingOverlay = styled(motion.div)`
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
`;

const LoadingContent = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
`;

const SpinningLoader = styled(motion.div)`
  color: ${OS_LEGAL_COLORS.primaryBlue};
`;

const LoadingText = styled.p`
  font-size: 0.9375rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-weight: 500;
`;

// Helper functions
const extractTitleFromMarkdown = (markdown: string): string | null => {
  if (!markdown) return null;
  const lines = markdown.split("\n");
  for (const line of lines) {
    const match = line.match(/^#\s+(.+)$/);
    if (match) {
      return match[1].trim();
    }
  }
  return null;
};

const removeTitleFromMarkdown = (markdown: string): string => {
  if (!markdown) return "";
  const lines = markdown.split("\n");
  const filteredLines = lines.filter((line) => !line.match(/^#\s+.+$/));
  return filteredLines.join("\n").trim();
};

// Component
interface SelectAnalyzerOrFieldsetModalProps {
  corpus?: CorpusType;
  document?: DocumentType;
  open: boolean;
  onClose: () => void;
}

export const SelectAnalyzerOrFieldsetModal: React.FC<
  SelectAnalyzerOrFieldsetModalProps
> = ({ corpus, document, open, onClose }) => {
  const [activeTab, setActiveTab] = useState<"analyzer" | "fieldset">(
    "analyzer"
  );
  const [selectedItem, setSelectedItem] = useState<string | null>(null);
  const [selectedFieldset, setSelectedFieldset] = useState<FieldsetType | null>(
    null
  );
  const [extractName, setExtractName] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedSchemas, setExpandedSchemas] = useState<Set<string>>(
    new Set()
  );
  const [analyzerInputData, setAnalyzerInputData] = useState<
    Record<string, any>
  >({});
  const [showInputForm, setShowInputForm] = useState(false);
  const itemsPerPage = 9;

  // Debounce search - memoized to prevent recreation
  const debouncedSearch = useMemo(
    () =>
      debounce((value: string) => {
        setDebouncedSearchTerm(value);
        setCurrentPage(1);
      }, 300),
    []
  );

  useEffect(() => {
    debouncedSearch(searchTerm);
  }, [searchTerm, debouncedSearch]);

  // Reset state when modal closes or tab changes
  useEffect(() => {
    if (!open) {
      setSearchTerm("");
      setDebouncedSearchTerm("");
      setSelectedItem(null);
      setSelectedFieldset(null);
      setExtractName("");
      setCurrentPage(1);
      setExpandedSchemas(new Set());
      setAnalyzerInputData({});
      setShowInputForm(false);
    }
  }, [open]);

  useEffect(() => {
    setSearchTerm("");
    setDebouncedSearchTerm("");
    setCurrentPage(1);
    setExpandedSchemas(new Set());
    setAnalyzerInputData({});
    setShowInputForm(false);
  }, [activeTab]);

  const { loading: loadingAnalyzers, data: analyzersData } = useQuery<
    GetAnalyzersOutputs,
    GetAnalyzersInputs
  >(GET_ANALYZERS, {
    skip: !open || activeTab !== "analyzer",
    fetchPolicy: "cache-and-network",
  });

  // Filter and paginate analyzers
  const { filteredAnalyzers, paginatedAnalyzers, totalPages } = useMemo(() => {
    if (!analyzersData?.analyzers.edges) {
      return { filteredAnalyzers: [], paginatedAnalyzers: [], totalPages: 0 };
    }

    const allAnalyzers = analyzersData.analyzers.edges
      .map((edge) => edge.node)
      .filter(Boolean) as AnalyzerType[];

    // Apply search filter
    let filtered = allAnalyzers;
    if (debouncedSearchTerm && activeTab === "analyzer") {
      const searchLower = debouncedSearchTerm.toLowerCase();
      filtered = allAnalyzers.filter((analyzer) => {
        const title =
          extractTitleFromMarkdown(analyzer.description || "") ||
          analyzer.manifest?.metadata?.title ||
          "";
        const taskName = analyzer.taskName || analyzer.analyzerId || "";
        const description = analyzer.description || "";

        return (
          title.toLowerCase().includes(searchLower) ||
          taskName.toLowerCase().includes(searchLower) ||
          description.toLowerCase().includes(searchLower)
        );
      });
    }

    // Paginate
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    const paginated = filtered.slice(startIndex, endIndex);

    return {
      filteredAnalyzers: filtered,
      paginatedAnalyzers: paginated,
      totalPages: Math.ceil(filtered.length / itemsPerPage),
    };
  }, [analyzersData, debouncedSearchTerm, currentPage, activeTab]);

  const toggleSchemaExpansion = (analyzerId: string) => {
    setExpandedSchemas((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(analyzerId)) {
        newSet.delete(analyzerId);
      } else {
        newSet.add(analyzerId);
      }
      return newSet;
    });
  };

  const [createExtract, { loading: creatingExtract }] = useMutation<
    RequestCreateExtractOutputType,
    RequestCreateExtractInputType
  >(REQUEST_CREATE_EXTRACT, {
    update(cache, { data }) {
      if (data?.createExtract.ok && data.createExtract.obj) {
        const newExtract = data.createExtract.obj;
        cache.modify({
          fields: {
            extracts(existingExtracts = { edges: [] }) {
              const newExtractRef = cache.writeFragment({
                data: newExtract,
                fragment: gql`
                  fragment NewExtract on ExtractType {
                    id
                    name
                    started
                    corpus {
                      id
                      title
                    }
                  }
                `,
              });
              return {
                ...existingExtracts,
                edges: [
                  ...existingExtracts.edges,
                  { __typename: "ExtractTypeEdge", node: newExtractRef },
                ],
              };
            },
          },
        });
      }
    },
  });

  const [startExtract, { loading: startingExtract }] = useMutation<
    RequestStartExtractOutputType,
    RequestStartExtractInputType
  >(REQUEST_START_EXTRACT);

  const [startDocumentAnalysis, { loading: startingDocumentAnalysis }] =
    useMutation<StartAnalysisOutput, StartAnalysisInput>(START_ANALYSIS, {
      update(cache, { data }) {
        if (data?.startAnalysisOnDoc.ok && data.startAnalysisOnDoc.obj) {
          const newAnalysis = data.startAnalysisOnDoc.obj;
          cache.modify({
            fields: {
              analyses(existingAnalyses = { edges: [] }, { readField }) {
                const newAnalysisRef = cache.writeFragment({
                  data: newAnalysis,
                  fragment: gql`
                    fragment NewAnalysis on AnalysisType {
                      id
                      analysisStarted
                      analysisCompleted
                      analyzedDocuments {
                        edges {
                          node {
                            id
                          }
                        }
                      }
                      receivedCallbackFile
                      annotations {
                        totalCount
                      }
                      analyzer {
                        id
                        analyzerId
                        description
                        manifest
                        labelsetSet {
                          totalCount
                        }
                        hostGremlin {
                          id
                        }
                      }
                    }
                  `,
                });

                const filteredEdges = existingAnalyses.edges.filter(
                  (edge: { node: Reference | StoreObject | undefined }) =>
                    readField("id", edge.node) !== newAnalysis.id
                );

                return {
                  ...existingAnalyses,
                  edges: [
                    ...filteredEdges,
                    { __typename: "AnalysisTypeEdge", node: newAnalysisRef },
                  ],
                };
              },
            },
          });
        }
      },
    });

  const [startDocumentExtract, { loading: startingDocumentExtract }] =
    useMutation<StartDocumentExtractOutput, StartDocumentExtractInput>(
      START_DOCUMENT_EXTRACT,
      {
        update(cache, { data }) {
          if (data?.startExtractForDoc.ok && data.startExtractForDoc.obj) {
            const newExtract = data.startExtractForDoc.obj;
            cache.modify({
              fields: {
                extracts(existingExtracts = { edges: [] }, { readField }) {
                  const newExtractRef = cache.writeFragment({
                    data: newExtract,
                    fragment: gql`
                      fragment NewExtract on ExtractType {
                        id
                        name
                        started
                        corpus {
                          id
                          title
                        }
                      }
                    `,
                  });

                  const filteredEdges = existingExtracts.edges.filter(
                    (edge: { node: Reference | StoreObject | undefined }) =>
                      readField("id", edge.node) !== newExtract.id
                  );

                  return {
                    ...existingExtracts,
                    edges: [
                      ...filteredEdges,
                      { __typename: "ExtractTypeEdge", node: newExtractRef },
                    ],
                  };
                },
              },
            });
          }
        },
      }
    );

  const handleRun = async () => {
    if (activeTab === "analyzer" && selectedItem) {
      const analyzer = filteredAnalyzers.find((a) => a.id === selectedItem);

      // If analyzer has inputs and we're not showing the form yet, show it
      if (
        analyzer?.inputSchema &&
        Object.keys(analyzer.inputSchema).length > 0 &&
        !showInputForm
      ) {
        setShowInputForm(true);
        return;
      }

      try {
        const variables: any = {
          ...(document ? { documentId: document.id } : {}),
          analyzerId: selectedItem,
          ...(corpus ? { corpusId: corpus.id } : {}),
        };

        // Add input data if analyzer has schema
        if (
          analyzer?.inputSchema &&
          Object.keys(analyzer.inputSchema).length > 0
        ) {
          variables.analysisInputData = analyzerInputData;
        }

        const result = await startDocumentAnalysis({
          variables,
        });
        if (result.data?.startAnalysisOnDoc.ok) {
          toast.success("Document analysis started successfully");
          onClose();
        } else {
          toast.error("Failed to start document analysis");
        }
      } catch (error) {
        toast.error("Error starting document analysis");
      }
    } else if (activeTab === "fieldset" && selectedFieldset) {
      if (document) {
        try {
          const result = await startDocumentExtract({
            variables: {
              documentId: document.id,
              fieldsetId: selectedFieldset.id,
              corpusId: corpus?.id,
            },
          });
          if (result.data?.startExtractForDoc.ok) {
            toast.success("Document extract started successfully");
            onClose();
          } else {
            toast.error("Failed to start document extract");
          }
        } catch (error) {
          toast.error("Error starting document extract");
        }
      } else if (corpus) {
        try {
          const createResult = await createExtract({
            variables: {
              corpusId: corpus.id,
              name: extractName,
              fieldsetId: selectedFieldset.id,
            },
          });
          if (createResult.data?.createExtract.ok) {
            const startResult = await startExtract({
              variables: { extractId: createResult.data.createExtract.obj.id },
            });
            if (startResult.data?.startExtract.ok) {
              toast.success("Corpus extract created and started successfully");
              onClose();
            } else {
              toast.error("Failed to start corpus extract");
            }
          } else {
            toast.error("Failed to create corpus extract");
          }
        } catch (error) {
          toast.error("Error creating or starting corpus extract");
        }
      }
    }
  };

  const handleFieldsetChange = (fieldset: FieldsetType | null) => {
    setSelectedFieldset(fieldset);
    setSelectedItem(fieldset?.id || null);
  };

  const selectedAnalyzer = filteredAnalyzers.find(
    (analyzer) => analyzer.id === selectedItem
  );

  const isLoading =
    loadingAnalyzers ||
    creatingExtract ||
    startingExtract ||
    startingDocumentAnalysis ||
    startingDocumentExtract;

  if (!open) return null;

  return createPortal(
    <ModalOverlay
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      onClick={onClose}
      data-testid="select-analyzer-or-fieldset-overlay"
    >
      <ModalContainer
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        onClick={(e) => e.stopPropagation()}
      >
        <ModalHeader>
          <HeaderTitle>
            <Sparkles size={24} />
            Start Analysis
          </HeaderTitle>
          <HeaderSubtitle>
            {document
              ? `Analyze "${document.title}"`
              : `Analyze all documents in "${corpus?.title}"`}
          </HeaderSubtitle>
          <CloseButton
            onClick={onClose}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            aria-label="Close"
          >
            <X />
          </CloseButton>
        </ModalHeader>

        <TabContainer>
          <TabButton
            $active={activeTab === "analyzer"}
            onClick={() => {
              setActiveTab("analyzer");
              setSelectedItem(null);
              setSelectedFieldset(null);
              setShowInputForm(false);
            }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <BarChart3 />
            Analyzer
          </TabButton>
          <TabButton
            $active={activeTab === "fieldset"}
            onClick={() => {
              setActiveTab("fieldset");
              setSelectedItem(null);
              setSelectedFieldset(null);
              setShowInputForm(false);
            }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Database />
            Fieldset
          </TabButton>
        </TabContainer>

        <ModalContent>
          <AnimatePresence>
            {activeTab === "analyzer" ? (
              <motion.div
                key="analyzer"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <SearchSection>
                  <SearchWrapper>
                    <SearchIcon />
                    <SearchInput
                      type="text"
                      placeholder="Search analyzers by name or description..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                    {filteredAnalyzers.length > 0 && (
                      <ResultCount>
                        {filteredAnalyzers.length} analyzer
                        {filteredAnalyzers.length !== 1 ? "s" : ""}
                      </ResultCount>
                    )}
                  </SearchWrapper>
                </SearchSection>

                {loadingAnalyzers ? (
                  <EmptyState>
                    <LoadingContent>
                      <SpinningLoader
                        animate={{ rotate: 360 }}
                        transition={{
                          duration: 1,
                          repeat: Infinity,
                          ease: "linear",
                        }}
                      >
                        <Loader2 size={32} />
                      </SpinningLoader>
                      <LoadingText>Loading analyzers...</LoadingText>
                    </LoadingContent>
                  </EmptyState>
                ) : paginatedAnalyzers.length > 0 ? (
                  <>
                    <AnalyzerGrid>
                      {paginatedAnalyzers.map((analyzer, index) => {
                        const hasInputs = !!(
                          analyzer.inputSchema &&
                          Object.keys(analyzer.inputSchema).length > 0
                        );
                        const title =
                          extractTitleFromMarkdown(
                            analyzer.description || ""
                          ) ||
                          analyzer.manifest?.metadata?.title ||
                          analyzer.taskName?.split(".").pop() ||
                          "Untitled Analyzer";
                        const cleanDescription = removeTitleFromMarkdown(
                          analyzer.description || ""
                        );
                        const isExpanded = expandedSchemas.has(analyzer.id);
                        const isSelected = selectedItem === analyzer.id;

                        return (
                          <AnalyzerCard
                            key={analyzer.id}
                            $selected={isSelected}
                            onClick={() => {
                              setSelectedItem(analyzer.id);
                              setAnalyzerInputData({});
                              setShowInputForm(false);
                            }}
                          >
                            <CardHeader>
                              <CardTitle>{title}</CardTitle>
                              <BadgeContainer>
                                {analyzer.isPublic && (
                                  <StatusBadge $type="public">
                                    <Tag />
                                  </StatusBadge>
                                )}
                                {hasInputs ? (
                                  <StatusBadge $type="configurable">
                                    <Settings />
                                  </StatusBadge>
                                ) : (
                                  <StatusBadge $type="ready">
                                    <Play />
                                  </StatusBadge>
                                )}
                              </BadgeContainer>
                            </CardHeader>

                            {analyzer.taskName && (
                              <TaskName>
                                <Hash size={8} />
                                {analyzer.taskName
                                  .split(".")
                                  .slice(-2)
                                  .join(".")}
                              </TaskName>
                            )}

                            {cleanDescription && (
                              <CardDescription>
                                {cleanDescription.substring(0, 100)}
                                {cleanDescription.length > 100 && "..."}
                              </CardDescription>
                            )}

                            {hasInputs && (
                              <>
                                <SchemaToggle
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleSchemaExpansion(analyzer.id);
                                  }}
                                >
                                  <Code />
                                  {isExpanded ? "Hide" : "Show"} Schema
                                  {isExpanded ? <ChevronUp /> : <ChevronDown />}
                                </SchemaToggle>
                                <AnimatePresence>
                                  {isExpanded && (
                                    <SchemaPreview
                                      initial={{ height: 0, opacity: 0 }}
                                      animate={{ height: "auto", opacity: 1 }}
                                      exit={{ height: 0, opacity: 0 }}
                                    >
                                      {JSON.stringify(
                                        analyzer.inputSchema,
                                        null,
                                        2
                                      )}
                                    </SchemaPreview>
                                  )}
                                </AnimatePresence>
                              </>
                            )}
                          </AnalyzerCard>
                        );
                      })}
                    </AnalyzerGrid>

                    {totalPages > 1 && (
                      <PaginationContainer>
                        <PageButton
                          onClick={() =>
                            setCurrentPage((p) => Math.max(1, p - 1))
                          }
                          disabled={currentPage === 1}
                        >
                          ←
                        </PageButton>
                        {Array.from({ length: totalPages }, (_, i) => i + 1)
                          .filter(
                            (page) =>
                              page === 1 ||
                              page === totalPages ||
                              Math.abs(page - currentPage) <= 1
                          )
                          .map((page, index, array) => (
                            <React.Fragment key={page}>
                              {index > 0 && array[index - 1] !== page - 1 && (
                                <span
                                  style={{
                                    padding: "0 0.5rem",
                                    color: OS_LEGAL_COLORS.textMuted,
                                  }}
                                >
                                  ...
                                </span>
                              )}
                              <PageButton
                                $active={currentPage === page}
                                onClick={() => setCurrentPage(page)}
                              >
                                {page}
                              </PageButton>
                            </React.Fragment>
                          ))}
                        <PageButton
                          onClick={() =>
                            setCurrentPage((p) => Math.min(totalPages, p + 1))
                          }
                          disabled={currentPage === totalPages}
                        >
                          →
                        </PageButton>
                      </PaginationContainer>
                    )}
                  </>
                ) : (
                  <EmptyState>
                    <EmptyStateIcon>
                      <Cpu />
                    </EmptyStateIcon>
                    <h3>
                      {searchTerm
                        ? "No analyzers match your search"
                        : "No analyzers available"}
                    </h3>
                    <p>Try adjusting your search or check back later.</p>
                  </EmptyState>
                )}

                {selectedAnalyzer && (
                  <>
                    {showInputForm &&
                    selectedAnalyzer.inputSchema &&
                    Object.keys(selectedAnalyzer.inputSchema).length > 0 ? (
                      <FormField>
                        <Label
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                            marginBottom: "1rem",
                          }}
                        >
                          <FileJson size={18} />
                          Configure Analyzer Parameters
                        </Label>
                        <InfoBox style={{ marginBottom: "1rem" }}>
                          <Settings />
                          <InfoContent>
                            <InfoTitle>
                              {extractTitleFromMarkdown(
                                selectedAnalyzer.description || ""
                              ) ||
                                selectedAnalyzer.manifest?.metadata?.title ||
                                "Selected Analyzer"}
                            </InfoTitle>
                            <div
                              style={{
                                fontSize: "0.875rem",
                                color: OS_LEGAL_COLORS.textSecondary,
                                marginTop: "0.25rem",
                              }}
                            >
                              Please configure the required parameters below
                            </div>
                          </InfoContent>
                        </InfoBox>
                        <RjsfFormContainer>
                          <Form
                            id="analyzer-input-form"
                            schema={selectedAnalyzer.inputSchema as RJSFSchema}
                            validator={validator}
                            formData={analyzerInputData}
                            onChange={(e: any) =>
                              setAnalyzerInputData(e.formData)
                            }
                          >
                            <></>
                          </Form>
                        </RjsfFormContainer>
                      </FormField>
                    ) : (
                      <InfoBox>
                        <Info />
                        <InfoContent>
                          <InfoTitle>
                            {extractTitleFromMarkdown(
                              selectedAnalyzer.description || ""
                            ) ||
                              selectedAnalyzer.manifest?.metadata?.title ||
                              "Selected Analyzer"}
                          </InfoTitle>
                          <InfoDescription>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {removeTitleFromMarkdown(
                                selectedAnalyzer.description || ""
                              ) ||
                                selectedAnalyzer.manifest?.metadata
                                  ?.description ||
                                "This analyzer will process your document and extract insights."}
                            </ReactMarkdown>
                          </InfoDescription>
                        </InfoContent>
                      </InfoBox>
                    )}
                  </>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="fieldset"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                {!document && (
                  <FormField>
                    <Label>Extract Name</Label>
                    <Input
                      type="text"
                      placeholder="Enter a name for this extract..."
                      value={extractName}
                      onChange={(e) => setExtractName(e.target.value)}
                      disabled={isLoading}
                    />
                  </FormField>
                )}

                <FormField>
                  <Label>Select Fieldset</Label>
                  <UnifiedFieldsetSelector
                    value={selectedFieldset}
                    onChange={handleFieldsetChange}
                    placeholder="Search or create a fieldset..."
                    disabled={isLoading}
                    showInfo={false}
                  />
                </FormField>

                {selectedFieldset && (
                  <InfoBox>
                    <Database />
                    <InfoContent>
                      <InfoTitle>{selectedFieldset.name}</InfoTitle>
                      <InfoDescription>
                        {selectedFieldset.description ||
                          "This fieldset will extract structured data from your document."}
                      </InfoDescription>
                    </InfoContent>
                  </InfoBox>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </ModalContent>

        <ModalFooter>
          <Button
            onClick={onClose}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            Cancel
          </Button>
          <Button
            $variant="primary"
            onClick={handleRun}
            disabled={
              !selectedItem ||
              (activeTab === "fieldset" && !document && !extractName) ||
              isLoading
            }
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            {isLoading ? (
              <>
                <SpinningLoader
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  <Loader2 size={18} />
                </SpinningLoader>
                Processing...
              </>
            ) : (
              <>
                {(() => {
                  if (activeTab === "analyzer" && selectedItem) {
                    const analyzer = filteredAnalyzers.find(
                      (a) => a.id === selectedItem
                    );
                    const hasInputs =
                      analyzer?.inputSchema &&
                      Object.keys(analyzer.inputSchema).length > 0;

                    if (hasInputs && !showInputForm) {
                      return (
                        <>
                          <Settings size={18} />
                          Configure
                        </>
                      );
                    }
                  }

                  return (
                    <>
                      <Sparkles size={18} />
                      Run Analysis
                    </>
                  );
                })()}
              </>
            )}
          </Button>
        </ModalFooter>

        <AnimatePresence>
          {isLoading && (
            <LoadingOverlay
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <LoadingContent>
                <SpinningLoader
                  animate={{ rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                >
                  <Loader2 size={32} />
                </SpinningLoader>
                <LoadingText>Starting analysis...</LoadingText>
              </LoadingContent>
            </LoadingOverlay>
          )}
        </AnimatePresence>
      </ModalContainer>
    </ModalOverlay>,
    window.document.body
  );
};
