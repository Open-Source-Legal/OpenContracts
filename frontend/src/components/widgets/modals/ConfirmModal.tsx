import { Label, Modal, Header, Button } from "semantic-ui-react";
import { X, AlertCircle, Check } from "lucide-react";

interface ConfirmModalProps {
  message: string;
  visible: boolean;
  yesAction: (args?: any) => void;
  noAction: (args?: any) => void;
  toggleModal: (args?: any) => void;
}
export function ConfirmModal({
  message,
  visible,
  yesAction,
  noAction,
  toggleModal,
}: ConfirmModalProps) {
  const onYesClick = () => {
    yesAction();
    toggleModal();
  };

  const onNoClick = () => {
    noAction();
    toggleModal();
  };

  return (
    <Modal open={visible} basic size="small">
      <Label
        corner="right"
        color="grey"
        onClick={() => toggleModal()}
        style={{ cursor: "pointer" }}
      >
        <X size={12} />
      </Label>
      <Header
        icon={<AlertCircle size={32} style={{ marginRight: "0.5rem" }} />}
        content="ARE YOU SURE?"
      />
      <Modal.Content>
        <p>{message}</p>
      </Modal.Content>
      <Modal.Actions>
        <Button basic color="red" inverted onClick={() => onNoClick()}>
          <X size={16} style={{ marginRight: "0.5rem" }} /> No
        </Button>
        <Button color="green" inverted onClick={() => onYesClick()}>
          <Check size={16} style={{ marginRight: "0.5rem" }} /> Yes
        </Button>
      </Modal.Actions>
    </Modal>
  );
}
