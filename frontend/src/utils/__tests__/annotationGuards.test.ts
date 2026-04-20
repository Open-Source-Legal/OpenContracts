import { describe, it, expect } from "vitest";
import { isTokenAnnotation, isSpanAnnotation } from "../annotationGuards";
import { LabelType, RawServerAnnotationType } from "../../types/graphql-api";

/**
 * Build a minimal annotation that satisfies the type signature. Only the
 * discriminator fields matter for the guards.
 */
function makeAnnotation(
  overrides: Partial<RawServerAnnotationType>
): RawServerAnnotationType {
  return {
    id: "ann-1",
    annotationLabel: {
      id: "lbl-1",
      labelType: LabelType.TokenLabel,
    } as RawServerAnnotationType["annotationLabel"],
    ...overrides,
  } as RawServerAnnotationType;
}

describe("annotationGuards", () => {
  describe("isTokenAnnotation", () => {
    it("returns true when annotationType is TokenLabel", () => {
      const ann = makeAnnotation({
        annotationType: LabelType.TokenLabel,
        annotationLabel: { labelType: LabelType.SpanLabel } as any,
      });
      expect(isTokenAnnotation(ann)).toBe(true);
    });

    it("returns true when nested annotationLabel.labelType is TokenLabel", () => {
      const ann = makeAnnotation({
        annotationType: undefined,
        annotationLabel: { labelType: LabelType.TokenLabel } as any,
      });
      expect(isTokenAnnotation(ann)).toBe(true);
    });

    it("returns false for span-only annotations", () => {
      const ann = makeAnnotation({
        annotationType: LabelType.SpanLabel,
        annotationLabel: { labelType: LabelType.SpanLabel } as any,
      });
      expect(isTokenAnnotation(ann)).toBe(false);
    });
  });

  describe("isSpanAnnotation", () => {
    it("returns true when annotationType is SpanLabel", () => {
      const ann = makeAnnotation({
        annotationType: LabelType.SpanLabel,
        annotationLabel: { labelType: LabelType.TokenLabel } as any,
      });
      expect(isSpanAnnotation(ann)).toBe(true);
    });

    it("returns true when nested annotationLabel.labelType is SpanLabel", () => {
      const ann = makeAnnotation({
        annotationType: undefined,
        annotationLabel: { labelType: LabelType.SpanLabel } as any,
      });
      expect(isSpanAnnotation(ann)).toBe(true);
    });

    it("returns false for token-only annotations", () => {
      const ann = makeAnnotation({
        annotationType: LabelType.TokenLabel,
        annotationLabel: { labelType: LabelType.TokenLabel } as any,
      });
      expect(isSpanAnnotation(ann)).toBe(false);
    });
  });
});
