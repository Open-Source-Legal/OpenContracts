/**
 * Generic CAML component embed system.
 *
 * Provides a registry + marker parser so CAML prose blocks can embed arbitrary
 * React components via a simple text marker syntax:
 *
 *   [component:TYPE key1=value1 key2=value2]
 *
 * Example markers:
 *   [component:extract-grid extractId=RXh0cmFjdFR5cGU6Mg==]
 *   [component:annotation-card annotationId=QW5ub3RhdGlvblR5cGU6MQ==]
 *
 * The registry maps TYPE strings to React components. Each component receives
 * a plain `Record<string, string>` of the parsed key=value props.
 *
 * This is an interim mechanism until upstream @os-legal/caml-react supports a
 * `customBlocks` prop (tracked in #1172). When that ships, migrate block types
 * from this marker system to proper CAML block definitions.
 */

import React, { ComponentType } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Props passed to every embedded CAML component. */
export type CamlComponentProps = Record<string, string>;

/**
 * A React component that can be embedded in CAML prose.
 * Uses Record<string, string | undefined> to cover optional marker props
 * while avoiding a blanket `any`.
 *
 * **Security note**: All prop values originate from user-authored CAML content
 * and should be treated as untrusted input. Components must never use props in
 * dangerous sinks (e.g. `dangerouslySetInnerHTML`, `eval`, or unescaped URLs).
 * Passing a prop as a GraphQL variable (e.g. `extractId`) is safe because the
 * server validates the ID against the user's permissions.
 */
export type CamlEmbedComponent = ComponentType<
  Record<string, string | undefined>
>;

/** Result of parsing a `[component:...]` marker. */
export interface ParsedComponentMarker {
  type: string;
  props: CamlComponentProps;
}

/** Map of component type names to their React components. */
export type CamlComponentRegistry = Record<string, CamlEmbedComponent>;

// ---------------------------------------------------------------------------
// Marker parser
// ---------------------------------------------------------------------------

/**
 * Regex matching `[component:TYPE key=value ...]` on a line by itself.
 *
 * Captures:
 *   1: TYPE  — the component type name (alphanumeric + hyphens)
 *   2: rest  — the remaining key=value pairs (may be empty)
 */
const COMPONENT_MARKER_RE = /^\[component:([a-zA-Z0-9-]+)(?:\s+(.*))?\]$/;

/**
 * Try to parse a prose block's text content as a component marker.
 *
 * Returns the parsed marker if the entire trimmed content is a single
 * `[component:...]` line, or `null` if it's regular markdown.
 */
export function parseComponentMarker(
  content: string
): ParsedComponentMarker | null {
  const trimmed = content.trim();
  const match = COMPONENT_MARKER_RE.exec(trimmed);
  if (!match) return null;

  const type = match[1];
  const rest = match[2] ?? "";
  const props: CamlComponentProps = {};

  // Use matchAll with an inline regex to avoid shared mutable lastIndex state
  // from a module-level RegExp with the `g` flag.
  for (const propMatch of rest.matchAll(
    /([a-zA-Z_]\w*)=(?:"((?:[^"\\]|\\.)*)"|(\S+))/g
  )) {
    const key = propMatch[1];
    const quoted = propMatch[2];
    // Only unescape \" and \\ — reject other escape sequences so that
    // user-authored content cannot inject control characters (\n, \t, \0, etc.).
    const value =
      quoted !== undefined
        ? quoted.replace(/\\(.)/g, (_, char) =>
            char === '"' || char === "\\" ? char : `\\${char}`
          )
        : propMatch[3];
    props[key] = value;
  }

  return { type, props };
}

/**
 * Build a `[component:...]` marker string from type and props.
 *
 * Used by the editor to insert markers at the cursor. Values containing
 * whitespace, double-quotes, backslashes, equals signs, or closing brackets
 * are automatically quoted, with internal backslashes and double-quotes escaped.
 */
export function buildComponentMarker(
  type: string,
  props: CamlComponentProps
): string {
  const pairs = Object.entries(props).map(([k, v]) => {
    const needsQuoting = /[\s"\\=\]]/.test(v);
    if (needsQuoting) {
      const escaped = v.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
      return `${k}="${escaped}"`;
    }
    return `${k}=${v}`;
  });
  const suffix = pairs.length > 0 ? " " + pairs.join(" ") : "";
  return `[component:${type}${suffix}]`;
}

/**
 * Name of the custom CAML fence used to embed an OpenContracts component.
 *
 * The library's parser does not have a dedicated case for `::: prose`, so a
 * `::: prose` fence ends up as `{type: "prose", body, ...}` *without* a
 * `content` field — and `ProseBlock` then crashes inside `splitPullquotes`.
 * Using a project-specific block type sidesteps the missing case: unknown
 * types fall through to the renderer's `customBlocks` lookup, where we own
 * the rendering and can simply pass the marker text to our resolver.
 */
export const OC_COMPONENT_FENCE = "oc-component";

/**
 * Shape of a parsed `::: oc-component` block produced by @os-legal/caml.
 * Used by `customBlocks` handlers when the renderer dispatches an
 * `oc-component` fence. Only `body` is read by the OpenContracts dispatcher;
 * the other fields are included for completeness.
 */
export interface OcComponentBlock {
  type: string;
  body?: string;
  attrs?: Record<string, string>;
}

/**
 * Wrap a marker in a CAML fence ready for insertion into the editor source.
 *
 * The marker text is preserved verbatim inside the fence body so existing
 * marker parsers (`parseComponentMarker`, `resolveComponentMarker`) keep
 * working against the same `[component:TYPE ...]` shape.
 */
export function buildComponentProseFence(
  type: string,
  props: CamlComponentProps
): string {
  return `\n::: ${OC_COMPONENT_FENCE}\n${buildComponentMarker(
    type,
    props
  )}\n:::\n`;
}

// ---------------------------------------------------------------------------
// Component resolution
// ---------------------------------------------------------------------------

/**
 * Parse a prose block for a component marker and resolve it against a registry.
 *
 * Returns a React element if the marker matches a registered component,
 * or `null` if the text is not a marker or the type is unregistered.
 * Used by both `useCamlComponentRenderer` and `CamlDirectiveRenderer` to
 * keep parsing + lookup in a single code path.
 *
 * @param key - Optional React key for the created element (useful when
 *   rendering multiple markers in a list to satisfy React reconciliation).
 */
export function resolveComponentMarker(
  md: string,
  registry: CamlComponentRegistry,
  key?: string
): React.ReactElement | null {
  const parsed = parseComponentMarker(md);
  if (!parsed) return null;
  const Component = registry[parsed.type];
  if (!Component) return null;
  return React.createElement(Component, { key, ...parsed.props });
}

/**
 * Build the `customBlocks` object passed to `<CamlArticle>` for the
 * project-specific `::: oc-component` fence.
 *
 * Both `useCamlComponentRenderer` and `CamlDirectiveRenderer` need to forward
 * the fence body through their own `renderMarkdown` so the inline-marker path
 * can resolve registered components. Centralising the lookup keeps the
 * `OcComponentBlock` cast and the body-extraction logic in one place.
 */
export function buildOcComponentCustomBlocks(
  renderMarkdown: (md: string) => React.ReactNode
): Record<string, (block: unknown) => React.ReactNode> {
  return {
    [OC_COMPONENT_FENCE]: (block: unknown) => {
      const body = ((block as OcComponentBlock | undefined)?.body ?? "").trim();
      return renderMarkdown(body);
    },
  };
}
