import React, { useEffect, useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { MockedProvider } from "@apollo/client/testing";
import { Provider as JotaiProvider, createStore } from "jotai";

import DocxAnnotatorWrapper from "../src/components/annotator/components/wrappers/DocxAnnotatorWrapper";
import {
  docTextAtom,
  docxBytesAtom,
  textSearchStateAtom,
} from "../src/components/annotator/context/DocumentAtom";
import { pdfAnnotationsAtom } from "../src/components/annotator/context/AnnotationAtoms";
import {
  activeSpanLabelAtom,
  spanLabelsToViewAtom,
} from "../src/components/annotator/context/AnnotationControlAtoms";
import { chatSourcesAtom } from "../src/components/annotator/context/ChatSourceAtom";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { zoomLevelAtom } from "../src/components/annotator/context/UISettingsAtom";
import {
  PdfAnnotations,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../src/components/annotator/types/annotations";
import {
  showSelectedAnnotationOnly,
  showStructuralAnnotations,
} from "../src/graphql/cache";
import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";
import { PermissionTypes, TextSearchSpanResult } from "../src/components/types";

/**
 * Mounts OpenContracts' DOCX viewer (`DocxAnnotatorWrapper`, which renders
 * `@os-legal/react-contract-annotate`'s `DocxAnnotator`) with its state
 * seeded into the same atoms the knowledge base fills, so the tests run the
 * production bindings.
 *
 * The test DOCX fixture is served at runtime via page.route() in
 * setupDocxFixture() — no Vite ?url import needed.
 */
const TEST_DOCX_URL = "/test-fixtures/test.docx";

const sampleLabels: AnnotationLabelType[] = [
  {
    id: "label-1",
    labelType: LabelType.SpanLabel,
    color: "#FF6B6B",
    description: "Marks important clauses",
    icon: "tag",
    text: "Important Clause",
  },
  {
    id: "label-2",
    labelType: LabelType.SpanLabel,
    color: "#4ECDC4",
    description: "Marks definitions",
    icon: "tag",
    text: "Definition",
  },
];

// Must match Docxodus's text extraction exactly (newlines between paragraphs)
const sampleDocText =
  "Hello World. This is a sample DOCX document for testing.\n" +
  "This paragraph contains an Important Clause that should be annotated.\n" +
  "The Definition section explains key terms used throughout.\n";

const ALL_PERMISSIONS = [
  PermissionTypes.CAN_READ,
  PermissionTypes.CAN_UPDATE,
  PermissionTypes.CAN_REMOVE,
];

const sampleAnnotation1 = new ServerSpanAnnotation(
  0,
  sampleLabels[0],
  "Hello World",
  false,
  { start: 0, end: 11 },
  ALL_PERMISSIONS,
  false,
  false,
  false,
  "ann-1"
);

// "Important Clause" at offset 84-100 in the Docxodus-extracted text
const sampleAnnotation2 = new ServerSpanAnnotation(
  0,
  sampleLabels[1],
  "Important Clause",
  false,
  { start: 84, end: 100 },
  ALL_PERMISSIONS,
  false,
  false,
  false,
  "ann-2"
);

const structuralAnnotation = new ServerSpanAnnotation(
  0,
  sampleLabels[0],
  "The Definition",
  true,
  { start: 118, end: 132 },
  [PermissionTypes.CAN_READ],
  false,
  false,
  false,
  "struct-ann-1"
);

interface ChatSourceHighlight {
  start_index: number;
  end_index: number;
  sourceId: string;
  messageId: string;
}

interface WrapperProps {
  readOnly?: boolean;
  withAnnotations?: boolean;
  /** Provide search results for highlighting in the DOCX body. */
  searchResults?: TextSearchSpanResult[];
  /** Chat sources of one message, which is shown as selected. */
  chatSources?: ChatSourceHighlight[];
  /** Which chat source is currently selected by the user. */
  selectedChatSourceId?: string;
  /** Restrict visible labels. */
  visibleLabels?: AnnotationLabelType[];
  /** Include a structural annotation and show structural annotations. */
  withStructuralAnnotation?: boolean;
  /** Adjust zoom to exercise the zoom branch. */
  zoomLevel?: number;
  /** Receives the annotation the user created. */
  onCreateAnnotation?: (
    annotation: ServerTokenAnnotation | ServerSpanAnnotation
  ) => void;
}

/** A Jotai store holding the viewer's state, the DOCX bytes once fetched. */
function useSeededStore({
  readOnly = true,
  withAnnotations = false,
  searchResults,
  chatSources,
  selectedChatSourceId,
  visibleLabels,
  withStructuralAnnotation = false,
  zoomLevel,
}: WrapperProps) {
  const [store] = useState(() => {
    // The display toggles CentralRouteManager sets from the URL in the app
    // (`selectedOnly` / `structural` absent: off).
    showSelectedAnnotationOnly(false);
    showStructuralAnnotations(withStructuralAnnotation);
    const s = createStore();
    const annotations = [
      ...(withAnnotations ? [sampleAnnotation1, sampleAnnotation2] : []),
      ...(withStructuralAnnotation ? [structuralAnnotation] : []),
    ];
    s.set(docTextAtom, sampleDocText);
    s.set(pdfAnnotationsAtom, new PdfAnnotations(annotations, [], []));
    s.set(textSearchStateAtom, {
      matches: searchResults ?? [],
      selectedIndex: 0,
    });
    if (chatSources?.length) {
      const messageId = chatSources[0].messageId;
      s.set(chatSourcesAtom, {
        messages: [
          {
            messageId,
            content: "",
            timestamp: "",
            sources: chatSources.map((source, index) => ({
              id: source.sourceId,
              page: 0,
              label: String(index + 1),
              label_id: 0,
              annotation_id: 0,
              rawText: sampleDocText.slice(
                source.start_index,
                source.end_index
              ),
              tokensByPage: {},
              boundsByPage: {},
              startIndex: source.start_index,
              endIndex: source.end_index,
              isTextBased: true,
            })),
          },
        ],
        selectedMessageId: messageId,
        selectedSourceIndex: selectedChatSourceId
          ? chatSources.findIndex((c) => c.sourceId === selectedChatSourceId)
          : null,
      });
    }
    s.set(spanLabelsToViewAtom, visibleLabels ?? null);
    if (zoomLevel !== undefined) s.set(zoomLevelAtom, zoomLevel);
    if (!readOnly) {
      s.set(activeSpanLabelAtom, sampleLabels[0]);
      s.set(corpusStateAtom, (prev) => ({
        ...prev,
        myPermissions: ALL_PERMISSIONS,
        humanSpanLabels: sampleLabels,
        spanLabels: sampleLabels,
      }));
    }
    return s;
  });

  useEffect(() => {
    fetch(TEST_DOCX_URL)
      .then((res) => res.arrayBuffer())
      .then((buf) => store.set(docxBytesAtom, new Uint8Array(buf)))
      .catch((err) => console.error("Failed to load test DOCX:", err));
  }, [store]);

  return store;
}

export const DocxAnnotatorTestWrapper: React.FC<WrapperProps> = (props) => {
  const store = useSeededStore(props);
  const { readOnly = true, onCreateAnnotation } = props;

  return (
    <MemoryRouter>
      <MockedProvider mocks={[]} addTypename={false}>
        <JotaiProvider store={store}>
          <div style={{ width: 800, height: 600, padding: 16 }}>
            <DocxAnnotatorWrapper
              readOnly={readOnly}
              createAnnotation={async (annotation) =>
                onCreateAnnotation?.(annotation)
              }
            />
          </div>
        </JotaiProvider>
      </MockedProvider>
    </MemoryRouter>
  );
};

/**
 * An editable viewer that shows the last annotation the user created in a
 * `last-annotation` element (its span in `data-start` / `data-end`).
 */
export const DocxAnnotatorEditableWrapper: React.FC = () => {
  const [last, setLast] = useState<{ start: number; end: number } | null>(null);
  return (
    <>
      <DocxAnnotatorTestWrapper
        readOnly={false}
        onCreateAnnotation={(annotation) => {
          const span = annotation.json as { start: number; end: number };
          setLast({ start: span.start, end: span.end });
        }}
      />
      {last && (
        <div
          data-testid="last-annotation"
          data-start={last.start}
          data-end={last.end}
        />
      )}
    </>
  );
};

export { sampleDocText };
