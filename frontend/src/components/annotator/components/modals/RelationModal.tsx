import { useState } from "react";
import { Transfer as SemanticTransfer } from "../../../widgets/data-display/Transfer";
import { Modal, Button, Label, Icon } from "semantic-ui-react";
import { RelationGroup } from "../../types/annotations";
import { AnnotationLabelType } from "../../../../types/graphql-api";
import styled from "styled-components";
import { useCreateRelationship } from "../../hooks/AnnotationHooks";
import { useCorpusState } from "../../context/CorpusAtom";

interface RelationModalProps {
  visible: boolean;
  source: string[];
  label: AnnotationLabelType;
  onClose?: () => void;
}

/* ------------------------------------------------------------------ */
/*     NEW  —  theme-aware label                                      */
/* ------------------------------------------------------------------ */
const RelationLabel = styled(Label)<{ $selected: boolean }>`
  &&& {
    cursor: pointer;
    background-color: ${(props): string =>
      props.$selected ? props.theme.color.G6 : props.theme.color.N6};
    color: ${(props): string =>
      props.$selected ? props.theme.color.N1 : props.theme.color.N10};
  }
`;

export const RelationModal = ({
  visible,
  source,
  label,
  onClose,
}: RelationModalProps): JSX.Element => {
  const [targetKeys, setTargetKeys] = useState<string[]>([]);
  const createRelationship = useCreateRelationship();
  const { relationLabels } = useCorpusState();
  const transferSource = source.map((a) => ({ key: a, annotation: a }));

  const handleOk = async () => {
    const sourceIds = source
      .filter((s) => !targetKeys.some((k) => k === s))
      .map((s) => s);

    // Create the relation using the hook
    await createRelationship(new RelationGroup(sourceIds, targetKeys, label));

    // Reset state
    setTargetKeys([]);
    onClose?.();
  };

  const handleCancel = () => {
    // Reset state
    setTargetKeys([]);
    onClose?.();
  };

  return (
    <Modal
      header="Annotate Relations"
      style={{ width: "800px" }}
      open={visible}
    >
      <Modal.Header>
        <h5>Choose a Relation</h5>
      </Modal.Header>
      <Modal.Content>
        {relationLabels.map((relation) => (
          <RelationLabel
            key={relation.text}
            $selected={relation.id === label.id}
            onClick={() => {
              /* Label selection is read-only here — the active label is
                 managed by the parent annotator and would need to be lifted
                 into shared state to allow changing it from this modal. */
            }}
          >
            <Icon name={relation.icon ?? "tag"} />
            {relation.text}
          </RelationLabel>
        ))}
        <Divider />
        <TransferContainer>
          <SemanticTransfer
            dataSource={transferSource}
            targetKeys={targetKeys}
            onChange={setTargetKeys}
          />
        </TransferContainer>
      </Modal.Content>
      <Modal.Actions>
        <Button color="green" onClick={handleOk}>
          Save Change
        </Button>
        <Button color="black" onClick={handleCancel}>
          Cancel
        </Button>
      </Modal.Actions>
    </Modal>
  );
};

/* ----------------------- helpers & layout -------------------------- */
const Divider = styled.hr`
  border: none;
  border-top: 1px solid ${({ theme }) => theme.color.N4};
  margin: ${({ theme }) => `${theme.spacing.sm} 0`};
`;

const TransferContainer = styled.div`
  padding: ${({ theme }) => theme.spacing.sm};
  display: flex;
  justify-content: center;
`;
