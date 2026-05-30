import React, { useCallback, useMemo, useRef } from "react";
import { useDropzone, FileRejection, DropEvent, Accept } from "react-dropzone";
import { Upload, FileArchive, FileText, RefreshCw } from "lucide-react";
import { Button } from "@os-legal/ui";
import { DropZone, DropZoneIcon, DropZoneText } from "../UploadModalStyles";
import { formatFileSize } from "../../../../../utils/files";
import { UPLOAD } from "../../../../../assets/configurations/constants";

export type UploadMode = "single" | "bulk";

export interface AcceptedFileType {
  mimetype: string;
  extension: string;
  label: string;
}

interface FileDropZoneProps {
  mode: UploadMode;
  disabled?: boolean;
  /** For bulk mode, the selected ZIP file */
  selectedFile?: File | null;
  /** For single mode, whether files have been added */
  hasFiles?: boolean;
  /** Accepted file types for single mode (from backend). Falls back to PDF-only. */
  acceptedFileTypes?: AcceptedFileType[];
  /**
   * Maximum accepted file size in bytes. Defaults to the single-document
   * cap; callers pass the ZIP cap for bulk mode. Files above the cap are
   * still chunked on upload, but the dropzone bounds what a user can pick
   * so the backend's per-flow ceiling isn't exceeded.
   */
  maxSizeBytes?: number;
  /** Human-readable form of ``maxSizeBytes`` (e.g. "2GB"). */
  maxSizeDisplay?: string;
  onFilesSelected: (files: File[]) => void;
  onFileRejected?: (rejections: FileRejection[]) => void;
}

/**
 * FileDropZone component for drag-and-drop file upload.
 * Supports two modes:
 * - single: Accept multiple PDF files
 * - bulk: Accept a single ZIP file
 */
export const FileDropZone: React.FC<FileDropZoneProps> = ({
  mode,
  disabled = false,
  selectedFile,
  hasFiles = false,
  acceptedFileTypes,
  maxSizeBytes = UPLOAD.MAX_FILE_SIZE_BYTES,
  maxSizeDisplay = UPLOAD.MAX_FILE_SIZE_DISPLAY,
  onFilesSelected,
  onFileRejected,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const ACCEPT_ZIP: Accept = { "application/zip": [".zip"] };

  // Build accept config from backend-provided file types, or fall back to PDF
  const singleAcceptConfig: Accept = useMemo(() => {
    if (!acceptedFileTypes || acceptedFileTypes.length === 0) {
      return { "application/pdf": [".pdf"] };
    }
    const accept: Accept = {};
    for (const ft of acceptedFileTypes) {
      accept[ft.mimetype] = [`.${ft.extension}`];
    }
    return accept;
  }, [acceptedFileTypes]);

  const acceptConfig = mode === "bulk" ? ACCEPT_ZIP : singleAcceptConfig;

  // Build human-readable label for accepted types (e.g. "PDF, DOCX, TXT")
  const acceptedLabels = useMemo(() => {
    if (!acceptedFileTypes || acceptedFileTypes.length === 0) return "PDF";
    return acceptedFileTypes.map((ft) => ft.label).join(", ");
  }, [acceptedFileTypes]);

  // Build comma-separated accept string for <input> (e.g. ".pdf,.docx,.txt")
  const inputAcceptString = useMemo(() => {
    if (!acceptedFileTypes || acceptedFileTypes.length === 0) {
      return ".pdf,application/pdf";
    }
    return acceptedFileTypes
      .flatMap((ft) => [`.${ft.extension}`, ft.mimetype])
      .join(",");
  }, [acceptedFileTypes]);

  const onDrop = useCallback(
    (acceptedFiles: File[], rejections: FileRejection[], event: DropEvent) => {
      if (acceptedFiles.length > 0) {
        onFilesSelected(acceptedFiles);
      }
      if (rejections.length > 0 && onFileRejected) {
        onFileRejected(rejections);
      }
    },
    [onFilesSelected, onFileRejected]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: acceptConfig,
    multiple: mode === "single",
    disabled: disabled || (mode === "single" && hasFiles),
    maxSize: maxSizeBytes,
  });

  const handleBrowseClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!disabled && fileInputRef.current) {
        fileInputRef.current.click();
      }
    },
    [disabled]
  );

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files || []);
      if (files.length > 0) {
        // Validate file sizes for manual input (dropzone handles this for drag-drop)
        const validFiles: File[] = [];
        const oversizedFiles: FileRejection[] = [];

        for (const file of files) {
          if (file.size > maxSizeBytes) {
            oversizedFiles.push({
              file,
              errors: [
                {
                  code: "file-too-large",
                  message: `File exceeds ${maxSizeDisplay} limit`,
                },
              ],
            });
          } else {
            validFiles.push(file);
          }
        }

        if (validFiles.length > 0) {
          onFilesSelected(validFiles);
        }
        if (oversizedFiles.length > 0 && onFileRejected) {
          onFileRejected(oversizedFiles);
        }
      }
      // Reset input to allow selecting the same file again
      if (e.target) {
        e.target.value = "";
      }
    },
    [onFilesSelected, onFileRejected]
  );

  // Render for bulk mode with a file selected
  if (mode === "bulk" && selectedFile) {
    return (
      <DropZone
        $hasFiles={true}
        onClick={handleBrowseClick}
        data-testid="file-dropzone"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip,application/zip"
          onChange={handleFileChange}
          disabled={disabled}
          style={{ display: "none" }}
          aria-label="Select ZIP file for bulk upload"
        />
        <DropZoneIcon>
          <FileArchive />
        </DropZoneIcon>
        <DropZoneText>
          <div className="primary-text">{selectedFile.name}</div>
          <div className="secondary-text">
            {formatFileSize(selectedFile.size)}
          </div>
        </DropZoneText>
        <Button
          variant="secondary"
          size="md"
          onClick={handleBrowseClick}
          disabled={disabled}
          style={{ marginTop: "var(--oc-spacing-md)" }}
        >
          <RefreshCw style={{ width: 16, height: 16, marginRight: 8 }} />
          Change File
        </Button>
      </DropZone>
    );
  }

  // Render empty drop zone
  return (
    <DropZone
      {...getRootProps()}
      $isDragActive={isDragActive}
      $hasFiles={false}
      data-testid="file-dropzone"
    >
      <input {...getInputProps()} />
      <input
        ref={fileInputRef}
        type="file"
        accept={mode === "bulk" ? ".zip,application/zip" : inputAcceptString}
        multiple={mode === "single"}
        onChange={handleFileChange}
        disabled={disabled}
        style={{ display: "none" }}
        aria-label={
          mode === "bulk"
            ? "Select ZIP file for bulk upload"
            : `Select ${acceptedLabels} files`
        }
      />
      <DropZoneIcon>
        {mode === "bulk" ? <FileArchive /> : <Upload />}
      </DropZoneIcon>
      <DropZoneText>
        <div className="primary-text">
          {isDragActive
            ? mode === "bulk"
              ? "Drop your ZIP file here..."
              : "Drop your files here..."
            : mode === "bulk"
            ? "Click to select a ZIP file"
            : `Drag & drop ${acceptedLabels} files here`}
        </div>
        <div className="secondary-text">
          {mode === "bulk"
            ? `ZIP should contain documents (max ${maxSizeDisplay})`
            : `Supported: ${acceptedLabels} · Max ${maxSizeDisplay} per file`}
        </div>
      </DropZoneText>
      <Button
        variant="primary"
        size="md"
        onClick={handleBrowseClick}
        disabled={disabled}
        style={{ marginTop: "var(--oc-spacing-md)" }}
      >
        <FileText style={{ width: 16, height: 16, marginRight: 8 }} />
        Browse Files
      </Button>
    </DropZone>
  );
};

export default FileDropZone;
