import React, { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import TxtAnnotator from "../src/components/annotator/renderers/txt/TxtAnnotator";
import { ServerSpanAnnotation } from "../src/components/annotator/types/annotations";
import { AnnotationLabelType, LabelType } from "../src/types/graphql-api";
import { PermissionTypes, TextSearchSpanResult } from "../src/components/types";

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

const sampleText =
  "This is a sample document text. It contains multiple sentences for testing purposes. " +
  "The annotator should render this text and allow selections to be made by the user.";

const sampleAnnotation = new ServerSpanAnnotation(
  0,
  sampleLabels[0],
  "sample document text",
  false,
  { start: 10, end: 30 },
  [
    PermissionTypes.CAN_READ,
    PermissionTypes.CAN_UPDATE,
    PermissionTypes.CAN_REMOVE,
  ],
  false,
  false,
  false,
  "ann-1"
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
  /** Pre-select an annotation ID so its label renders. */
  preselectAnnotation?: string;
  /** Filter visible labels (null = show all, [] = hide all). */
  visibleLabels?: AnnotationLabelType[] | null;
  /** Display search results for highlighting. */
  searchResults?: TextSearchSpanResult[];
  /** Display chat sources for highlighting. */
  chatSources?: ChatSourceHighlight[];
  /** Mark a chat source as currently selected. */
  selectedChatSourceId?: string;
  /** Use a second annotation for multi-annotation overlap testing. */
  withOverlappingAnnotations?: boolean;
  /** Exclude CAN_REMOVE from the annotation's permissions. */
  noDeletePermission?: boolean;
  /** Exclude CAN_UPDATE from the annotation's permissions. */
  noUpdatePermission?: boolean;
  /** Mark the first annotation as approved. */
  approved?: boolean;
  /** Mark the first annotation as rejected. */
  rejected?: boolean;
  /** Mark the first annotation as structural. */
  structural?: boolean;
  /**
   * Pass explicit `showStructuralAnnotations` to the annotator.
   * Defaults to the `structural` flag so existing callers behave the same;
   * tests that want to assert the "structural annotation is filtered out
   * when showStructuralAnnotations=false" branch can override this
   * independently of the annotation's structural flag.
   */
  showStructuralAnnotations?: boolean;
  /** Disable approve/reject callbacks to test the "no feedback actions" path. */
  hideApproveReject?: boolean;
}

export const TxtAnnotatorTestWrapper: React.FC<WrapperProps> = ({
  readOnly = true,
  withAnnotations = false,
  preselectAnnotation,
  visibleLabels,
  searchResults,
  chatSources,
  selectedChatSourceId,
  withOverlappingAnnotations = false,
  noDeletePermission = false,
  noUpdatePermission = false,
  approved = false,
  rejected = false,
  structural = false,
  showStructuralAnnotations,
  hideApproveReject = false,
}) => {
  const [selected, setSelected] = useState<string[]>(
    preselectAnnotation ? [preselectAnnotation] : []
  );

  const perms: PermissionTypes[] = [PermissionTypes.CAN_READ];
  if (!noUpdatePermission) perms.push(PermissionTypes.CAN_UPDATE);
  if (!noDeletePermission) perms.push(PermissionTypes.CAN_REMOVE);

  const firstAnn = new ServerSpanAnnotation(
    0,
    sampleLabels[0],
    "sample document text",
    structural,
    { start: 10, end: 30 },
    perms,
    approved,
    rejected,
    false,
    "ann-1"
  );

  const secondAnn = new ServerSpanAnnotation(
    0,
    sampleLabels[1],
    "contains multiple",
    false,
    { start: 35, end: 52 },
    [PermissionTypes.CAN_READ, PermissionTypes.CAN_UPDATE],
    false,
    false,
    false,
    "ann-2"
  );

  const annotations = withAnnotations
    ? withOverlappingAnnotations
      ? [firstAnn, secondAnn]
      : [firstAnn]
    : [];

  return (
    <MemoryRouter>
      <div style={{ width: 600, height: 400, padding: 16 }}>
        <TxtAnnotator
          text={sampleText}
          annotations={annotations}
          searchResults={searchResults ?? []}
          chatSources={chatSources}
          selectedChatSourceId={selectedChatSourceId}
          getSpan={(span) =>
            new ServerSpanAnnotation(
              0,
              sampleLabels[0],
              span.text,
              false,
              { start: span.start, end: span.end },
              [
                PermissionTypes.CAN_READ,
                PermissionTypes.CAN_UPDATE,
                PermissionTypes.CAN_REMOVE,
              ],
              false,
              false,
              false
            )
          }
          visibleLabels={
            visibleLabels === undefined ? sampleLabels : visibleLabels
          }
          availableLabels={sampleLabels}
          selectedLabelTypeId={null}
          read_only={readOnly}
          allowInput={!readOnly}
          createAnnotation={() => {}}
          updateAnnotation={() => {}}
          approveAnnotation={hideApproveReject ? undefined : () => {}}
          rejectAnnotation={hideApproveReject ? undefined : () => {}}
          deleteAnnotation={() => {}}
          selectedAnnotations={selected}
          setSelectedAnnotations={setSelected}
          showStructuralAnnotations={showStructuralAnnotations ?? structural}
        />
      </div>
    </MemoryRouter>
  );
};
