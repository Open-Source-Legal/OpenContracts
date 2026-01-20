import { Icon as SemanticIcon } from "semantic-ui-react";
import { Card, CardBody } from "@os-legal/ui";
import styled from "styled-components";
import { Ban } from "lucide-react";
import { AnnotationLabelType } from "../../../types/graphql-api";

const StyledCard = styled(Card)<{ $selected?: boolean }>`
  margin: 5px;
  cursor: pointer;
  background-color: ${(props) => (props.$selected ? "#e2ffdb" : "#fff")};
`;

const FluidCard = styled(Card)`
  width: 100%;
  margin: 5px;
`;

const CardHeader = styled.div`
  font-weight: 600;
  font-size: 1.1rem;
  margin-bottom: 0.25rem;
`;

const CardMeta = styled.div`
  color: #666;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
`;

const CardDescription = styled.div`
  color: #333;
`;

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
    <StyledCard
      key={label.id}
      onClick={() => onSelect(label)}
      $selected={selected}
    >
      <CardBody>
        <div style={{ float: "right" }}>
          <SemanticIcon name={label?.icon ? label.icon : "tag"} />
        </div>

        <CardHeader>{label.text}</CardHeader>
        <CardMeta>
          <div>{label.description}</div>
        </CardMeta>
        <CardDescription>{label.description}</CardDescription>
      </CardBody>
    </StyledCard>
  );
};

export const EmptyLabelListItem = () => {
  return (
    <FluidCard key={-1}>
      <CardBody>
        <CardHeader>
          <span style={{ float: "right" }}>
            <Ban size={16} />
          </span>
          No Matching Labels
        </CardHeader>
        <CardMeta>
          <div>N/A</div>
        </CardMeta>
        <CardDescription>No label matches your search terms.</CardDescription>
      </CardBody>
    </FluidCard>
  );
};
