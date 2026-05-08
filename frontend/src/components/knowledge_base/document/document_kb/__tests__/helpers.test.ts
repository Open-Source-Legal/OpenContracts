import { describe, expect, it } from "vitest";

import { relationToGroup } from "../helpers";
import {
  AnnotationLabelType,
  LabelType,
} from "../../../../../types/graphql-api";

const label: AnnotationLabelType = {
  id: "lbl-1",
  text: "label",
  color: "#000",
  description: "",
  icon: "",
  labelType: LabelType.RelationshipLabel,
};

describe("relationToGroup", () => {
  it("maps source/target edges to id arrays and preserves structural=false default", () => {
    const group = relationToGroup({
      id: "rel-1",
      relationshipLabel: label,
      sourceAnnotations: {
        edges: [{ node: { id: "src-1" } }, { node: { id: "src-2" } }],
      },
      targetAnnotations: { edges: [{ node: { id: "tgt-1" } }] },
    });

    expect(group.id).toBe("rel-1");
    expect(group.sourceIds).toEqual(["src-1", "src-2"]);
    expect(group.targetIds).toEqual(["tgt-1"]);
    expect(group.label).toBe(label);
    expect(group.structural).toBe(false);
  });

  it("propagates structural=true from the wire payload", () => {
    const group = relationToGroup({
      id: "rel-2",
      structural: true,
      relationshipLabel: label,
      sourceAnnotations: { edges: [{ node: { id: "a" } }] },
      targetAnnotations: { edges: [{ node: { id: "b" } }] },
    });

    expect(group.structural).toBe(true);
  });

  it("forces structural=true when forceStructural overrides the payload", () => {
    const group = relationToGroup(
      {
        id: "rel-3",
        structural: false,
        relationshipLabel: label,
        sourceAnnotations: { edges: [{ node: { id: "a" } }] },
        targetAnnotations: { edges: [{ node: { id: "b" } }] },
      },
      true
    );

    expect(group.structural).toBe(true);
  });

  it("filters out edges with null/missing nodes so consumers never see undefined ids", () => {
    const group = relationToGroup({
      id: "rel-4",
      relationshipLabel: label,
      sourceAnnotations: {
        edges: [
          { node: { id: "ok" } },
          null,
          { node: null },
          // edge present but node id missing — exercise the undefined-id filter
          { node: undefined as unknown as { id: string } },
        ],
      },
      targetAnnotations: {
        edges: [null, { node: { id: "tgt" } }],
      },
    });

    expect(group.sourceIds).toEqual(["ok"]);
    expect(group.targetIds).toEqual(["tgt"]);
  });
});
