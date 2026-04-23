import React from "react";
import { Provider as JotaiProvider, useSetAtom } from "jotai";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { RelationshipActionModal } from "../src/components/knowledge_base/document/unified_feed/RelationshipActionModal";
import { RelationGroup } from "../src/components/annotator/types/annotations";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { AnnotationLabelType } from "../src/types/graphql-api";

const CorpusSetupInner: React.FC<{
  enabled: boolean;
  hasLabelset: boolean;
  relationLabels: AnnotationLabelType[];
  children: React.ReactNode;
}> = ({ enabled, hasLabelset, relationLabels, children }) => {
  const setCorpusState = useSetAtom(corpusStateAtom);
  React.useEffect(() => {
    if (!enabled) return;
    setCorpusState((prev) => ({
      ...prev,
      selectedCorpus: {
        id: "corpus-1",
        title: "Test Corpus",
        labelSet: hasLabelset
          ? ({ id: "labelset-1", title: "Test Labelset" } as any)
          : null,
      } as any,
      relationLabels,
    }));
  }, [enabled, hasLabelset, relationLabels, setCorpusState]);
  return <>{children}</>;
};

export const RelationshipActionModalTestWrapper: React.FC<{
  open?: boolean;
  mocks?: MockedResponse[];
  selectedAnnotationIds?: string[];
  existingRelationships?: RelationGroup[];
  annotations?: Array<{ id: string; rawText?: string }>;
  withCorpus?: boolean;
  hasLabelset?: boolean;
  relationLabels?: AnnotationLabelType[];
  onAddToExisting?: (
    relationshipId: string,
    role: "source" | "target"
  ) => Promise<void>;
  onCreate?: (
    labelId: string,
    sourceIds: string[],
    targetIds: string[]
  ) => Promise<void>;
  onClose?: () => void;
  corpusId?: string;
}> = ({
  open = true,
  mocks = [],
  selectedAnnotationIds = ["ann-1", "ann-2"],
  existingRelationships = [],
  annotations = [
    { id: "ann-1", rawText: "First annotation text" },
    { id: "ann-2", rawText: "Second annotation text" },
  ],
  withCorpus = false,
  hasLabelset = false,
  relationLabels = [],
  onAddToExisting = async () => {},
  onCreate = async () => {},
  onClose = () => {},
  corpusId = "corpus-1",
}) => (
  <JotaiProvider>
    <MockedProvider mocks={mocks} addTypename={false}>
      <CorpusSetupInner
        enabled={withCorpus}
        hasLabelset={hasLabelset}
        relationLabels={relationLabels}
      >
        <RelationshipActionModal
          open={open}
          onClose={onClose}
          selectedAnnotationIds={selectedAnnotationIds}
          existingRelationships={existingRelationships}
          corpusId={corpusId}
          documentId="doc-1"
          annotations={annotations}
          onAddToExisting={onAddToExisting}
          onCreate={onCreate}
        />
      </CorpusSetupInner>
    </MockedProvider>
  </JotaiProvider>
);
