import React from "react";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import { MockedProvider, type MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";

import { EnhancedLabelSelector } from "../src/components/annotator/labels/EnhancedLabelSelector";
import {
  corpusStateAtom,
  type CorpusState,
} from "../src/components/annotator/context/CorpusAtom";
import { selectedDocumentAtom } from "../src/components/annotator/context/DocumentAtom";
import { pdfAnnotationsAtom } from "../src/components/annotator/context/AnnotationAtoms";
import {
  PdfAnnotations,
  DocTypeAnnotation,
} from "../src/components/annotator/types/annotations";
import {
  AnnotationLabelType,
  LabelType,
  CorpusType,
  LabelSetType,
} from "../src/types/graphql-api";
import { PermissionTypes } from "../src/components/types";

const spanLabels: AnnotationLabelType[] = [
  {
    id: "label-important",
    text: "Important Clause",
    color: "#FF6B6B",
    description: "Marks important clauses",
    icon: "tag",
    labelType: LabelType.SpanLabel,
  },
  {
    id: "label-definition",
    text: "Definition",
    color: "#4ECDC4",
    description: "Marks definitions",
    icon: "tag",
    labelType: LabelType.SpanLabel,
  },
  {
    id: "label-risk",
    text: "Risk",
    color: "#FFD93D",
    description: "Marks risks",
    icon: "tag",
    labelType: LabelType.SpanLabel,
  },
];

const docTypeLabels: AnnotationLabelType[] = [
  {
    id: "doctype-contract",
    text: "Contract",
    color: "#6C5CE7",
    description: "Contract type",
    icon: "file",
    labelType: LabelType.DocTypeLabel,
  },
];

const mockLabelSet = {
  id: "labelset-1",
  title: "Standard Labels",
  allAnnotationLabels: [...spanLabels, ...docTypeLabels],
} as unknown as LabelSetType;

const mockCorpus = {
  id: "corpus-1",
  title: "Test Corpus",
  labelSet: mockLabelSet,
} as unknown as CorpusType;

const mockCorpusNoLabelset = {
  id: "corpus-2",
  title: "Labelless Corpus",
  labelSet: null,
} as unknown as CorpusType;

const mockDocumentTxt = {
  id: "doc-1",
  title: "Doc",
  fileType: "application/txt",
} as any;

interface WrapperOptions {
  readOnly?: boolean;
  /** Whether the corpus has a label set. When false, tests the no-labelset
   * empty state. */
  withLabelset?: boolean;
  /** Initial active label. */
  activeLabel?: AnnotationLabelType | null;
  /** Pre-attach a doc-type annotation so we test filtering + toggle state. */
  withExistingDocTypeAnnotation?: boolean;
  /** Provide labels via the `labels` prop (overrides label choices from state). */
  labelsProp?: AnnotationLabelType[];
  /** Apollo mocks (for the smart-label-search-or-create mutation). */
  mocks?: MockedResponse[];
}

/**
 * Hydrates Jotai atoms inside the Playwright CT Provider scope. We create a
 * NESTED JotaiProvider inside the outer one from `playwright/index.tsx` so
 * atom hydration is test-scoped and doesn't bleed across tests.
 */
const HydrateAtoms: React.FC<{
  children: React.ReactNode;
  opts: Required<
    Omit<WrapperOptions, "mocks" | "labelsProp" | "activeLabel">
  > & {
    activeLabel: AnnotationLabelType | null;
  };
}> = ({ children, opts }) => {
  const corpus = opts.withLabelset ? mockCorpus : mockCorpusNoLabelset;

  const corpusState: CorpusState = {
    selectedCorpus: corpus,
    myPermissions: opts.readOnly
      ? [PermissionTypes.CAN_READ]
      : [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
    spanLabels,
    humanSpanLabels: spanLabels,
    relationLabels: [],
    docTypeLabels,
    humanTokenLabels: [],
    allowComments: true,
    isLoading: false,
  };

  const existingDocTypes = opts.withExistingDocTypeAnnotation
    ? [
        new DocTypeAnnotation(
          docTypeLabels[0],
          [PermissionTypes.CAN_READ, PermissionTypes.CAN_REMOVE],
          "dtann-1"
        ),
      ]
    : [];

  useHydrateAtoms([
    [selectedDocumentAtom, mockDocumentTxt],
    [corpusStateAtom, corpusState],
    [pdfAnnotationsAtom, new PdfAnnotations([], [], existingDocTypes)],
  ] as any);

  return <>{children}</>;
};

/**
 * Harness component that lets us drive the `activeSpanLabel` prop reactively
 * so tests can verify label selection + clearing in the same mount.
 */
const LabelSelectorHarness: React.FC<{
  initialActive: AnnotationLabelType | null;
  readOnly: boolean;
  labelsProp?: AnnotationLabelType[];
}> = ({ initialActive, readOnly, labelsProp }) => {
  const [activeLabel, setActive] = React.useState<AnnotationLabelType | null>(
    initialActive
  );

  return (
    <>
      <div
        data-testid="active-label-display"
        data-active-id={activeLabel?.id ?? ""}
      >
        {activeLabel?.text ?? "(none)"}
      </div>
      <EnhancedLabelSelector
        activeSpanLabel={activeLabel}
        setActiveLabel={(label) => setActive(label ?? null)}
        sidebarWidth="0px"
        readOnly={readOnly}
        hideControls={false}
        labels={labelsProp}
      />
    </>
  );
};

export const EnhancedLabelSelectorTestWrapper: React.FC<WrapperOptions> = ({
  readOnly = false,
  withLabelset = true,
  activeLabel = null,
  withExistingDocTypeAnnotation = false,
  labelsProp,
  mocks = [],
}) => {
  return (
    <MemoryRouter>
      <MockedProvider
        mocks={mocks}
        cache={new InMemoryCache({ addTypename: false })}
      >
        <JotaiProvider>
          <HydrateAtoms
            opts={{
              readOnly,
              withLabelset,
              withExistingDocTypeAnnotation,
              activeLabel,
            }}
          >
            <div
              style={{
                width: "100vw",
                height: "100vh",
                position: "relative",
              }}
            >
              <LabelSelectorHarness
                initialActive={activeLabel}
                readOnly={readOnly}
                labelsProp={labelsProp}
              />
            </div>
          </HydrateAtoms>
        </JotaiProvider>
      </MockedProvider>
    </MemoryRouter>
  );
};

export { spanLabels, docTypeLabels };
