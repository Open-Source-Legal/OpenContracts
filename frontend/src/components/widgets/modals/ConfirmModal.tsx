import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { X, Check, AlertCircle } from "lucide-react";

interface ConfirmModalProps {
  message: string;
  visible: boolean;
  /** Called when the user clicks "Yes". Must NOT close the modal — toggleModal handles that. */
  yesAction: () => void;
  /** Called when the user clicks "No". Must NOT close the modal — toggleModal handles that. */
  noAction: () => void;
  /** Closes the modal. Called automatically after yesAction/noAction and on overlay/escape close. */
  toggleModal: () => void;
  /** Variant for the confirm button. Defaults to "danger" for destructive actions. */
  confirmVariant?: "primary" | "secondary" | "danger" | "ghost";
  /** Label for the confirm button. Defaults to "Yes". */
  confirmLabel?: string;
  /** Label for the cancel button. Defaults to "No". */
  cancelLabel?: string;
  /**
   * In-flight state for an async confirm action. When this prop is supplied
   * (defined), the modal switches to a *caller-controlled* close: clicking
   * "Yes" fires `yesAction` but does NOT auto-close, so the spinner stays
   * visible until the caller closes via `toggleModal` once the work settles.
   * While truthy, both buttons and overlay/escape dismissal are disabled.
   * Omitting the prop preserves the original auto-close-on-Yes behavior.
   */
  confirmLoading?: boolean;
}
export function ConfirmModal({
  message,
  visible,
  yesAction,
  noAction,
  toggleModal,
  confirmVariant = "danger",
  confirmLabel = "Yes",
  cancelLabel = "No",
  confirmLoading,
}: ConfirmModalProps) {
  // Opting into the controlled-loading flow means the caller closes the modal
  // itself after the async action settles, so "Yes" must not auto-close.
  const controlledLoading = confirmLoading !== undefined;

  const onYesClick = () => {
    yesAction();
    // Gate on `controlledLoading` (was the prop supplied at all?), NOT
    // `confirmLoading`'s truthiness like `onClose` below: once a caller opts
    // in, "Yes" must hand off close to them even on the first click while
    // `confirmLoading` is still false. ESC/overlay (`onClose`) instead gate on
    // the truthy value so the dialog can still be dismissed when idle.
    if (!controlledLoading) toggleModal();
  };

  const onNoClick = () => {
    noAction();
    toggleModal();
  };

  return (
    <Modal
      open={visible}
      onClose={() => {
        if (!confirmLoading) toggleModal();
      }}
      size="sm"
    >
      <ModalHeader
        title={
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <AlertCircle size={20} />
            ARE YOU SURE?
          </span>
        }
        onClose={() => {
          if (!confirmLoading) toggleModal();
        }}
      />
      <ModalBody>
        <p>{message}</p>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onClick={() => onNoClick()}
          leftIcon={<X size={16} />}
          disabled={confirmLoading}
        >
          {cancelLabel}
        </Button>
        <Button
          variant={confirmVariant}
          onClick={() => onYesClick()}
          leftIcon={<Check size={16} />}
          loading={confirmLoading}
          disabled={confirmLoading}
        >
          {confirmLabel}
        </Button>
      </ModalFooter>
    </Modal>
  );
}
