import React, { useEffect } from "react";
import { Provider as JotaiProvider } from "jotai";
import { useSetAtom } from "jotai";
import { FloatingDocumentControls } from "../src/components/knowledge_base/document/FloatingDocumentControls";
import { PermissionTypes } from "../src/components/types";
import {
  showAnnotationBoundingBoxesAtom,
  showStructuralAnnotationsAtom,
  showSelectedAnnotationOnlyAtom,
} from "../src/components/annotator/context/UISettingsAtom";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
interface FloatingDocumentControlsTestWrapperProps {
  visible?: boolean;
  onAnalysesClick?: () => void;
  onExtractsClick?: () => void;
  analysesOpen?: boolean;
  extractsOpen?: boolean;
  panelOffset?: number;
  readOnly?: boolean;
  // Test configuration props
  showBoundingBoxes?: boolean;
  showStructural?: boolean;
  showSelectedOnly?: boolean;
  corpusPermissions?: PermissionTypes[];
}

// Inner component that sets up the atom states
const TestSetup: React.FC<{
  showBoundingBoxes: boolean;
  showStructural: boolean;
  showSelectedOnly: boolean;
  corpusPermissions: PermissionTypes[];
  children: React.ReactNode;
}> = ({
  showBoundingBoxes,
  showStructural,
  showSelectedOnly,
  corpusPermissions,
  children,
}) => {
  const setShowBoundingBoxes = useSetAtom(showAnnotationBoundingBoxesAtom);
  const setShowStructural = useSetAtom(showStructuralAnnotationsAtom);
  const setShowSelectedOnly = useSetAtom(showSelectedAnnotationOnlyAtom);
  const setCorpusState = useSetAtom(corpusStateAtom);

  useEffect(() => {
    // Set UI settings
    setShowBoundingBoxes(showBoundingBoxes);
    setShowStructural(showStructural);
    setShowSelectedOnly(showSelectedOnly);

    // Set corpus state with permissions
    setCorpusState({
      selectedCorpus: {
        id: "test-corpus",
        title: "Test Corpus",
        description: "Test corpus description",
        myPermissions: corpusPermissions,
        allowComments: true,
        // Add any other required fields for CorpusType
      } as any,
      myPermissions: corpusPermissions,
      spanLabels: [],
      humanSpanLabels: [],
      relationLabels: [],
      docTypeLabels: [],
      humanTokenLabels: [],
      allowComments: true,
      isLoading: false,
    });
  }, [showBoundingBoxes, showStructural, showSelectedOnly, corpusPermissions]);

  return <>{children}</>;
};

export const FloatingDocumentControlsTestWrapper: React.FC<
  FloatingDocumentControlsTestWrapperProps
> = ({
  visible = true,
  onAnalysesClick,
  onExtractsClick,
  analysesOpen = false,
  extractsOpen = false,
  panelOffset = 0,
  readOnly = false,
  showBoundingBoxes = false,
  showStructural = false,
  showSelectedOnly = false,
  corpusPermissions = [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
}) => {
  // No mocking needed here

  return (
    <JotaiProvider>
      <TestSetup
        showBoundingBoxes={showBoundingBoxes}
        showStructural={showStructural}
        showSelectedOnly={showSelectedOnly}
        corpusPermissions={corpusPermissions}
      >
        <div
          style={{
            width: "100vw",
            height: "100vh",
            position: "relative",
            background: "#f5f5f5",
          }}
        >
          <FloatingDocumentControls
            visible={visible}
            onAnalysesClick={onAnalysesClick}
            onExtractsClick={onExtractsClick}
            analysesOpen={analysesOpen}
            extractsOpen={extractsOpen}
            panelOffset={panelOffset}
            readOnly={readOnly}
          />
        </div>
      </TestSetup>
    </JotaiProvider>
  );
};
