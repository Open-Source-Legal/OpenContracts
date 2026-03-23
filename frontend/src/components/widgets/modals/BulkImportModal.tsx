/**
 * BulkImportModal - Modal for importing a ZIP file with folder structure preserved.
 *
 * This modal provides:
 * 1. A confirmation step warning users about the import
 * 2. A file selection step with drag-and-drop
 * 3. Upload progress display
 *
 * The import uses the ImportZipToCorpus mutation which:
 * - Preserves folder structure from the ZIP
 * - Creates document relationships if a relationships.csv file is present
 * - Validates ZIP security (path traversal, zip bombs, etc.)
 */
import React, { useState, useRef, useCallback } from "react";
import { useMutation, useReactiveVar } from "@apollo/client";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { toast } from "react-toastify";
import {
  CheckCircle,
  FileArchive,
  CloudUpload,
  AlertTriangle,
  Info,
  AlertCircle,
  RefreshCw,
  FolderOpen,
  Loader,
} from "lucide-react";

import {
  showBulkImportModal,
  selectedFolderId as selectedFolderIdVar,
} from "../../../graphql/cache";
import { folderCorpusIdAtom } from "../../../atoms/folderAtoms";
import { useAtomValue } from "jotai";
import {
  IMPORT_ZIP_TO_CORPUS,
  ImportZipToCorpusInputs,
  ImportZipToCorpusOutputs,
} from "../../../graphql/mutations";
import {
  StyledModalWrapper,
  HeaderIcon,
  DropZone,
  DropZoneIcon,
  DropZoneText,
  DropZoneButton,
  UploadProgress,
  ProgressLabel,
  ErrorMessage,
  StepIndicator,
  Step,
  StepConnector,
  AlertBox,
  AlertTitle,
  AlertBody,
  SpinnerIcon,
  ProgressContent,
} from "./UploadModalStyles";

type UploadStep = "confirm" | "upload" | "progress";

export const BulkImportModal: React.FC = () => {
  const visible = useReactiveVar(showBulkImportModal);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const targetFolderId = useReactiveVar(selectedFolderIdVar);

  const [step, setStep] = useState<UploadStep>("confirm");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [base64File, setBase64File] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [importZipMutation] = useMutation<
    ImportZipToCorpusOutputs,
    ImportZipToCorpusInputs
  >(IMPORT_ZIP_TO_CORPUS, {
    // Evict documents and folders from cache to force refetch after import
    update(cache) {
      cache.evict({ fieldName: "documents" });
      cache.evict({ fieldName: "corpusFolders" });
      cache.gc();
    },
  });

  /**
   * Resets all modal state and closes the modal.
   */
  const handleClose = useCallback(() => {
    setStep("confirm");
    setSelectedFile(null);
    setBase64File(null);
    setLoading(false);
    setError(null);
    setUploadProgress(0);
    setIsDragActive(false);
    showBulkImportModal(false);
  }, []);

  /**
   * Handles file selection and converts to base64.
   */
  const handleFileSelect = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Please select a ZIP file.");
      return;
    }

    setSelectedFile(file);
    setError(null);

    // Convert to base64
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result as string;
      // Remove the data URL prefix (e.g., "data:application/zip;base64,")
      const base64Data = base64.split(",")[1];
      setBase64File(base64Data);
    };
    reader.onerror = () => {
      setError("Failed to read the file. Please try again.");
    };
    reader.readAsDataURL(file);
  }, []);

  /**
   * Handle file input change event.
   */
  const handleFileInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect]
  );

  /**
   * Handle drag events.
   */
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragActive(false);

      const file = e.dataTransfer.files?.[0];
      if (file) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect]
  );

  /**
   * Trigger file input click.
   */
  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  /**
   * Handle the import submission.
   */
  const handleImport = useCallback(async () => {
    if (!base64File || !corpusId) {
      setError("Missing required data for import.");
      return;
    }

    setLoading(true);
    setStep("progress");
    setUploadProgress(10);

    try {
      // Simulate progress during upload
      const progressInterval = setInterval(() => {
        setUploadProgress((prev) => Math.min(prev + 10, 90));
      }, 500);

      const result = await importZipMutation({
        variables: {
          base64FileString: base64File,
          corpusId,
          targetFolderId: targetFolderId || undefined,
          makePublic: false,
        },
      });

      clearInterval(progressInterval);

      if (result.data?.importZipToCorpus?.ok) {
        setUploadProgress(100);
        toast.success(
          `Import started! Job ID: ${
            result.data.importZipToCorpus.jobId || "N/A"
          }`
        );
        // Close modal after a brief delay to show completion
        setTimeout(() => {
          handleClose();
        }, 1500);
      } else {
        setError(
          result.data?.importZipToCorpus?.message ||
            "Import failed. Please try again."
        );
        setStep("upload");
        setUploadProgress(0);
      }
    } catch (err: any) {
      setError(err.message || "An error occurred during import.");
      setStep("upload");
      setUploadProgress(0);
    } finally {
      setLoading(false);
    }
  }, [base64File, corpusId, targetFolderId, importZipMutation, handleClose]);

  /**
   * Proceed to upload step after confirmation.
   */
  const handleConfirm = useCallback(() => {
    setStep("upload");
  }, []);

  /**
   * Go back to confirmation step.
   */
  const handleBack = useCallback(() => {
    setStep("confirm");
    setSelectedFile(null);
    setBase64File(null);
    setError(null);
  }, []);

  /**
   * Render the step indicator.
   */
  const renderStepIndicator = () => (
    <StepIndicator>
      <Step $active={step === "confirm"} $completed={step !== "confirm"}>
        <CheckCircle size={13} />
        Confirm
      </Step>
      <StepConnector $completed={step !== "confirm"} />
      <Step $active={step === "upload"} $completed={step === "progress"}>
        <FileArchive size={13} />
        Select File
      </Step>
      <StepConnector $completed={step === "progress"} />
      <Step $active={step === "progress"}>
        <CloudUpload size={13} />
        Import
      </Step>
    </StepIndicator>
  );

  /**
   * Render the confirmation step content.
   */
  const renderConfirmStep = () => (
    <div>
      <AlertBox $variant="warning">
        <AlertTriangle />
        <AlertBody>
          <AlertTitle>
            Important: Bulk Import Cannot Be Easily Undone
          </AlertTitle>
          <p>
            This will import all documents from the ZIP file into the current
            corpus, preserving the folder structure. Consider the following:
          </p>
          <ul>
            <li>
              Documents will be created with the folder structure from the ZIP
            </li>
            <li>
              If a <strong>relationships.csv</strong> file is included, document
              relationships will be automatically created
            </li>
            <li>
              Duplicate file paths will create new versions of existing
              documents
            </li>
            <li>
              Removing imported documents requires deleting them individually or
              in batches
            </li>
          </ul>
        </AlertBody>
      </AlertBox>

      <AlertBox $variant="info">
        <Info />
        <AlertBody>
          <AlertTitle>Supported Format</AlertTitle>
          <p>
            Upload a ZIP file containing PDF, DOCX, PPTX, XLSX, or TXT files.
            The folder structure within the ZIP will be preserved in the corpus.
          </p>
        </AlertBody>
      </AlertBox>
    </div>
  );

  /**
   * Render the upload step content.
   */
  const renderUploadStep = () => (
    <div>
      {error && (
        <ErrorMessage>
          <AlertCircle />
          <div className="content">
            <div className="header">Error</div>
            <div className="message">{error}</div>
          </div>
        </ErrorMessage>
      )}

      <DropZone
        $isDragActive={isDragActive}
        $hasFiles={!!selectedFile}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={selectedFile ? undefined : handleBrowseClick}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip"
          style={{ display: "none" }}
          onChange={handleFileInputChange}
        />

        {selectedFile ? (
          <>
            <DropZoneIcon>
              <FileArchive />
            </DropZoneIcon>
            <DropZoneText>
              <div className="primary-text">{selectedFile.name}</div>
              <div className="secondary-text">
                {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
              </div>
            </DropZoneText>
            <DropZoneButton onClick={handleBrowseClick}>
              <RefreshCw /> Choose Different File
            </DropZoneButton>
          </>
        ) : (
          <>
            <DropZoneIcon>
              <CloudUpload />
            </DropZoneIcon>
            <DropZoneText>
              <div className="primary-text">
                {isDragActive
                  ? "Drop your ZIP file here"
                  : "Drag & drop a ZIP file here"}
              </div>
              <div className="secondary-text">or click to browse</div>
            </DropZoneText>
            <DropZoneButton onClick={handleBrowseClick}>
              <FolderOpen /> Browse Files
            </DropZoneButton>
          </>
        )}
      </DropZone>
    </div>
  );

  /**
   * Render the progress step content.
   */
  const renderProgressStep = () => (
    <ProgressContent>
      <SpinnerIcon>
        <Loader />
      </SpinnerIcon>
      <h3>Importing Documents...</h3>
      <p>This may take a few moments depending on the size of your ZIP file.</p>
      <UploadProgress $percent={uploadProgress} />
      <ProgressLabel>{Math.round(uploadProgress)}%</ProgressLabel>
    </ProgressContent>
  );

  const getSubtitle = () => {
    switch (step) {
      case "confirm":
        return "Review import details before proceeding";
      case "upload":
        return "Select a ZIP file to import";
      case "progress":
        return "Processing your import...";
      default:
        return "";
    }
  };

  if (!visible) {
    return null;
  }

  return (
    <StyledModalWrapper>
      <Modal open={visible} onClose={handleClose} size="md">
        <ModalHeader
          title={
            <>
              <HeaderIcon>
                <FileArchive />
              </HeaderIcon>
              Bulk Import Documents
            </>
          }
          subtitle={getSubtitle()}
          onClose={handleClose}
          showCloseButton={step !== "progress"}
        />

        <ModalBody>
          {renderStepIndicator()}
          {step === "confirm" && renderConfirmStep()}
          {step === "upload" && renderUploadStep()}
          {step === "progress" && renderProgressStep()}
        </ModalBody>

        {step !== "progress" && (
          <ModalFooter>
            {step === "confirm" && (
              <>
                <Button variant="secondary" onClick={handleClose}>
                  Cancel
                </Button>
                <Button variant="primary" onClick={handleConfirm}>
                  Continue
                </Button>
              </>
            )}
            {step === "upload" && (
              <>
                <Button variant="secondary" onClick={handleBack}>
                  Back
                </Button>
                <Button
                  variant="primary"
                  onClick={handleImport}
                  disabled={!selectedFile || !base64File || loading}
                >
                  <CloudUpload
                    style={{ width: 16, height: 16, marginRight: 8 }}
                  />
                  Start Import
                </Button>
              </>
            )}
          </ModalFooter>
        )}
      </Modal>
    </StyledModalWrapper>
  );
};
