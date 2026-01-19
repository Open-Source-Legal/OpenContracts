import { Card, Icon as SemanticIcon } from "semantic-ui-react";
import { Ban } from "lucide-react";
import { AnnotationLabelType } from "../../../types/graphql-api";

interface LabelListItemProps {
  label: AnnotationLabelType;
  selected: boolean;
  onSelect: (label: AnnotationLabelType) => void;
}

export const LabelListItem = ({
  label,
  selected,
  onSelect,
}: LabelListItemProps) => {
  return (
    <Card
      key={label.id}
      onClick={() => onSelect(label)}
      style={
        selected
          ? { margin: "5px", backgroundColor: "#e2ffdb" }
          : { margin: "5px" }
      }
    >
      <Card.Content>
        <div style={{ float: "right" }}>
          <SemanticIcon name={label?.icon ? label.icon : "tag"} />
        </div>

        <Card.Header>{label.text}</Card.Header>
        <Card.Meta>
          <div>{label.description}</div>
        </Card.Meta>
        <Card.Description>{label.description}</Card.Description>
      </Card.Content>
    </Card>
  );
};

export const EmptyLabelListItem = () => {
  return (
    <Card fluid key={-1} style={{ margin: "5px" }}>
      <Card.Content>
        <Card.Header>
          <span style={{ float: "right" }}>
            <Ban size={16} />
          </span>
          No Matching Labels
        </Card.Header>
        <Card.Meta>
          <div>N/A</div>
        </Card.Meta>
        <Card.Description>No label matches your search terms.</Card.Description>
      </Card.Content>
    </Card>
  );
};
