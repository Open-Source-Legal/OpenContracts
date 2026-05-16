import { SyntheticEvent, useEffect, useState } from "react";

import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";

import { isSafeUrl } from "../../utils/urlAnnotation";

interface CreateUrlAnnotationModalProps {
  visible: boolean;
  /** Text the user selected; shown read-only for context. */
  selectedText: string;
  onCancel: () => void;
  /** Called with the trimmed URL when the user confirms. */
  onConfirm: (url: string) => void;
  /** Initial value, used by the edit-URL flow. */
  initialUrl?: string;
}

/**
 * Small modal that prompts the user for a target URL when turning a
 * selection into an OC_URL link annotation. Validation reuses ``isSafeUrl``
 * from ``urlAnnotation.ts`` — the same allow-list (http(s) absolute or
 * site-relative ``/...``) used by the renderer click-handler and the
 * backend ``validate_link_url`` helper, so the three checks cannot drift.
 */
export const CreateUrlAnnotationModal = ({
  visible,
  selectedText,
  onCancel,
  onConfirm,
  initialUrl = "",
}: CreateUrlAnnotationModalProps) => {
  const [url, setUrl] = useState(initialUrl);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      setUrl(initialUrl);
      setError(null);
    }
  }, [visible, initialUrl]);

  const handleConfirm = (event: SyntheticEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const trimmed = url.trim();
    if (!trimmed) {
      setError("URL is required.");
      return;
    }
    if (!isSafeUrl(trimmed)) {
      setError(
        "URL must start with http://, https://, or '/' (site-relative path)."
      );
      return;
    }
    onConfirm(trimmed);
  };

  return (
    <Modal open={visible} onClose={onCancel}>
      <ModalHeader>{initialUrl ? "Edit link target" : "Add link"}</ModalHeader>
      <ModalBody>
        <div
          onMouseDown={(e) => e.stopPropagation()}
          style={{ display: "flex", flexDirection: "column", gap: 12 }}
        >
          {selectedText && (
            <div
              style={{
                fontSize: 12,
                color: "#6b7280",
                background: "#f9fafb",
                padding: "8px 10px",
                borderRadius: 4,
                maxHeight: 80,
                overflow: "auto",
              }}
            >
              <span style={{ fontWeight: 600 }}>Selected text:</span>{" "}
              {selectedText}
            </div>
          )}
          <label
            htmlFor="oc-url-input"
            style={{ fontSize: 13, fontWeight: 500 }}
          >
            Target URL
          </label>
          <input
            id="oc-url-input"
            type="url"
            value={url}
            onChange={(e) => {
              setUrl(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                handleConfirm(e);
              }
            }}
            placeholder="https://example.com or /relative/path"
            autoFocus
            style={{
              padding: "8px 10px",
              border: error ? "1px solid #dc2626" : "1px solid #d1d5db",
              borderRadius: 4,
              fontSize: 14,
            }}
          />
          {error && (
            <div style={{ fontSize: 12, color: "#dc2626" }}>{error}</div>
          )}
        </div>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onMouseDown={(e: React.MouseEvent) => e.stopPropagation()}
          onClick={(e: SyntheticEvent) => {
            e.stopPropagation();
            onCancel();
          }}
        >
          Cancel
        </Button>
        <Button
          variant="primary"
          onMouseDown={(e: React.MouseEvent) => e.stopPropagation()}
          onClick={handleConfirm}
        >
          {initialUrl ? "Save link" : "Create link"}
        </Button>
      </ModalFooter>
    </Modal>
  );
};
