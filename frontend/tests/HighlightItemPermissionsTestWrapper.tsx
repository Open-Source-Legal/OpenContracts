import React from "react";
import { MemoryRouter } from "react-router-dom";
import { HighlightItem } from "../src/components/annotator/sidebar/HighlightItem";
import { ServerTokenAnnotation } from "../src/components/annotator/types/annotations";
import { PermissionTypes } from "../src/components/types";
import { AnnotationLabelType } from "../src/types/graphql-api";

/**
 * Playwright CT cannot serialize class instances or function closures across
 * the worker boundary, so the harness builds the annotation fixture from
 * primitive props and wires the component internally. Tests configure the
 * fixture via the flat prop set below.
 */

const TEST_LABEL: AnnotationLabelType = {
  id: "label-1",
  text: "Test Label",
  color: "#2ecc71",
  description: "Fixture annotation label",
  labelType: "TOKEN_LABEL" as any,
  icon: "tag" as any,
  readonly: false,
};

export interface HighlightItemHarnessProps {
  /** Whether the annotation is structural (parser-detected structure). */
  structural?: boolean;
  /** Whether the surrounding context is read-only. */
  readOnly?: boolean;
  /** Permissions the current user has on the annotation. */
  permissions?: PermissionTypes[];
  /** Whether the parent supplies an onDelete handler. */
  withOnDelete?: boolean;
  /**
   * Test id set on a hidden receipt div each time onDelete fires. Lets the
   * CT test assert the click handler was invoked without passing closures.
   */
  deleteReceiptTestId?: string;
}

export const HighlightItemHarness: React.FC<HighlightItemHarnessProps> = ({
  structural = false,
  readOnly = false,
  permissions = [],
  withOnDelete = true,
  deleteReceiptTestId = "delete-receipt",
}) => {
  const [deletedId, setDeletedId] = React.useState<string | null>(null);

  const annotation = React.useMemo(
    () =>
      new ServerTokenAnnotation(
        1,
        TEST_LABEL,
        "Lorem ipsum fixture text for the sidebar card.",
        structural,
        {
          "1": {
            bounds: { left: 0, top: 0, right: 0, bottom: 0 },
            tokensJsons: [],
            rawText: "Lorem ipsum fixture text for the sidebar card.",
          },
        },
        permissions,
        false,
        false,
        false,
        "ann-fixture"
      ),
    [structural, permissions]
  );

  const onDelete = withOnDelete ? (id: string) => setDeletedId(id) : undefined;

  return (
    <MemoryRouter>
      <div style={{ padding: 16, maxWidth: 380 }}>
        <HighlightItem
          annotation={annotation}
          read_only={readOnly}
          relations={[]}
          onDelete={onDelete}
          onSelect={() => {}}
        />
        {/* Receipt: rendered only after the onDelete callback has fired. */}
        {deletedId !== null && (
          <div data-testid={deleteReceiptTestId}>{deletedId}</div>
        )}
      </div>
    </MemoryRouter>
  );
};
