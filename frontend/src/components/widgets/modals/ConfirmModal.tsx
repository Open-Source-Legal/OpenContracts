import { Modal, Header } from "semantic-ui-react";
import { X, AlertCircle, Check } from "lucide-react";
import { Button, IconButton } from "@os-legal/ui";
import styled from "styled-components";

const CloseButtonWrapper = styled.div`
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  z-index: 1;
`;

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
      <CloseButtonWrapper>
        <IconButton
          variant="ghost"
          size="sm"
          aria-label="Close modal"
          onClick={() => toggleModal()}
          style={{ color: "white" }}
        >
          <X size={16} />
        </IconButton>
      </CloseButtonWrapper>
      <Header
        icon={<AlertCircle size={32} style={{ marginRight: "0.5rem" }} />}
        content="ARE YOU SURE?"
      />
      <Modal.Content>
        <p>{message}</p>
      </Modal.Content>
      <Modal.Actions>
        <Button
          variant="danger"
          onClick={() => onNoClick()}
          leftIcon={<X size={16} />}
        >
          No
        </Button>
        <Button
          variant="primary"
          onClick={() => onYesClick()}
          leftIcon={<Check size={16} />}
        >
          Yes
        </Button>
      </Modal.Actions>
    </Modal>
  );
}
