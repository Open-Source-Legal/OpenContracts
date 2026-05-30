import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import { useQuery } from "@apollo/client";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
} from "@os-legal/ui";
import {
  Upload,
  FileArchive,
  ArrowLeft,
  ArrowRight,
  X,
  Check,
} from "lucide-react";
import {
  StyledModalWrapper,
  HeaderIcon,
  SectionTitle,
  EditSection,
  EditPanel,
  EditPanelHeader,
  ErrorMessage,
  InlineCorpusItem,
  CorpusListContainer,
} from "./UploadModalStyles";
import {
  FileDropZone,
  FileList,
  FileDetailsForm,
  CorpusSelectorCard,
  StepIndicator,
  UploadProgress,
  UploadMode,
  UploadStep,
} from "./components";
import { AcceptedFileType } from "./components/FileDropZone";
import {
  useUploadState,
  useUploadMutations,
  useCorpusSearch,
  FileDetails,
} from "./hooks";
import { CorpusType } from "../../../../types/graphql-api";
import {
  UPLOAD,
  DOCUMENT_METADATA,
} from "../../../../assets/configurations/constants";
import {
  GET_SUPPORTED_MIME_TYPES,
  SupportedMimeTypesQueryResult,
} from "../../../admin/system_settings/graphql";

export interface UploadModalProps {
  open: boolean;
  onClose: () => void;
  /** Pre-selected corpus ID - skips corpus selection step */
  corpusId?: string | null;
  /** Pre-selected folder ID */
  folderId?: string | null;
  /** Force a specific mode instead of auto-detecting */
  forceMode?: UploadMode;
  /** Files to preload into the modal */
  preloadedFiles?: File[];
  /** Callback when upload completes */
  onUploadComplete?: () => void;
  /** Refetch callback after successful upload */
  refetch?: () => void;
}

/**
 * Unified Upload Modal supporting single document and bulk ZIP upload.
 *
 * Features:
 * - Dynamically fetches supported file types from backend pipeline registry
 * - Auto-detects mode based on file type (ZIP → bulk, document → single)
 * - Multi-step wizard for single mode (Select → Details → Corpus)
 * - Simplified single-step flow for bulk mode
 * - Uses @os-legal/ui design system
 */
export const UploadModal: React.FC<UploadModalProps> = ({
  open,
  onClose,
  corpusId,
  folderId,
  forceMode,
  preloadedFiles,
  onUploadComplete,
  refetch,
}) => {
  // Mode state - auto-detected or forced
  const [mode, setMode] = useState<UploadMode>(forceMode || "single");

  // Step state for single mode
  const [step, setStep] = useState<UploadStep>("select");

  // For bulk mode - the selected ZIP file
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipUploadProgress, setZipUploadProgress] = useState<number>(0);

  // Selected corpus for upload (when not pre-provided)
  const [selectedCorpus, setSelectedCorpus] = useState<CorpusType | null>(null);

  // Error state
  const [error, setError] = useState<string | null>(null);

  // Track if modal just opened to handle initialization
  const prevOpenRef = useRef(false);

  // File upload state for single mode
  // Destructure to avoid dependency array issues (uploadState object changes every render)
  const uploadState = useUploadState();
  const {
    addFiles: uploadStateAddFiles,
    reset: uploadStateReset,
    setFileStatus: uploadStateSetFileStatus,
  } = uploadState;

  // Corpus search hook - needed for both single mode (corpus step) and bulk mode (inline selector)
  const corpusSearch = useCorpusSearch({
    skip: !open || !!corpusId,
    requireUpdatePermission: true,
  });

  // Query supported file types from backend pipeline registry
  const { data: mimeTypesData } = useQuery<SupportedMimeTypesQueryResult>(
    GET_SUPPORTED_MIME_TYPES,
    { fetchPolicy: "cache-first" }
  );

  // Derive accepted file types (only fully supported ones) and MIME set for filtering
  const acceptedFileTypes: AcceptedFileType[] = useMemo(() => {
    if (!mimeTypesData?.supportedMimeTypes) return [];
    return mimeTypesData.supportedMimeTypes
      .filter((mt) => mt.fullySupported)
      .map((mt) => ({
        mimetype: mt.mimetype,
        extension: mt.fileType,
        label: mt.label,
      }));
  }, [mimeTypesData]);

  const acceptedMimeSet = useMemo(
    () => new Set(acceptedFileTypes.map((ft) => ft.mimetype)),
    [acceptedFileTypes]
  );

  const acceptedExtensions = useMemo(
    () => new Set(acceptedFileTypes.map((ft) => `.${ft.extension}`)),
    [acceptedFileTypes]
  );

  const acceptedLabels = useMemo(() => {
    if (acceptedFileTypes.length === 0) return "PDF";
    return acceptedFileTypes.map((ft) => ft.label).join(", ");
  }, [acceptedFileTypes]);

  // Upload mutations
  const uploadMutations = useUploadMutations({
    corpusId: corpusId ?? selectedCorpus?.id ?? undefined,
    folderId: folderId ?? undefined,
    onFileStatusChange: uploadStateSetFileStatus,
    onComplete: () => {
      onUploadComplete?.();
      refetch?.();
      onClose();
    },
  });

  // Handle modal open/close
  useEffect(() => {
    const justOpened = open && !prevOpenRef.current;
    prevOpenRef.current = open;

    if (justOpened) {
      // Reset state when modal opens
      setStep("select");
      setError(null);
      setZipFile(null);
      setZipUploadProgress(0);
      setSelectedCorpus(null);
      uploadStateReset();

      // Note: preloadedFiles are handled in a separate effect to handle
      // timing issues with React batching (files may arrive after modal opens)

      // Set mode based on force or default
      setMode(forceMode || "single");
    }

    if (!open) {
      // Clean up on close
      setError(null);
    }
  }, [open, forceMode]);

  // Handle preloaded files arriving (may come after modal opens due to React batching)
  // This is separate from the open transition effect to handle timing issues
  const preloadedFilesProcessedRef = useRef(false);

  useEffect(() => {
    // Only process preloaded files once per modal open, and only when modal is open
    if (
      open &&
      preloadedFiles &&
      preloadedFiles.length > 0 &&
      !preloadedFilesProcessedRef.current
    ) {
      preloadedFilesProcessedRef.current = true;
      uploadStateAddFiles(preloadedFiles);
    }

    // Reset the processed flag when modal closes
    if (!open) {
      preloadedFilesProcessedRef.current = false;
    }
  }, [open, preloadedFiles, uploadStateAddFiles]);

  // Handle file selection
  const handleFilesSelected = useCallback(
    (files: File[]) => {
      setError(null);

      if (mode === "bulk") {
        // Bulk mode - only accept ZIP
        const zipFiles = files.filter(
          (f) => f.type === "application/zip" || f.name.endsWith(".zip")
        );
        if (zipFiles.length > 0) {
          setZipFile(zipFiles[0]);
        } else {
          setError("Please select a .zip file");
        }
      } else {
        // Single mode - filter to supported file types
        const validFiles = files.filter((f) => {
          if (acceptedMimeSet.size > 0) {
            const ext = f.name.includes(".")
              ? `.${f.name.split(".").pop()?.toLowerCase()}`
              : "";
            return acceptedMimeSet.has(f.type) || acceptedExtensions.has(ext);
          }
          // Fallback to PDF if backend hasn't responded yet
          return f.type === "application/pdf" || f.name.endsWith(".pdf");
        });
        if (validFiles.length > 0) {
          uploadState.addFiles(validFiles);
        } else {
          setError(`Please select supported files (${acceptedLabels})`);
        }
      }
    },
    [mode, uploadState, acceptedMimeSet, acceptedExtensions, acceptedLabels]
  );

  // Handle file rejections from dropzone
  const handleFileRejected = useCallback(() => {
    if (mode === "bulk") {
      setError("Invalid file type. Please select a .zip file.");
    } else {
      setError(`Invalid file type. Supported formats: ${acceptedLabels}`);
    }
  }, [mode, acceptedLabels]);

  // Form validation for single mode
  const isFormValid = useCallback(() => {
    if (!uploadState.hasFiles) return false;

    // Check all files have required fields with length constraints
    return uploadState.files.every((pkg) => {
      if (!pkg.formData) return false;

      const title = pkg.formData.title?.trim() ?? "";
      const description = pkg.formData.description?.trim() ?? "";
      const slug = pkg.formData.slug?.trim() ?? "";

      // Required fields must be non-empty and within limits
      const titleValid =
        title.length > 0 && title.length <= DOCUMENT_METADATA.MAX_TITLE_LENGTH;
      const descriptionValid =
        description.length > 0 &&
        description.length <= DOCUMENT_METADATA.MAX_DESCRIPTION_LENGTH;
      // Slug is optional but if provided must be within limits
      const slugValid =
        slug.length === 0 || slug.length <= DOCUMENT_METADATA.MAX_SLUG_LENGTH;

      return titleValid && descriptionValid && slugValid;
    });
  }, [uploadState.files, uploadState.hasFiles]);

  // Handle step navigation
  const handleContinue = useCallback(() => {
    if (step === "select" && uploadState.hasFiles) {
      setStep("details");
      // Select first file for editing
      if (uploadState.selectedIndex < 0) {
        uploadState.setSelectedIndex(0);
      }
    } else if (step === "details") {
      if (corpusId) {
        // Skip corpus step if already provided
        setStep("uploading");
        uploadMutations.uploadFiles(uploadState.files);
      } else {
        setStep("corpus");
      }
    } else if (step === "corpus") {
      setStep("uploading");
      uploadMutations.uploadFiles(uploadState.files, selectedCorpus?.id);
    }
  }, [step, uploadState, corpusId, selectedCorpus, uploadMutations]);

  const handleBack = useCallback(() => {
    if (step === "details") {
      setStep("select");
    } else if (step === "corpus") {
      setStep("details");
    }
  }, [step]);

  // Handle form field changes
  const handleFormChange = useCallback(
    (updates: Partial<FileDetails>) => {
      if (uploadState.selectedIndex >= 0) {
        uploadState.updateFileDetails(uploadState.selectedIndex, updates);
      }
    },
    [uploadState]
  );

  // Handle bulk upload
  const handleBulkUpload = useCallback(async () => {
    if (!zipFile) return;

    setError(null);
    setZipUploadProgress(UPLOAD.BULK_PROGRESS_INITIAL);

    const success = await uploadMutations.uploadZipFile(
      zipFile,
      selectedCorpus?.id
    );

    if (success) {
      setZipUploadProgress(100);
      refetch?.();
      onUploadComplete?.();
      onClose();
    } else {
      setZipUploadProgress(0);
      // Show visible error in modal (toast is also shown in mutation hook)
      setError("Upload failed. Please check the file and try again.");
    }
  }, [
    zipFile,
    selectedCorpus,
    uploadMutations,
    refetch,
    onUploadComplete,
    onClose,
  ]);

  // Handle skip corpus
  const handleSkipCorpus = useCallback(() => {
    setStep("uploading");
    uploadMutations.uploadFiles(uploadState.files, null);
  }, [uploadState.files, uploadMutations]);

  // Get header content
  const getHeaderTitle = () => {
    if (mode === "bulk") {
      return (
        <>
          <HeaderIcon>
            <FileArchive />
          </HeaderIcon>
          Bulk Upload Documents
        </>
      );
    }
    return (
      <>
        <HeaderIcon>
          <Upload />
        </HeaderIcon>
        Upload Documents
      </>
    );
  };

  const getSubtitle = () => {
    if (mode === "bulk") {
      return "Upload multiple documents from a ZIP file";
    }
    switch (step) {
      case "select":
        return "Select files to upload";
      case "details":
        return "Review and edit document details";
      case "corpus":
        return "Optionally add to a corpus";
      case "uploading":
        return "Processing your uploads...";
      default:
        return "";
    }
  };

  // Get current file's form data
  const currentFormData =
    uploadState.selectedIndex >= 0
      ? uploadState.files[uploadState.selectedIndex]?.formData || null
      : null;

  const isUploading = step === "uploading" || uploadMutations.isUploading;

  return (
    <StyledModalWrapper>
      <Modal
        open={open}
        onClose={onClose}
        size="lg"
        closeOnEscape={!isUploading}
      >
        <ModalHeader
          title={getHeaderTitle()}
          subtitle={getSubtitle()}
          onClose={onClose}
          showCloseButton={!isUploading}
        />

        <ModalBody>
          {/* Error message */}
          {error && (
            <ErrorMessage>
              <X />
              <div className="content">
                <div className="header">Error</div>
                <div className="message">{error}</div>
              </div>
            </ErrorMessage>
          )}

          {/* Bulk mode content */}
          {mode === "bulk" && (
            <>
              <FileDropZone
                mode="bulk"
                selectedFile={zipFile}
                disabled={isUploading}
                acceptedFileTypes={acceptedFileTypes}
                maxSizeBytes={UPLOAD.MAX_IMPORT_ZIP_BYTES}
                maxSizeDisplay={UPLOAD.MAX_IMPORT_ZIP_DISPLAY}
                onFilesSelected={handleFilesSelected}
                onFileRejected={handleFileRejected}
              />

              {/* Corpus selector for bulk mode */}
              <div style={{ marginTop: "var(--oc-spacing-md)" }}>
                <SectionTitle>Add to Corpus (Optional)</SectionTitle>
                <Input
                  id="bulk-corpus-search"
                  placeholder="Search corpuses..."
                  value={corpusSearch.searchTerm}
                  onChange={(e) => corpusSearch.setSearchTerm(e.target.value)}
                  disabled={isUploading}
                  size="lg"
                  fullWidth
                />
                {corpusSearch.corpuses.length > 0 && (
                  <CorpusListContainer>
                    {corpusSearch.corpuses
                      .slice(0, UPLOAD.CORPUS_PREVIEW_LIMIT)
                      .map((corpus) => (
                        <InlineCorpusItem
                          key={corpus.id}
                          $selected={selectedCorpus?.id === corpus.id}
                          onClick={() =>
                            setSelectedCorpus(
                              selectedCorpus?.id === corpus.id ? null : corpus
                            )
                          }
                          role="button"
                          tabIndex={0}
                        >
                          <div className="corpus-title">{corpus.title}</div>
                        </InlineCorpusItem>
                      ))}
                  </CorpusListContainer>
                )}
              </div>

              {/* Progress for bulk mode */}
              {zipUploadProgress > 0 && (
                <UploadProgress
                  files={[
                    {
                      file: zipFile!,
                      formData: { title: "", slug: "", description: "" },
                      status:
                        zipUploadProgress === 100 ? "success" : "uploading",
                    },
                  ]}
                />
              )}
            </>
          )}

          {/* Single mode content */}
          {mode === "single" && (
            <>
              {/* Step indicator */}
              <StepIndicator currentStep={step} showCorpusStep={!corpusId} />

              {/* Uploading progress */}
              {step === "uploading" && (
                <>
                  <UploadProgress files={uploadState.files} />
                  <FileList
                    files={uploadState.files}
                    selectedIndex={uploadState.selectedIndex}
                    onSelect={uploadState.toggleSelectedFile}
                    onRemove={() => {}}
                    disabled={true}
                  />
                </>
              )}

              {/* Select step */}
              {step === "select" && (
                <>
                  {!uploadState.hasFiles ? (
                    <FileDropZone
                      mode="single"
                      hasFiles={uploadState.hasFiles}
                      acceptedFileTypes={acceptedFileTypes}
                      onFilesSelected={handleFilesSelected}
                      onFileRejected={handleFileRejected}
                    />
                  ) : (
                    <FileList
                      files={uploadState.files}
                      selectedIndex={uploadState.selectedIndex}
                      onSelect={uploadState.toggleSelectedFile}
                      onRemove={uploadState.removeFile}
                    />
                  )}
                </>
              )}

              {/* Details step */}
              {step === "details" && (
                <EditSection>
                  <EditPanel>
                    <EditPanelHeader>Selected Files</EditPanelHeader>
                    <FileList
                      files={uploadState.files}
                      selectedIndex={uploadState.selectedIndex}
                      onSelect={uploadState.toggleSelectedFile}
                      onRemove={uploadState.removeFile}
                    />
                  </EditPanel>
                  <EditPanel>
                    <EditPanelHeader>Document Details</EditPanelHeader>
                    <FileDetailsForm
                      formData={currentFormData}
                      onChange={handleFormChange}
                    />
                  </EditPanel>
                </EditSection>
              )}

              {/* Corpus step */}
              {step === "corpus" && !corpusId && (
                <CorpusSelectorCard
                  corpuses={corpusSearch.corpuses}
                  selectedCorpus={selectedCorpus}
                  onSelect={setSelectedCorpus}
                  onSearchChange={corpusSearch.debouncedSetSearchTerm}
                  searchTerm={corpusSearch.searchTerm}
                  loading={corpusSearch.loading}
                />
              )}
            </>
          )}
        </ModalBody>

        <ModalFooter>
          {/* Bulk mode actions */}
          {mode === "bulk" && (
            <>
              <Button
                variant="secondary"
                onClick={onClose}
                disabled={isUploading}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleBulkUpload}
                disabled={!zipFile || isUploading}
                loading={isUploading}
              >
                {isUploading ? (
                  "Uploading..."
                ) : (
                  <>
                    <Upload style={{ width: 16, height: 16, marginRight: 8 }} />
                    Upload ZIP
                  </>
                )}
              </Button>
            </>
          )}

          {/* Single mode actions */}
          {mode === "single" && (
            <>
              <Button
                variant="secondary"
                onClick={onClose}
                disabled={isUploading}
              >
                <X style={{ width: 16, height: 16, marginRight: 8 }} />
                {isUploading ? "Close" : "Cancel"}
              </Button>

              {step === "select" && uploadState.hasFiles && (
                <Button variant="primary" onClick={handleContinue}>
                  Continue
                  <ArrowRight
                    style={{ width: 16, height: 16, marginLeft: 8 }}
                  />
                </Button>
              )}

              {step === "details" && (
                <>
                  <Button variant="secondary" onClick={handleBack}>
                    <ArrowLeft
                      style={{ width: 16, height: 16, marginRight: 8 }}
                    />
                    Back
                  </Button>
                  {corpusId ? (
                    <Button
                      variant="primary"
                      onClick={handleContinue}
                      disabled={!isFormValid()}
                    >
                      <Upload
                        style={{ width: 16, height: 16, marginRight: 8 }}
                      />
                      Upload
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        onClick={handleSkipCorpus}
                        disabled={!isFormValid()}
                      >
                        Skip Corpus
                      </Button>
                      <Button
                        variant="primary"
                        onClick={handleContinue}
                        disabled={!isFormValid()}
                      >
                        Continue
                        <ArrowRight
                          style={{ width: 16, height: 16, marginLeft: 8 }}
                        />
                      </Button>
                    </>
                  )}
                </>
              )}

              {step === "corpus" && !corpusId && (
                <>
                  <Button variant="secondary" onClick={handleBack}>
                    <ArrowLeft
                      style={{ width: 16, height: 16, marginRight: 8 }}
                    />
                    Back
                  </Button>
                  <Button variant="secondary" onClick={handleSkipCorpus}>
                    Skip
                  </Button>
                  <Button variant="primary" onClick={handleContinue}>
                    <Upload style={{ width: 16, height: 16, marginRight: 8 }} />
                    Upload
                  </Button>
                </>
              )}
            </>
          )}
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};

export default UploadModal;
