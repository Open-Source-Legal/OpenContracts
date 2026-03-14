/**
 * SelectExportTypeModal
 *
 * This modal allows the user to:
 * 1) Choose an export type from a dropdown, e.g. OpenContracts, FUNSD, etc.
 * 2) Fetch available post-processors from the API.
 * 3) Select one or more post-processors to run on the exported data.
 * 4) For each selected post-processor that defines an inputSchema,
 *    present a dynamically generated JSON schema form to collect user input.
 * 5) Submit these postProcessors and their corresponding user inputKwargs to the export mutation.
 *
 * The result of the export is a file that is post-processed according to the user's selections here.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import styled from "styled-components";
import {
  ApolloError,
  useLazyQuery,
  useMutation,
  useReactiveVar,
} from "@apollo/client";
import { toast } from "react-toastify";
import { Dropdown, DropdownOption } from "@os-legal/ui";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Spinner,
} from "@os-legal/ui";
import { Package, FileOutput, Settings, Info } from "lucide-react";
import { exportingCorpus } from "../../../graphql/cache";
import {
  StartExportCorpusInputs,
  StartExportCorpusOutputs,
  START_EXPORT_CORPUS,
} from "../../../graphql/mutations";
import {
  GET_POST_PROCESSORS,
  GetPostprocessorsInput,
  GetPostprocessorsOutput,
} from "../../../graphql/queries";

import Form from "@rjsf/core";
import { RJSFSchema } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";

import funsd_icon from "../../../assets/icons/FUNSD.png";
import open_contracts_icon from "../../../assets/icons/oc_45_dark.png";
import { ExportTypes } from "../../types";
import { PipelineComponentType } from "../../../types/graphql-api";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";
import { accentAlpha } from "../../../assets/configurations/osLegalStyles";
import { modalFooterBorder, modalFooterMobile } from "./sharedModalStyles";

// -- Styled Components --

const TABLET_BREAKPOINT = 768;

const StyledModalWrapper = styled.div`
  .oc-modal-overlay {
    padding: var(--oc-spacing-md);

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: 0;
      align-items: flex-end;
    }
  }

  .oc-modal {
    width: 100%;
    max-width: 600px;
    overflow-y: auto;
    overflow-x: visible;

    @media (max-width: ${TABLET_BREAKPOINT}px) {
      max-width: 90vw;
    }

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      max-width: 100%;
      max-height: 95vh;
      border-radius: var(--oc-radius-lg) var(--oc-radius-lg) 0 0;
      animation: oc-slide-up-fade 0.3s var(--oc-easing-spring);
    }
  }

  .oc-modal-body {
    background: var(--oc-bg-subtle, #f1f5f9);
    padding: var(--oc-spacing-lg);
    overflow: visible;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: var(--oc-spacing-md);
      padding-bottom: calc(var(--oc-spacing-xl) + 80px);
      -webkit-overflow-scrolling: touch;
      overflow-y: auto;
    }
  }

  .oc-modal-footer {
    background: var(--oc-bg-surface);
    ${modalFooterBorder}
    ${modalFooterMobile}
  }
`;

const FormSection = styled.div`
  background: var(--oc-bg-surface);
  border-radius: var(--oc-radius-lg);
  padding: var(--oc-spacing-lg);
  margin-bottom: var(--oc-spacing-md);
  box-shadow: var(--oc-shadow-sm);
  border: 1px solid var(--oc-border-default);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: var(--oc-spacing-md);
    margin-bottom: var(--oc-spacing-sm);
    border-radius: var(--oc-radius-md);
  }

  &:last-child {
    margin-bottom: 0;
  }
`;

const SectionTitle = styled.h3`
  font-size: var(--oc-font-size-xs);
  font-weight: 600;
  color: var(--oc-fg-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 var(--oc-spacing-md) 0;
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-sm);

  svg {
    width: 14px;
    height: 14px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 11px;
    margin-bottom: var(--oc-spacing-sm);
  }
`;

const FormatOption = styled.div<{ $isSelected: boolean }>`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-md);
  padding: var(--oc-spacing-md);
  border-radius: var(--oc-radius-md);
  border: 1px solid
    ${(props) =>
      props.$isSelected
        ? "var(--oc-accent, #0f766e)"
        : "var(--oc-border-default)"};
  background: ${(props) =>
    props.$isSelected ? accentAlpha(0.05) : "var(--oc-bg-surface)"};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: var(--oc-accent, #0f766e);
    background: ${accentAlpha(0.03)};
  }
`;

const FormatIcon = styled.img`
  width: 32px;
  height: 32px;
  border-radius: var(--oc-radius-sm);
  object-fit: contain;
`;

const FormatInfo = styled.div`
  flex: 1;
`;

const FormatName = styled.div`
  font-size: var(--oc-font-size-sm);
  font-weight: 600;
  color: var(--oc-fg-primary);
`;

const FormatDescription = styled.div`
  font-size: var(--oc-font-size-xs);
  color: var(--oc-fg-secondary);
  margin-top: 2px;
`;

const FormatList = styled.div`
  display: flex;
  flex-direction: column;
  gap: var(--oc-spacing-sm);
`;

const ProcessorFormCard = styled.div`
  padding: var(--oc-spacing-md);
  border: 1px solid var(--oc-border-default);
  border-radius: var(--oc-radius-md);
  background: var(--oc-bg-surface);
  margin-top: var(--oc-spacing-md);

  /* Style RJSF core form fields inside the card */
  .rjsf .form-group.field {
    margin-bottom: var(--oc-spacing-sm);
  }

  .rjsf .form-control {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid var(--oc-border-default, #ddd);
    border-radius: var(--oc-radius-sm, 4px);
    font-size: var(--oc-font-size-sm, 0.875rem);
  }

  .rjsf .control-label {
    display: block;
    font-size: var(--oc-font-size-sm, 0.875rem);
    font-weight: 600;
    margin-bottom: 0.25rem;
  }
`;

const ProcessorFormHeader = styled.div`
  display: flex;
  align-items: center;
  gap: var(--oc-spacing-sm);
  margin-bottom: var(--oc-spacing-md);
  padding-bottom: var(--oc-spacing-sm);
  border-bottom: 1px solid var(--oc-border-default);

  h4 {
    margin: 0;
    font-size: var(--oc-font-size-sm);
    font-weight: 600;
    color: var(--oc-fg-primary);
  }
`;

const HintText = styled.p`
  font-size: var(--oc-font-size-xs);
  color: var(--oc-fg-secondary);
  margin: 0 0 var(--oc-spacing-md) 0;
  line-height: 1.5;
`;

const LoadingOverlay = styled.div<{ $visible: boolean }>`
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(2px);
  display: ${(props) => (props.$visible ? "flex" : "none")};
  align-items: center;
  justify-content: center;
  z-index: 100;
  border-radius: var(--oc-radius-lg);
`;

const HeaderIcon = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--oc-radius-md);
  background: linear-gradient(
    135deg,
    var(--oc-accent) 0%,
    var(--oc-accent-hover) 100%
  );
  color: white;
  margin-right: var(--oc-spacing-sm);

  svg {
    width: 18px;
    height: 18px;
  }
`;

const SelectedIndicator = styled.div`
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--oc-accent, #0f766e);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  &::after {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: white;
  }
`;

const UnselectedIndicator = styled.div`
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid var(--oc-border-default);
  flex-shrink: 0;
`;

// -- Component --

export interface SelectExportTypeModalProps {
  open: boolean;
  onClose: () => void;
}

export function SelectExportTypeModal({
  open,
  onClose,
}: SelectExportTypeModalProps) {
  const exporting_corpus = useReactiveVar(exportingCorpus);

  const [exportFormat, setExportFormat] = useState<ExportTypes>(
    ExportTypes.OPEN_CONTRACTS
  );

  const [availablePostProcessors, setAvailablePostProcessors] = useState<
    PipelineComponentType[]
  >([]);

  const [selectedPostProcessors, setSelectedPostProcessors] = useState<
    string[]
  >([]);

  const [postProcessorKwargs, setPostProcessorKwargs] = useState<{
    [processorName: string]: any;
  }>({});

  const [fetchPostProcessors, { loading: loadingProcessors }] = useLazyQuery<
    GetPostprocessorsOutput,
    GetPostprocessorsInput
  >(GET_POST_PROCESSORS, {
    onCompleted: (data) => {
      if (
        data?.pipelineComponents?.postProcessors &&
        Array.isArray(data.pipelineComponents.postProcessors)
      ) {
        setAvailablePostProcessors(data.pipelineComponents.postProcessors);
      }
    },
    onError: (err) => {
      toast.error(`Failed to load post-processors: ${err.message}`);
    },
    fetchPolicy: "network-only",
  });

  const [startExportCorpus] = useMutation<
    StartExportCorpusOutputs,
    StartExportCorpusInputs
  >(START_EXPORT_CORPUS, {
    onCompleted: () => {
      toast.success(
        "Export started. Check export status under the user menu dropdown in the top right."
      );
      onClose();
    },
    onError: (err: ApolloError) => {
      toast.error(`Could not start export: ${err.message}`);
    },
  });

  useEffect(() => {
    if (open) {
      fetchPostProcessors();
    }
  }, [open, fetchPostProcessors]);

  const handleFormatSelect = useCallback((format: ExportTypes) => {
    setExportFormat(format);
  }, []);

  const handleSelectedProcessorsChange = useCallback(
    (value: string | string[] | null): void => {
      const selected = Array.isArray(value) ? value : [];
      const newKwargs: { [key: string]: any } = {};
      selected.forEach((procName: string) => {
        newKwargs[procName] = postProcessorKwargs[procName] ?? {};
      });
      setPostProcessorKwargs(newKwargs);
      setSelectedPostProcessors(selected);
    },
    [postProcessorKwargs]
  );

  const postProcessorDropdownOptions = useMemo<DropdownOption[]>(() => {
    return availablePostProcessors.map((pproc) => ({
      value: pproc.moduleName || "",
      label: pproc.name || "Unknown Post-Processor",
    }));
  }, [availablePostProcessors]);

  const onPostProcessorFormChange = useCallback(
    (processorName: string, formData: any) => {
      setPostProcessorKwargs((prev) => ({
        ...prev,
        [processorName]: formData,
      }));
    },
    []
  );

  const triggerCorpusExport = useCallback(() => {
    if (exporting_corpus) {
      startExportCorpus({
        variables: {
          corpusId: exporting_corpus.id,
          exportFormat,
          postProcessors: selectedPostProcessors,
          inputKwargs: postProcessorKwargs,
        },
      });
    }
  }, [
    exporting_corpus,
    exportFormat,
    postProcessorKwargs,
    selectedPostProcessors,
    startExportCorpus,
  ]);

  const renderPostProcessorForms = useMemo(() => {
    return selectedPostProcessors.map((procName) => {
      const procObj = availablePostProcessors.find(
        (p) => p.moduleName === procName
      );
      if (!procObj?.inputSchema || typeof procObj.inputSchema !== "object") {
        return null;
      }

      return (
        <ProcessorFormCard key={procName}>
          <ProcessorFormHeader>
            <Settings size={14} />
            <h4>{procObj.title || procName} Inputs</h4>
          </ProcessorFormHeader>
          <Form
            id={`postprocessor-${procName}`}
            schema={{
              type: "object",
              properties: procObj.inputSchema as RJSFSchema,
            }}
            validator={validator}
            formData={postProcessorKwargs[procName] || {}}
            onChange={(e) => onPostProcessorFormChange(procName, e.formData)}
            uiSchema={{
              "ui:submitButtonOptions": { norender: true },
            }}
          >
            <></>
          </Form>
        </ProcessorFormCard>
      );
    });
  }, [
    selectedPostProcessors,
    availablePostProcessors,
    postProcessorKwargs,
    onPostProcessorFormChange,
  ]);

  const corpusName = exporting_corpus?.title || "corpus";

  const headerTitle = (
    <>
      <HeaderIcon>
        <Package />
      </HeaderIcon>
      Export Corpus
    </>
  );

  return (
    <StyledModalWrapper>
      <Modal open={open} onClose={onClose} size="lg" closeOnEscape>
        <ModalHeader
          title={headerTitle}
          subtitle={`Configure export settings for "${corpusName}"`}
          onClose={onClose}
          showCloseButton={!loadingProcessors}
        />

        <ModalBody style={{ position: "relative" }}>
          <LoadingOverlay $visible={loadingProcessors}>
            <Spinner size={32} />
          </LoadingOverlay>

          {/* Export Format Section */}
          <FormSection>
            <SectionTitle>
              <FileOutput />
              Export Format
            </SectionTitle>
            <HintText>
              Choose the format for your exported corpus data.
            </HintText>

            <FormatList>
              <FormatOption
                $isSelected={exportFormat === ExportTypes.OPEN_CONTRACTS}
                onClick={() => handleFormatSelect(ExportTypes.OPEN_CONTRACTS)}
                data-testid="format-open-contracts"
              >
                {exportFormat === ExportTypes.OPEN_CONTRACTS ? (
                  <SelectedIndicator />
                ) : (
                  <UnselectedIndicator />
                )}
                <FormatIcon src={open_contracts_icon} alt="OpenContracts" />
                <FormatInfo>
                  <FormatName>OpenContracts</FormatName>
                  <FormatDescription>
                    Complete archive with annotated PDFs and metadata
                  </FormatDescription>
                </FormatInfo>
              </FormatOption>

              <FormatOption
                $isSelected={exportFormat === ExportTypes.FUNSD}
                onClick={() => handleFormatSelect(ExportTypes.FUNSD)}
                data-testid="format-funsd"
              >
                {exportFormat === ExportTypes.FUNSD ? (
                  <SelectedIndicator />
                ) : (
                  <UnselectedIndicator />
                )}
                <FormatIcon src={funsd_icon} alt="FUNSD" />
                <FormatInfo>
                  <FormatName>FUNSD</FormatName>
                  <FormatDescription>
                    Standard format for form understanding tasks
                  </FormatDescription>
                </FormatInfo>
              </FormatOption>
            </FormatList>
          </FormSection>

          {/* Post-Processing Section */}
          <FormSection>
            <SectionTitle>
              <Info />
              Post-Processing Options
            </SectionTitle>
            <HintText>
              Optionally select post-processors to transform your export data.
            </HintText>

            <Dropdown
              mode="multiselect"
              fluid
              searchable="local"
              placeholder="Select post-processors..."
              options={postProcessorDropdownOptions}
              onChange={handleSelectedProcessorsChange}
              value={selectedPostProcessors}
            />

            {selectedPostProcessors.length > 0 && renderPostProcessorForms}
          </FormSection>
        </ModalBody>

        <ModalFooter>
          <Button
            variant="secondary"
            onClick={onClose}
            disabled={loadingProcessors}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={triggerCorpusExport}
            disabled={loadingProcessors || !exportFormat}
            loading={loadingProcessors}
          >
            Start Export
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
}
