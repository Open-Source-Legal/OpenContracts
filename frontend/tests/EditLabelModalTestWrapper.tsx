import React from "react";
import { Provider as JotaiProvider } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import { EditLabelModal } from "../src/components/annotator/components/modals/EditLabelModal";
import {
  corpusStateAtom,
  CorpusState,
} from "../src/components/annotator/context/CorpusAtom";
import { ServerTokenAnnotation } from "../src/components/annotator/types/annotations";
import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";

const mockLabels: AnnotationLabelType[] = [
  {
    id: "label-1",
    text: "Important",
    color: "#ff0000",
    description: "Important text",
    icon: undefined,
    analyzer: null,
    labelType: LabelType.SpanLabel,
    __typename: "AnnotationLabelType",
  },
  {
    id: "label-2",
    text: "Reference",
    color: "#0000ff",
    description: "Reference text",
    icon: undefined,
    analyzer: null,
    labelType: LabelType.SpanLabel,
    __typename: "AnnotationLabelType",
  },
];

const mockAnnotation = new ServerTokenAnnotation(
  0,
  mockLabels[0],
  "Test annotation text",
  false,
  {
    1: {
      bounds: { top: 0, bottom: 20, left: 0, right: 100 },
      tokensJsons: [],
      rawText: "Test annotation text",
    },
  },
  [PermissionTypes.CAN_READ],
  false,
  false,
  false,
  "ann-1"
);

const defaultCorpusState: CorpusState = {
  selectedCorpus: null,
  myPermissions: [],
  spanLabels: mockLabels,
  humanSpanLabels: mockLabels,
  relationLabels: [],
  docTypeLabels: [],
  humanTokenLabels: [],
  allowComments: true,
  isLoading: false,
};

function HydrateAtoms({ children }: { children: React.ReactNode }) {
  useHydrateAtoms([[corpusStateAtom, defaultCorpusState]] as any);
  return <>{children}</>;
}

interface WrapperProps {
  visible?: boolean;
  onHide?: () => void;
}

export const EditLabelModalTestWrapper: React.FC<WrapperProps> = ({
  visible = true,
  onHide = () => {},
}) => (
  <JotaiProvider>
    <HydrateAtoms>
      <EditLabelModal
        annotation={mockAnnotation}
        visible={visible}
        onHide={onHide}
      />
    </HydrateAtoms>
  </JotaiProvider>
);
