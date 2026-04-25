import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";

/**
 * Helper to build a relationship label suitable for injecting into
 * corpusState.relationLabels.
 */
export const buildRelationLabel = (
  id: string,
  text: string,
  overrides: Partial<AnnotationLabelType> = {}
): AnnotationLabelType =>
  ({
    id,
    text,
    description: `${text} description`,
    color: "#3B82F6",
    icon: null,
    analyzer: null,
    labelType: LabelType.RelationshipLabel,
    __typename: "AnnotationLabelType",
    ...overrides,
  } as AnnotationLabelType);
