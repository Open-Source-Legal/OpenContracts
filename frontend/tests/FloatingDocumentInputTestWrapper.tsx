import React, { useEffect } from "react";
import { Provider as JotaiProvider } from "jotai";
import { useSetAtom } from "jotai";
import { FloatingDocumentInput } from "../src/components/knowledge_base/document/FloatingDocumentInput";
import {
  searchTextAtom,
  textSearchStateAtom,
} from "../src/components/annotator/context/DocumentAtom";
// No need to import ref atoms - they are managed internally

interface FloatingDocumentInputTestWrapperProps {
  visible?: boolean;
  onChatSubmit?: (message: string) => void;
  onToggleChat?: () => void;
  panelOffset?: number;
  fixed?: boolean;
  readOnly?: boolean;
  // Test configuration props
  initialSearchText?: string;
  initialSearchMatches?: any[];
  initialSelectedIndex?: number;
}

// Inner component that sets up the atom states
const TestSetup: React.FC<{
  initialSearchText: string;
  initialSearchMatches: any[];
  initialSelectedIndex: number;
  children: React.ReactNode;
}> = ({
  initialSearchText,
  initialSearchMatches,
  initialSelectedIndex,
  children,
}) => {
  const setSearchText = useSetAtom(searchTextAtom);
  const setTextSearchState = useSetAtom(textSearchStateAtom);
  // Refs are managed internally by the component

  useEffect(() => {
    // Set initial search text
    setSearchText(initialSearchText);

    // Set text search state
    setTextSearchState({
      textSearchMatches: initialSearchMatches,
      selectedTextSearchMatchIndex: initialSelectedIndex,
    });

    // No need to initialize refs
  }, [initialSearchText, initialSearchMatches, initialSelectedIndex]);

  return <>{children}</>;
};

export const FloatingDocumentInputTestWrapper: React.FC<
  FloatingDocumentInputTestWrapperProps
> = ({
  visible = true,
  onChatSubmit,
  onToggleChat,
  panelOffset = 0,
  fixed = true,
  readOnly = false,
  initialSearchText = "",
  initialSearchMatches = [],
  initialSelectedIndex = 0,
}) => {
  console.log(
    "[FloatingDocumentInputTestWrapper] Rendering with visible:",
    visible
  );

  return (
    <JotaiProvider>
      <TestSetup
        initialSearchText={initialSearchText}
        initialSearchMatches={initialSearchMatches}
        initialSelectedIndex={initialSelectedIndex}
      >
        <div
          style={{
            width: "100vw",
            height: "100vh",
            position: "relative",
            background: "#f5f5f5",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          data-testid="test-wrapper-container"
        >
          <div data-testid="float-input-container">
            <FloatingDocumentInput
              visible={visible}
              onChatSubmit={onChatSubmit}
              onToggleChat={onToggleChat}
              panelOffset={panelOffset}
              fixed={fixed}
              readOnly={readOnly}
            />
          </div>
        </div>
      </TestSetup>
    </JotaiProvider>
  );
};
