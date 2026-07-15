import React from "react";
import { Progress } from "@os-legal/ui";
import styled from "styled-components";
import { FileUploadPackage } from "../hooks/useUploadState";

const ProgressContainer = styled.div`
  margin: var(--oc-spacing-md) 0;

  .progress-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--oc-spacing-xs);
    font-size: var(--oc-font-size-sm);
  }

  .progress-text {
    color: var(--oc-fg-secondary);
  }

  .progress-count {
    color: var(--oc-fg-tertiary);
    font-weight: 500;
  }
`;

interface UploadProgressProps {
  files: FileUploadPackage[];
  /** Actual byte-transfer progress for a single streamed archive. */
  progressPercent?: number;
  /** Overrides the file-count status text when reporting archive transfer. */
  statusText?: string;
}

/**
 * Upload progress bar showing overall progress across all files.
 * Displays number of completed files and percentage.
 */
export const UploadProgress: React.FC<UploadProgressProps> = ({
  files,
  progressPercent,
  statusText,
}) => {
  const completedCount = files.filter(
    (f) => f.status === "success" || f.status === "failed"
  ).length;
  const successCount = files.filter((f) => f.status === "success").length;
  const totalCount = files.length;
  const filePercentage =
    totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const percentage = progressPercent ?? filePercentage;

  const allComplete =
    progressPercent === undefined
      ? completedCount === totalCount
      : progressPercent >= 100;
  const hasFailures = files.some((f) => f.status === "failed");

  return (
    <ProgressContainer>
      <div className="progress-label">
        <span className="progress-text">
          {statusText ||
            (allComplete
              ? hasFailures
                ? "Upload completed with errors"
                : "All files uploaded successfully"
              : "Uploading files...")}
        </span>
        <span className="progress-count">
          {progressPercent === undefined
            ? `${successCount} / ${totalCount} completed (${Math.round(
                percentage
              )}%)`
            : `${Math.round(percentage)}% uploaded`}
        </span>
      </div>
      <Progress
        value={percentage}
        variant={
          allComplete || progressPercent !== undefined
            ? "determinate"
            : "indeterminate"
        }
        size="md"
      />
    </ProgressContainer>
  );
};

export default UploadProgress;
