/**
 * BulkImportModal - Modal for importing a ZIP file with folder structure preserved.
 *
 * This modal provides:
 * 1. A confirmation step warning users about the import
 * 2. A file selection step with drag-and-drop
 * 3. Upload progress display
 *
 * The import streams the ZIP via multipart/form-data to
 * ``POST /api/imports/zip-to-corpus/``. The backend then:
 * - Preserves folder structure from the ZIP
 * - Creates document relationships if a relationships.csv file is present
 * - Validates ZIP security (path traversal, zip bombs, etc.)
 *
 * The legacy ``ImportZipToCorpus`` GraphQL mutation was removed because
 * base64-encoding large zips into a JSON request body crashed Apollo
 * with "Payload allocation size overflow" / "NetworkError when
 * attempting to fetch resource" for files past ~100 MB.
 */
import React, { useState, useRef, useCallback, useEffect } from "react";
import { useApolloClient, useQuery, useReactiveVar } from "@apollo/client";
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
import { evictCorpusDocumentCaches } from "../../../graphql/cacheEvictions";
import {
  GET_BULK_DOCUMENT_UPLOAD_STATUS,
  type BulkDocumentUploadStatusInput,
  type BulkDocumentUploadStatusOutput,
} from "../../../graphql/queries";
import { folderCorpusIdAtom } from "../../../atoms/folderAtoms";
import { useAtomValue } from "jotai";
import { importZipToCorpusMultipart } from "../../../utils/importHttp";
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
  ButtonIcon,
} from "./UploadModalStyles";

type UploadStep = "confirm" | "upload" | "progress";

export const BulkImportModal: React.FC = () => {
  const visible = useReactiveVar(showBulkImportModal);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const targetFolderId = useReactiveVar(selectedFolderIdVar);

  const [step, setStep] = useState<UploadStep>("confirm");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const completedJobIdRef = useRef<string | null>(null);
  const apolloClient = useApolloClient();
  const {
    data: statusData,
    error: statusError,
    stopPolling,
  } = useQuery<BulkDocumentUploadStatusOutput, BulkDocumentUploadStatusInput>(
    GET_BULK_DOCUMENT_UPLOAD_STATUS,
    {
      variables: { jobId: jobId ?? "" },
      skip: !jobId,
      fetchPolicy: "network-only",
      pollInterval: jobId ? 3000 : 0,
    }
  );
  const jobStatus = statusData?.bulkDocumentUploadStatus;

  useEffect(() => {
    if (jobStatus?.completed) stopPolling();
  }, [jobStatus?.completed, stopPolling]);

  useEffect(() => {
    if (
      !jobId ||
      !jobStatus?.completed ||
      completedJobIdRef.current === jobId
    ) {
      return;
    }

    completedJobIdRef.current = jobId;
    if (jobStatus.success) {
      // Refresh only after the worker has created the documents. Evicting at
      // HTTP 202 previously caused an immediate refetch with no new rows.
      evictCorpusDocumentCaches(apolloClient.cache);
      toast.success(
        `Import complete: ${jobStatus.processedFiles} of ${jobStatus.totalFiles} files processed.`
      );
    } else {
      toast.error(
        "Import completed with errors. Review the job details below."
      );
    }
  }, [apolloClient.cache, jobId, jobStatus]);

  /**
   * Resets all modal state and closes the modal.
   */
  const handleClose = useCallback(() => {
    setStep("confirm");
    setSelectedFile(null);
    setLoading(false);
    setError(null);
    setUploadProgress(0);
    setJobId(null);
    setIsDragActive(false);
    completedJobIdRef.current = null;
    showBulkImportModal(false);
  }, []);

  /**
   * Handles file selection. The File is held by reference and streamed
   * directly through ``fetch`` + ``FormData`` on submit — no base64
   * conversion, no in-memory copy of the bytes.
   */
  const handleFileSelect = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Please select a ZIP file.");
      return;
    }

    setSelectedFile(file);
    setError(null);
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
    if (!selectedFile || !corpusId) {
      setError("Missing required data for import.");
      return;
    }

    setLoading(true);
    setStep("progress");
    setUploadProgress(0);
    setJobId(null);

    try {
      const result = await importZipToCorpusMultipart({
        file: selectedFile,
        corpusId,
        targetFolderId: targetFolderId || undefined,
        makePublic: false,
        onProgress: (fraction) => setUploadProgress(fraction * 100),
      });

      if (result.ok) {
        // A 202 only confirms the archive was staged. The status query drives
        // completion and cache invalidation once the Celery task finishes.
        setJobId(result.job_id);
        setUploadProgress(100);
        toast.info(`Archive uploaded. Import job started: ${result.job_id}`);
      } else {
        setError(result.error || "Import failed. Please try again.");
        setStep("upload");
        setUploadProgress(0);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "An error occurred during import.";
      setError(message);
      setStep("upload");
      setUploadProgress(0);
    } finally {
      setLoading(false);
    }
  }, [selectedFile, corpusId, targetFolderId]);

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
      {!jobId ? (
        <>
          <h3>Uploading Archive...</h3>
          <p>The archive is being transferred and staged for import.</p>
          <UploadProgress $percent={uploadProgress} />
          <ProgressLabel>{Math.round(uploadProgress)}% uploaded</ProgressLabel>
        </>
      ) : jobStatus?.completed ? (
        <>
          <h3>
            {jobStatus.success
              ? "Import Complete"
              : "Import Completed with Errors"}
          </h3>
          <p>
            Processed {jobStatus.processedFiles} of {jobStatus.totalFiles} files
            {jobStatus.skippedFiles > 0
              ? `; skipped ${jobStatus.skippedFiles}`
              : ""}
            {jobStatus.errorFiles > 0 ? `; ${jobStatus.errorFiles} failed` : ""}
            .
          </p>
        </>
      ) : (
        <>
          <h3>Importing Documents...</h3>
          <p>
            The archive was uploaded. Documents are being processed in the
            background; you can close this dialog safely.
          </p>
        </>
      )}
      {jobId && <ProgressLabel>Job ID: {jobId}</ProgressLabel>}
      {jobStatus?.completed && jobStatus.errors.length > 0 && (
        <ErrorMessage>
          <AlertCircle />
          <div className="content">
            <div className="header">Import details</div>
            <div className="message">{jobStatus.errors.join(" ")}</div>
          </div>
        </ErrorMessage>
      )}
      {statusError && !jobStatus?.completed && (
        <p>
          The archive was accepted, but its status could not be refreshed. You
          can close this dialog safely and refresh the corpus later.
        </p>
      )}
    </ProgressContent>
  );

  const getSubtitle = () => {
    switch (step) {
      case "confirm":
        return "Review import details before proceeding";
      case "upload":
        return "Select a ZIP file to import";
      case "progress":
        return jobId
          ? jobStatus?.completed
            ? "Import status"
            : "Import is running in the background"
          : "Uploading your archive...";
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
          showCloseButton={step !== "progress" || !loading}
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
                  disabled={!selectedFile || loading}
                >
                  <ButtonIcon>
                    <CloudUpload />
                  </ButtonIcon>
                  Start Import
                </Button>
              </>
            )}
          </ModalFooter>
        )}
        {step === "progress" && !loading && (
          <ModalFooter>
            <Button variant="secondary" onClick={handleClose}>
              Close
            </Button>
          </ModalFooter>
        )}
      </Modal>
    </StyledModalWrapper>
  );
};
