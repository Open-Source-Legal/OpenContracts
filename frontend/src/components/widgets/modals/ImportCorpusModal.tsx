/**
 * ImportCorpusModal - Modal for importing a full OpenContracts corpus export ZIP.
 *
 * The import streams the ZIP via multipart/form-data to
 * ``POST /api/imports/corpus/``. The backend then:
 * - Creates a NEW corpus (the user becomes the creator with CRUD permissions)
 * - Hydrates documents, annotations, label sets, and analyses from the export
 *
 * Visibility of the trigger button is gated on the server-derived
 * `me.canImportCorpus` field; this modal still defends itself against
 * disallowed users by showing the server's permission error if the
 * upload is rejected.
 *
 * The legacy ``importOpenContractsZip`` GraphQL mutation was removed
 * because base64-encoding large export zips into a JSON request body
 * crashed Apollo for files past ~100 MB.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useApolloClient, useReactiveVar } from "@apollo/client";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { toast } from "react-toastify";
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  CloudUpload,
  FileArchive,
  FolderOpen,
  Info,
  Loader,
  RefreshCw,
} from "lucide-react";

import { UPLOAD } from "../../../assets/configurations/constants";
import { showImportCorpusModal } from "../../../graphql/cache";
import { importCorpusExportMultipart } from "../../../utils/importHttp";
import {
  AlertBody,
  AlertBox,
  AlertTitle,
  ButtonIcon,
  DropZone,
  DropZoneButton,
  DropZoneIcon,
  DropZoneText,
  ErrorMessage,
  HeaderIcon,
  ProgressContent,
  ProgressLabel,
  SpinnerIcon,
  Step,
  StepConnector,
  StepIndicator,
  StyledModalWrapper,
  UploadProgress,
} from "./UploadModalStyles";

type ImportStep = "confirm" | "upload" | "progress";

export const ImportCorpusModal: React.FC = () => {
  const visible = useReactiveVar(showImportCorpusModal);

  const [step, setStep] = useState<ImportStep>("confirm");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const progressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null
  );
  const apolloClient = useApolloClient();

  const clearProgressInterval = useCallback(() => {
    if (progressIntervalRef.current !== null) {
      clearInterval(progressIntervalRef.current);
      progressIntervalRef.current = null;
    }
  }, []);

  useEffect(() => clearProgressInterval, [clearProgressInterval]);

  const handleClose = useCallback(() => {
    setStep("confirm");
    setSelectedFile(null);
    setLoading(false);
    setError(null);
    setUploadProgress(0);
    setIsDragActive(false);
    showImportCorpusModal(false);
  }, []);

  const handleFileSelect = useCallback((file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Please select a ZIP file.");
      return;
    }

    if (file.size > UPLOAD.MAX_IMPORT_ZIP_BYTES) {
      setError(
        `File exceeds the ${UPLOAD.MAX_IMPORT_ZIP_DISPLAY} import limit.`
      );
      return;
    }

    setSelectedFile(file);
    setError(null);
  }, []);

  const handleFileInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect]
  );

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
      if (file) handleFileSelect(file);
    },
    [handleFileSelect]
  );

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleImport = useCallback(async () => {
    if (!selectedFile) {
      setError("Please choose a ZIP file to import.");
      return;
    }

    setLoading(true);
    setStep("progress");
    setUploadProgress(10);

    progressIntervalRef.current = setInterval(() => {
      setUploadProgress((prev) => Math.min(prev + 10, 90));
    }, 500);

    try {
      const result = await importCorpusExportMultipart({ file: selectedFile });

      clearProgressInterval();

      if (result.ok) {
        // Make the freshly-created corpus visible in the corpus list view.
        apolloClient.cache.evict({ fieldName: "corpuses" });
        apolloClient.cache.gc();

        setUploadProgress(100);
        toast.success("SUCCESS! Corpus file upload and import has started.");
        setTimeout(() => handleClose(), 1500);
      } else {
        setError(result.error || "Import failed. Please try again.");
        setStep("upload");
        setUploadProgress(0);
      }
    } catch (err) {
      clearProgressInterval();
      const message =
        err instanceof Error ? err.message : "An error occurred during import.";
      setError(message);
      setStep("upload");
      setUploadProgress(0);
    } finally {
      setLoading(false);
    }
  }, [selectedFile, apolloClient, handleClose, clearProgressInterval]);

  const handleConfirm = useCallback(() => setStep("upload"), []);

  const handleBack = useCallback(() => {
    setStep("confirm");
    setSelectedFile(null);
    setError(null);
  }, []);

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

  const renderConfirmStep = () => (
    <div>
      <AlertBox $variant="warning">
        <AlertTriangle />
        <AlertBody>
          <AlertTitle>Importing creates a new corpus</AlertTitle>
          <p>
            This will unpack the OpenContracts export ZIP into a brand-new
            corpus that you own. Note:
          </p>
          <ul>
            <li>
              Only files produced by the OpenContracts corpus export are
              supported (use bulk document upload for raw PDFs/DOCX)
            </li>
            <li>
              Documents, annotations, label sets, and analyses are restored
            </li>
            <li>The import runs asynchronously; refresh to see progress</li>
            <li>
              Imports cannot be partially undone — delete the corpus to roll
              back
            </li>
          </ul>
        </AlertBody>
      </AlertBox>

      <AlertBox $variant="info">
        <Info />
        <AlertBody>
          <AlertTitle>Supported Format</AlertTitle>
          <p>
            Upload a ZIP produced by the OpenContracts corpus export feature.
          </p>
        </AlertBody>
      </AlertBox>
    </div>
  );

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
                  ? "Drop your corpus ZIP here"
                  : "Drag & drop a corpus export ZIP here"}
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

  const renderProgressStep = () => (
    <ProgressContent>
      <SpinnerIcon>
        <Loader />
      </SpinnerIcon>
      <h3>Importing Corpus...</h3>
      <p>This may take a few moments depending on the size of your ZIP file.</p>
      <UploadProgress $percent={uploadProgress} />
      <ProgressLabel>{Math.round(uploadProgress)}%</ProgressLabel>
    </ProgressContent>
  );

  const getSubtitle = (current: ImportStep): string => {
    switch (current) {
      case "confirm":
        return "Review import details before proceeding";
      case "upload":
        return "Select a corpus export ZIP to import";
      case "progress":
        return "Processing your import...";
    }
  };

  if (!visible) return null;

  return (
    <StyledModalWrapper>
      <Modal open={visible} onClose={handleClose} size="md">
        <ModalHeader
          title={
            <>
              <HeaderIcon>
                <FileArchive />
              </HeaderIcon>
              Import Corpus
            </>
          }
          subtitle={getSubtitle(step)}
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
      </Modal>
    </StyledModalWrapper>
  );
};
