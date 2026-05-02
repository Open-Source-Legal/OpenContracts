import { describe, it, expect } from "vitest";
import {
  parseComponentMarker,
  buildComponentMarker,
  buildComponentProseFence,
  resolveComponentMarker,
} from "../camlComponents";

describe("parseComponentMarker()", () => {
  it("parses a marker with a single unquoted prop", () => {
    const result = parseComponentMarker(
      "[component:extract-grid extractId=abc123]"
    );
    expect(result).toEqual({
      type: "extract-grid",
      props: { extractId: "abc123" },
    });
  });

  it("parses a marker with multiple unquoted props", () => {
    const result = parseComponentMarker(
      "[component:my-widget foo=bar baz=qux]"
    );
    expect(result).toEqual({
      type: "my-widget",
      props: { foo: "bar", baz: "qux" },
    });
  });

  it("parses a marker with quoted prop values", () => {
    const result = parseComponentMarker(
      '[component:card title="Hello World" subtitle="A subtitle"]'
    );
    expect(result).toEqual({
      type: "card",
      props: { title: "Hello World", subtitle: "A subtitle" },
    });
  });

  it("parses a marker with mixed quoted and unquoted props", () => {
    const result = parseComponentMarker(
      '[component:widget id=123 label="My Label"]'
    );
    expect(result).toEqual({
      type: "widget",
      props: { id: "123", label: "My Label" },
    });
  });

  it("parses a marker with no props", () => {
    const result = parseComponentMarker("[component:empty-widget]");
    expect(result).toEqual({ type: "empty-widget", props: {} });
  });

  it("handles leading/trailing whitespace", () => {
    const result = parseComponentMarker(
      "  [component:extract-grid extractId=abc]  "
    );
    expect(result).toEqual({
      type: "extract-grid",
      props: { extractId: "abc" },
    });
  });

  it("returns null for regular markdown", () => {
    expect(parseComponentMarker("# Hello World")).toBeNull();
    expect(parseComponentMarker("Some paragraph text")).toBeNull();
    expect(parseComponentMarker("[not a component marker]")).toBeNull();
  });

  it("returns null for multi-line input", () => {
    expect(
      parseComponentMarker("[component:widget id=1]\n[component:widget id=2]")
    ).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(parseComponentMarker("")).toBeNull();
  });

  it("handles quoted values containing equals signs", () => {
    const result = parseComponentMarker('[component:filter expr="a=b"]');
    expect(result).toEqual({
      type: "filter",
      props: { expr: "a=b" },
    });
  });

  it("supports underscores in prop keys", () => {
    const result = parseComponentMarker("[component:grid my_prop=value]");
    expect(result).toEqual({
      type: "grid",
      props: { my_prop: "value" },
    });
  });

  it("preserves literal backslash-n/backslash-t in quoted values (no control char injection)", () => {
    const result = parseComponentMarker(
      '[component:widget label="line\\none"]'
    );
    expect(result).toEqual({
      type: "widget",
      props: { label: "line\\none" },
    });
  });

  it("preserves literal backslash-t in quoted values", () => {
    const result = parseComponentMarker('[component:widget label="col\\tcol"]');
    expect(result).toEqual({
      type: "widget",
      props: { label: "col\\tcol" },
    });
  });

  it("preserves null byte escape sequences in quoted values", () => {
    const result = parseComponentMarker('[component:widget label="a\\0b"]');
    expect(result).toEqual({
      type: "widget",
      props: { label: "a\\0b" },
    });
  });
});

describe("buildComponentMarker()", () => {
  it("builds a marker with a single prop", () => {
    expect(buildComponentMarker("extract-grid", { extractId: "abc123" })).toBe(
      "[component:extract-grid extractId=abc123]"
    );
  });

  it("builds a marker with no props", () => {
    expect(buildComponentMarker("empty-widget", {})).toBe(
      "[component:empty-widget]"
    );
  });

  it("quotes values containing spaces", () => {
    expect(buildComponentMarker("card", { title: "Hello World" })).toBe(
      '[component:card title="Hello World"]'
    );
  });

  it("does not quote values without spaces", () => {
    expect(buildComponentMarker("grid", { id: "abc123" })).toBe(
      "[component:grid id=abc123]"
    );
  });

  it("round-trips through parseComponentMarker", () => {
    const original = { type: "extract-grid", props: { extractId: "abc" } };
    const marker = buildComponentMarker(original.type, original.props);
    const parsed = parseComponentMarker(marker);
    expect(parsed).toEqual(original);
  });

  it("round-trips quoted values", () => {
    const original = {
      type: "card",
      props: { title: "Hello World", id: "123" },
    };
    const marker = buildComponentMarker(original.type, original.props);
    const parsed = parseComponentMarker(marker);
    expect(parsed).toEqual(original);
  });

  it("escapes double quotes inside values", () => {
    const marker = buildComponentMarker("widget", {
      label: 'Say "hello"',
    });
    expect(marker).toBe('[component:widget label="Say \\"hello\\""]');
  });

  it("round-trips values containing double quotes", () => {
    const original = {
      type: "widget",
      props: { label: 'Say "hello"' },
    };
    const marker = buildComponentMarker(original.type, original.props);
    const parsed = parseComponentMarker(marker);
    expect(parsed).toEqual(original);
  });

  it("round-trips values containing equals signs", () => {
    const original = {
      type: "filter",
      props: { expr: "a=b" },
    };
    const marker = buildComponentMarker(original.type, original.props);
    const parsed = parseComponentMarker(marker);
    expect(parsed).toEqual(original);
  });

  it("escapes backslashes inside values", () => {
    const original = {
      type: "widget",
      props: { path: "C:\\Users\\test" },
    };
    const marker = buildComponentMarker(original.type, original.props);
    const parsed = parseComponentMarker(marker);
    expect(parsed).toEqual(original);
  });

  it("quotes values containing closing brackets", () => {
    const marker = buildComponentMarker("widget", { expr: "arr[0]" });
    expect(marker).toBe('[component:widget expr="arr[0]"]');
    const parsed = parseComponentMarker(marker);
    expect(parsed).toEqual({
      type: "widget",
      props: { expr: "arr[0]" },
    });
  });
});

describe("buildComponentProseFence()", () => {
  it("wraps marker in the project's oc-component fence", () => {
    const result = buildComponentProseFence("extract-grid", {
      extractId: "abc",
    });
    expect(result).toBe(
      "\n::: oc-component\n[component:extract-grid extractId=abc]\n:::\n"
    );
  });
});

describe("resolveComponentMarker()", () => {
  const FakeComponent = () => null;
  const registry = { "extract-grid": FakeComponent };

  it("returns null for regular markdown (not a marker)", () => {
    expect(resolveComponentMarker("# Hello World", registry)).toBeNull();
  });

  it("returns null for a valid marker with an unrecognized type", () => {
    expect(
      resolveComponentMarker("[component:unknown-widget foo=bar]", registry)
    ).toBeNull();
  });

  it("returns a React element for a registered component type", () => {
    const result = resolveComponentMarker(
      "[component:extract-grid extractId=abc]",
      registry
    );
    expect(result).not.toBeNull();
  });

  it("attaches the supplied key to the created element", () => {
    const marker = "[component:extract-grid extractId=abc]";
    const result = resolveComponentMarker(marker, registry, marker);
    expect(result).not.toBeNull();
    expect(result?.key).toBe(marker);
  });

  it("creates elements with null key when no key argument is supplied", () => {
    const result = resolveComponentMarker(
      "[component:extract-grid extractId=abc]",
      registry
    );
    expect(result).not.toBeNull();
    expect(result?.key).toBeNull();
  });
});
