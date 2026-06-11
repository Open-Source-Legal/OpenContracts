/**
 * Unit tests for ``urlAnnotation.ts``:
 *
 * - ``isUrlAnnotation`` returns true for ANY annotation with a non-empty
 *   ``linkUrl`` (user OC_URL links and enrichment reference mentions alike).
 * - ``openAnnotationUrl`` opens http(s) URLs via ``window.open`` with
 *   noopener/noreferrer, navigates site-relative paths in the current tab,
 *   and refuses dangerous schemes (``javascript:``, ``data:``) even when
 *   the model layer would normally have stripped them.
 *
 * These tests pin the click-time defence: the renderer must never invoke
 * ``window.open`` with attacker-controlled schemes, even if a stale cached
 * annotation slipped through the model-level allow-list.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

import {
  OC_URL_LABEL,
  OC_REF_LAW_LABEL,
  OC_REF_DOC_LABEL,
} from "../../../../assets/configurations/constants";
import { LabelType } from "../../types/enums";
import { PermissionTypes } from "../../../types";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../../types/annotations";
import {
  annotationChipLabel,
  isSafeUrl,
  isUrlAnnotation,
  openAnnotationUrl,
} from "../urlAnnotation";
import type { AnnotationLabelType } from "../../../../types/graphql-api";

// SemanticICONS unions are unwieldy in tests; cast via ``unknown`` once
// at the constant boundary so the rest of the file stays well-typed.
const ocUrlLabel: AnnotationLabelType = {
  id: "label-url",
  text: OC_URL_LABEL,
  color: "#2563EB",
  description: "url",
  labelType: LabelType.SpanLabel,
  icon: "link" as unknown as AnnotationLabelType["icon"],
};

const otherLabel: AnnotationLabelType = {
  id: "label-other",
  text: "Other",
  color: "#333333",
  description: "",
  labelType: LabelType.SpanLabel,
  icon: "tag" as unknown as AnnotationLabelType["icon"],
};

function makeSpan(
  label: AnnotationLabelType,
  linkUrl: string | null | undefined
): ServerSpanAnnotation {
  return new ServerSpanAnnotation(
    0,
    label,
    "hello",
    false,
    { start: 0, end: 5 },
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    "ann-1",
    undefined,
    linkUrl
  );
}

function makeToken(
  label: AnnotationLabelType,
  linkUrl: string | null | undefined
): ServerTokenAnnotation {
  return new ServerTokenAnnotation(
    0,
    label,
    "hello",
    false,
    {
      0: { bounds: {}, rawText: "hello", tokensJsons: [] },
    } as unknown as Record<string, unknown>,
    [PermissionTypes.CAN_READ],
    false,
    false,
    false,
    "ann-1",
    undefined,
    linkUrl
  );
}

describe("isUrlAnnotation", () => {
  it("returns true when linkUrl is non-empty (OC_URL label)", () => {
    expect(isUrlAnnotation(makeSpan(ocUrlLabel, "https://example.com"))).toBe(
      true
    );
    expect(isUrlAnnotation(makeToken(ocUrlLabel, "https://example.com"))).toBe(
      true
    );
  });

  it("returns false when linkUrl is missing", () => {
    // Common while the author is editing — the annotation is not yet
    // clickable so click handlers must keep selection behaviour.
    expect(isUrlAnnotation(makeSpan(ocUrlLabel, null))).toBe(false);
    expect(isUrlAnnotation(makeSpan(ocUrlLabel, undefined))).toBe(false);
    expect(isUrlAnnotation(makeSpan(ocUrlLabel, ""))).toBe(false);
    expect(isUrlAnnotation(makeSpan(ocUrlLabel, "   "))).toBe(false);
  });

  it("returns true for any label with a linkUrl (reference mentions)", () => {
    // link_url is the contract, not the label: enrichment reference
    // mentions (OC_REF_LAW / OC_REF_DOC) carry canonical /d/… paths and
    // must be clickable in both viewers. The URL itself is still gated by
    // isSafeUrl at open time.
    expect(isUrlAnnotation(makeSpan(otherLabel, "https://example.com"))).toBe(
      true
    );
    expect(
      isUrlAnnotation(makeSpan(otherLabel, "/d/owner/dgcl/dgcl-145"))
    ).toBe(true);
    expect(isUrlAnnotation(makeSpan(otherLabel, null))).toBe(false);
  });
});

describe("annotationChipLabel", () => {
  const refLawLabel: AnnotationLabelType = {
    ...otherLabel,
    id: "label-ref-law",
    text: OC_REF_LAW_LABEL,
  };
  const refDocLabel: AnnotationLabelType = {
    ...otherLabel,
    id: "label-ref-doc",
    text: OC_REF_DOC_LABEL,
  };

  it("maps reference-mention label codes to friendly names", () => {
    // The chip should read "Law" / "Exhibit", not the raw OC_REF_* code.
    expect(annotationChipLabel(makeSpan(refLawLabel, "/d/x"))).toBe("Law");
    expect(annotationChipLabel(makeSpan(refDocLabel, "/d/x"))).toBe("Exhibit");
  });

  it("passes other labels through unchanged", () => {
    expect(annotationChipLabel(makeSpan(otherLabel, null))).toBe("Other");
    expect(annotationChipLabel(makeSpan(ocUrlLabel, "https://x"))).toBe(
      OC_URL_LABEL
    );
  });
});

describe("openAnnotationUrl", () => {
  let originalOpen: typeof window.open;
  let originalLocation: Location;
  let openSpy: ReturnType<typeof vi.fn>;
  let assignSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    originalOpen = window.open;
    openSpy = vi.fn();
    window.open = openSpy as unknown as typeof window.open;

    // jsdom's ``window.location`` is non-configurable per-property. Replace
    // the whole object via Object.defineProperty on window — that descriptor
    // IS configurable — so we can inject a recording stub for ``assign``.
    originalLocation = window.location;
    assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: {
        ...originalLocation,
        assign: assignSpy,
      },
    });
  });

  afterEach(() => {
    window.open = originalOpen;
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });

  it("opens https URLs in a new tab with noopener,noreferrer", () => {
    const ok = openAnnotationUrl(makeSpan(ocUrlLabel, "https://example.com"));
    expect(ok).toBe(true);
    expect(openSpy).toHaveBeenCalledWith(
      "https://example.com",
      "_blank",
      "noopener,noreferrer"
    );
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("opens http URLs in a new tab with noopener,noreferrer", () => {
    const ok = openAnnotationUrl(makeSpan(ocUrlLabel, "http://example.com"));
    expect(ok).toBe(true);
    expect(openSpy).toHaveBeenCalledTimes(1);
  });

  it("navigates site-relative paths via window.location.assign as fallback", () => {
    // When no ``navigate`` callback is supplied, the helper falls back to
    // a hard navigation. This keeps the API safe for non-router contexts.
    const ok = openAnnotationUrl(makeSpan(ocUrlLabel, "/corpus/foo"));
    expect(ok).toBe(true);
    expect(assignSpy).toHaveBeenCalledWith("/corpus/foo");
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("uses the navigate callback when supplied for site-relative paths", () => {
    // Preferred path: pass a ``useNavigate()`` callback from react-router-dom
    // so the SPA router resolves the URL in place, preserving Apollo cache
    // and component state. The hard ``window.location.assign`` fallback
    // must NOT fire.
    const navigateSpy = vi.fn();
    const ok = openAnnotationUrl(
      makeSpan(ocUrlLabel, "/corpus/foo"),
      navigateSpy
    );
    expect(ok).toBe(true);
    expect(navigateSpy).toHaveBeenCalledWith("/corpus/foo");
    expect(assignSpy).not.toHaveBeenCalled();
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("refuses to open javascript: URLs", () => {
    // The model layer would already strip these, but the renderer is the
    // last line of defence — never reflect attacker-controlled schemes.
    const ok = openAnnotationUrl(makeSpan(ocUrlLabel, "javascript:alert(1)"));
    expect(ok).toBe(false);
    expect(openSpy).not.toHaveBeenCalled();
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("refuses to open data: URLs", () => {
    const ok = openAnnotationUrl(
      makeSpan(ocUrlLabel, "data:text/html,<script>alert(1)</script>")
    );
    expect(ok).toBe(false);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("refuses to open protocol-relative URLs (open-redirect guard)", () => {
    // ``//evil.com`` starts with ``/`` but the browser would resolve it
    // as ``https://evil.com`` — the site-relative branch must reject it
    // so this open-redirect vector closes here at the renderer layer.
    const ok = openAnnotationUrl(makeSpan(ocUrlLabel, "//evil.com"));
    expect(ok).toBe(false);
    expect(openSpy).not.toHaveBeenCalled();
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("refuses to open empty/missing URLs", () => {
    expect(openAnnotationUrl(makeSpan(ocUrlLabel, ""))).toBe(false);
    expect(openAnnotationUrl(makeSpan(ocUrlLabel, undefined))).toBe(false);
    expect(openAnnotationUrl(makeSpan(ocUrlLabel, null))).toBe(false);
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("trims whitespace from valid URLs before opening", () => {
    const ok = openAnnotationUrl(
      makeSpan(ocUrlLabel, "  https://example.com  ")
    );
    expect(ok).toBe(true);
    expect(openSpy).toHaveBeenCalledWith(
      "https://example.com",
      "_blank",
      "noopener,noreferrer"
    );
  });
});

describe("isSafeUrl", () => {
  // Direct coverage of the exported helper used by authoring UIs
  // (``CreateUrlAnnotationModal`` shares it via import) so the
  // empty-string branch is exercised independently of
  // ``openAnnotationUrl`` (which short-circuits earlier on ``!url``).
  it("returns false for an empty string", () => {
    expect(isSafeUrl("")).toBe(false);
  });

  it("returns false for a whitespace-only string", () => {
    // ``isSafeUrl`` trims internally and then checks the *normalised*
    // length, so leading/trailing whitespace must collapse to false.
    expect(isSafeUrl("   ")).toBe(false);
    expect(isSafeUrl("\t\n  ")).toBe(false);
  });

  it("returns true for absolute http(s) URLs", () => {
    expect(isSafeUrl("http://example.com")).toBe(true);
    expect(isSafeUrl("https://example.com/path")).toBe(true);
    // Case-insensitive scheme.
    expect(isSafeUrl("HTTPS://EXAMPLE.COM")).toBe(true);
  });

  it("returns true for site-relative paths", () => {
    expect(isSafeUrl("/corpus/foo")).toBe(true);
  });

  it("rejects protocol-relative URLs (open-redirect guard)", () => {
    expect(isSafeUrl("//evil.com")).toBe(false);
    expect(isSafeUrl("//evil.com/path?x=1")).toBe(false);
  });

  it("rejects dangerous schemes", () => {
    expect(isSafeUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeUrl("data:text/html,<script>")).toBe(false);
    expect(isSafeUrl("file:///etc/passwd")).toBe(false);
    expect(isSafeUrl("ftp://example.com")).toBe(false);
  });
});
