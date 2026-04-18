import React from "react";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { RelationItem } from "../src/components/annotator/sidebar/RelationItem";
import {
  RelationGroup,
  ServerTokenAnnotation,
} from "../src/components/annotator/types/annotations";
import { PermissionTypes } from "../src/components/types";
import type { AnnotationLabelType } from "../src/types/graphql-api";

const label: AnnotationLabelType = {
  id: "rel-label-1",
  text: "contracts_with",
  color: "#2ecc71",
  description: "Relation label",
  labelType: "RELATIONSHIP_LABEL" as any,
  icon: "link" as any,
  readonly: false,
};

const spanLabel: AnnotationLabelType = {
  id: "span-label-1",
  text: "Party",
  color: "#3b82f6",
  description: "Party span",
  labelType: "SPAN_LABEL" as any,
  icon: "tag" as any,
  readonly: false,
};

const minimalJson = {
  0: {
    bounds: { top: 0, bottom: 10, left: 0, right: 10 },
    rawText: "Alice",
    tokensJsons: [],
  },
};

const makeAnnot = (id: string, rawText: string): ServerTokenAnnotation =>
  new ServerTokenAnnotation(
    0,
    spanLabel,
    rawText,
    false,
    minimalJson as any,
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    id
  );

export interface RelationItemTestWrapperProps {
  readOnly?: boolean;
  selected?: boolean;
  structural?: boolean;
  onSelectRelation?: () => void;
  onSelectAnnotation?: (id: string) => void;
  onDeleteRelation?: (id: string) => void;
  onRemoveAnnotationFromRelation?: (aid: string, rid: string) => void;
}

export const RelationItemTestWrapper: React.FC<
  RelationItemTestWrapperProps
> = ({
  readOnly = false,
  selected = false,
  structural = false,
  onSelectRelation = () => {},
  onSelectAnnotation = () => {},
  onDeleteRelation = () => {},
  onRemoveAnnotationFromRelation = () => {},
}) => {
  const source = makeAnnot("src-1", "Acme Corp");
  const target = makeAnnot("tgt-1", "Beta LLC");
  const relation = new RelationGroup(
    ["src-1"],
    ["tgt-1"],
    label,
    "rel-42",
    structural
  );

  return (
    <JotaiProvider>
      <MemoryRouter>
        <div style={{ padding: 16, maxWidth: 420, background: "#f7f8fa" }}>
          <RelationItem
            relation={relation}
            source_annotations={[source]}
            target_annotations={[target]}
            read_only={readOnly}
            selected={selected}
            onSelectRelation={onSelectRelation}
            onSelectAnnotation={onSelectAnnotation}
            onDeleteRelation={onDeleteRelation}
            onRemoveAnnotationFromRelation={onRemoveAnnotationFromRelation}
          />
        </div>
      </MemoryRouter>
    </JotaiProvider>
  );
};
