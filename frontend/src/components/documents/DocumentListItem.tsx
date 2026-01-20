import { CheckCircle, XCircle, Loader2, FileText, Trash2 } from "lucide-react";
import { LoadingOverlay } from "../common/LoadingOverlay";

import {
  NOT_STARTED,
  UPLOADING,
  SUCCESS,
  FAILED,
  FileDetailsProps,
} from "../widgets/modals/DocumentUploadModal";
import {
  FileListItem,
  FileItemContent,
  FileItemIcon,
  FileItemDetails,
  FileItemActions,
  DeleteButton,
} from "../widgets/modals/UploadModalStyles";

interface ContractListItemProps {
  document: FileDetailsProps;
  status: string;
  selected: boolean;
  onRemove: () => void;
  onSelect: () => void;
}

export const ContractListItem = ({
  document,
  status,
  selected,
  onRemove,
  onSelect,
}: ContractListItemProps) => {
  const getStatusIcon = () => {
    switch (status) {
      case SUCCESS:
        return <CheckCircle size={16} />;
      case FAILED:
        return <XCircle size={16} />;
      case UPLOADING:
        return (
          <Loader2 size={16} style={{ animation: "spin 1s linear infinite" }} />
        );
      default:
        return <FileText size={16} />;
    }
  };

  const getStatusText = () => {
    switch (status) {
      case SUCCESS:
        return "Uploaded successfully";
      case FAILED:
        return "Upload failed";
      case UPLOADING:
        return "Uploading...";
      default:
        return "Ready to upload";
    }
  };

  const handleRemoveClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onRemove();
  };

  return (
    <FileListItem $selected={selected} $status={status} onClick={onSelect}>
      <LoadingOverlay
        active={status === UPLOADING}
        inverted
        content="Uploading..."
      />
      <FileItemContent>
        <FileItemIcon $status={status}>{getStatusIcon()}</FileItemIcon>
        <FileItemDetails>
          <div className="file-name">
            {document?.title || "Untitled Document"}
          </div>
          <div
            className={`file-status ${
              status === FAILED ? "error" : status === SUCCESS ? "success" : ""
            }`}
          >
            {getStatusText()}
          </div>
        </FileItemDetails>
      </FileItemContent>
      {status === NOT_STARTED && (
        <FileItemActions>
          <DeleteButton onClick={handleRemoveClick} aria-label="Remove file">
            <Trash2 size={14} />
          </DeleteButton>
        </FileItemActions>
      )}
    </FileListItem>
  );
};
