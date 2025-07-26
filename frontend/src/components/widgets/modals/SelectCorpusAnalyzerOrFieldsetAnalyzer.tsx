import React, { useState, useEffect } from "react";
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
  Sparkles,
  Info,
  Loader2,
} from "lucide-react";
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
} from "../../../types/graphql-api";
import { UnifiedFieldsetSelector } from "../selectors/UnifiedFieldsetSelector";

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
  max-width: 640px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const ModalHeader = styled.div`
  padding: 2rem 2rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: linear-gradient(180deg, #fafbfc 0%, rgba(250, 251, 252, 0) 100%);
`;

const HeaderTitle = styled.h2`
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

const HeaderSubtitle = styled.p`
  margin: 0.5rem 0 0;
  color: #64748b;
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
  border: 1px solid #e2e8f0;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

  svg {
    width: 20px;
    height: 20px;
    color: #64748b;
  }

  &:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
    svg {
      color: #475569;
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
  border: 2px solid ${(props) => (props.$active ? "#3b82f6" : "#e2e8f0")};
  background: ${(props) => (props.$active ? "#eff6ff" : "white")};
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.9375rem;
  color: ${(props) => (props.$active ? "#3b82f6" : "#64748b")};
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
    background: ${(props) => (props.$active ? "#eff6ff" : "#f8fafc")};
    border-color: ${(props) => (props.$active ? "#3b82f6" : "#cbd5e1")};
  }
`;

const ModalContent = styled.div`
  padding: 2rem;
  flex: 1;
  overflow-y: auto;
`;

const FormField = styled.div`
  margin-bottom: 1.5rem;

  &:last-child {
    margin-bottom: 0;
  }
`;

const Label = styled.label`
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.5rem;
`;

const Input = styled.input`
  width: 100%;
  padding: 0.875rem 1rem;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 0.9375rem;
  transition: all 0.2s ease;
  background: white;

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &:disabled {
    background: #f8fafc;
    cursor: not-allowed;
  }
`;

const SelectContainer = styled.div`
  position: relative;
`;

const Select = styled.select`
  width: 100%;
  padding: 0.875rem 3rem 0.875rem 1rem;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  font-size: 0.9375rem;
  background: white;
  cursor: pointer;
  transition: all 0.2s ease;
  appearance: none;

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &:disabled {
    background: #f8fafc;
    cursor: not-allowed;
  }
`;

const SelectIcon = styled(ChevronRight)`
  position: absolute;
  right: 1rem;
  top: 50%;
  transform: translateY(-50%) rotate(90deg);
  width: 20px;
  height: 20px;
  color: #64748b;
  pointer-events: none;
`;

const InfoBox = styled(motion.div)`
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 12px;
  padding: 1.25rem;
  margin-top: 1.5rem;
  display: flex;
  gap: 1rem;

  svg {
    width: 20px;
    height: 20px;
    color: #0284c7;
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
  color: #0c4a6e;
`;

const InfoDescription = styled.p`
  margin: 0;
  font-size: 0.875rem;
  color: #075985;
  line-height: 1.5;
`;

const ModalFooter = styled.div`
  padding: 1.5rem 2rem;
  border-top: 1px solid #e2e8f0;
  background: #fafbfc;
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
    background: #3b82f6;
    color: white;
    border: 2px solid #3b82f6;

    &:hover:not(:disabled) {
      background: #2563eb;
      border-color: #2563eb;
    }

    &:disabled {
      background: #94a3b8;
      border-color: #94a3b8;
      cursor: not-allowed;
    }
  `
      : `
    background: white;
    color: #64748b;
    border: 2px solid #e2e8f0;

    &:hover:not(:disabled) {
      background: #f8fafc;
      border-color: #cbd5e1;
      color: #475569;
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
  color: #3b82f6;
`;

const LoadingText = styled.p`
  font-size: 0.9375rem;
  color: #64748b;
  font-weight: 500;
`;

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

  const { loading: loadingAnalyzers, data: analyzersData } = useQuery<
    GetAnalyzersOutputs,
    GetAnalyzersInputs
  >(GET_ANALYZERS, {
    skip: !open,
  });

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

                // Filter out any existing analysis with the same ID
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

                  // Filter out any existing extract with the same ID
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
      try {
        const result = await startDocumentAnalysis({
          variables: {
            ...(document ? { documentId: document.id } : {}),
            analyzerId: selectedItem,
            ...(corpus ? { corpusId: corpus.id } : {}),
          },
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

  const selectedAnalyzer = analyzersData?.analyzers.edges.find(
    (edge) => edge.node.id === selectedItem
  )?.node;

  const isLoading =
    loadingAnalyzers ||
    creatingExtract ||
    startingExtract ||
    startingDocumentAnalysis ||
    startingDocumentExtract;

  if (!open) return null;

  return (
    <ModalOverlay
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <ModalContainer
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
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
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.2 }}
              >
                <FormField>
                  <Label>Select Analyzer</Label>
                  <SelectContainer>
                    <Select
                      value={selectedItem || ""}
                      onChange={(e) => setSelectedItem(e.target.value)}
                      disabled={loadingAnalyzers}
                    >
                      <option value="">Choose an analyzer...</option>
                      {analyzersData?.analyzers.edges.map((edge) => (
                        <option key={edge.node.id} value={edge.node.id}>
                          {edge.node.description}
                        </option>
                      ))}
                    </Select>
                    <SelectIcon />
                  </SelectContainer>
                </FormField>

                {selectedAnalyzer && (
                  <InfoBox
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <Info />
                    <InfoContent>
                      <InfoTitle>{selectedAnalyzer.description}</InfoTitle>
                      <InfoDescription>
                        {selectedAnalyzer.manifest?.metadata?.description ||
                          "This analyzer will process your document and extract insights."}
                      </InfoDescription>
                    </InfoContent>
                  </InfoBox>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="fieldset"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.2 }}
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
                  <InfoBox
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
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
                <Sparkles size={18} />
                Run Analysis
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
    </ModalOverlay>
  );
};
