import React from "react";
import {
  DoclingIcon,
  LlamaParseIcon,
  TextParserIcon,
  PdfThumbnailIcon,
  TextThumbnailIcon,
  ModernBertIcon,
  SentenceTransformerIcon,
  MultimodalIcon,
  GenericComponentIcon,
  getComponentIcon,
  getComponentDisplayName,
} from "../src/components/admin/PipelineIcons";
import { PIPELINE_ICON_NAMES } from "./pipeline-icons.ct-constants";

// ---------------------------------------------------------------------------
// Catalog of pipeline icons, paired to the name list in pipeline-icons.ct-
// constants.ts so the wrapper and the test file can't silently drift when a
// new icon is added. Adding an icon component here without extending
// PIPELINE_ICON_NAMES (or vice versa) will fail the compile-time check below.
// Non-component exports live in the sibling constants module because
// Playwright CT's babel plugin treats *TestWrapper.tsx as a component file.
// ---------------------------------------------------------------------------
const ICON_COMPONENTS_BY_NAME: Record<
  (typeof PIPELINE_ICON_NAMES)[number],
  React.FC<any>
> = {
  DoclingIcon,
  LlamaParseIcon,
  TextParserIcon,
  PdfThumbnailIcon,
  TextThumbnailIcon,
  ModernBertIcon,
  SentenceTransformerIcon,
  MultimodalIcon,
  GenericComponentIcon,
};

const ALL_ICON_COMPONENTS = PIPELINE_ICON_NAMES.map((name) => ({
  name,
  Component: ICON_COMPONENTS_BY_NAME[name],
}));

/**
 * Mounts the full catalog of pipeline icons at default size. The data-testid
 * labels make each cell addressable for per-icon assertions, while a single
 * render cycle exercises the full React component tree.
 */
export const PipelineIconCatalogWrapper: React.FC = () => (
  <div
    data-testid="pipeline-icon-catalog"
    style={{
      display: "grid",
      gridTemplateColumns: "repeat(3, 1fr)",
      gap: "1rem",
      padding: "1rem",
    }}
  >
    {ALL_ICON_COMPONENTS.map(({ name, Component }) => (
      <div
        key={name}
        data-testid={`icon-cell-${name}`}
        style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
      >
        <Component />
        <span>{name}</span>
      </div>
    ))}
  </div>
);

/**
 * Renders each icon twice: once at default size and once at a custom size with
 * a className. Exercises both code paths in the `BrandIcon` helper and the
 * inline-SVG branches that spread `size`/`className` props.
 */
export const PipelineIconPropsWrapper: React.FC = () => (
  <div data-testid="pipeline-icon-props">
    {ALL_ICON_COMPONENTS.map(({ name, Component }) => (
      <div key={name} data-testid={`icon-props-${name}`}>
        <Component />
        <Component size={24} className="custom-icon-class" />
        <Component size={96} className="large-icon" />
      </div>
    ))}
  </div>
);

// Build a map keyed by component reference so we can resolve a stable name
// even when minification strips Function.name (Vite/SWC sometimes does this).
const ICON_NAME_BY_REF = new Map<React.FC<any>, string>(
  ALL_ICON_COMPONENTS.map(({ name, Component }) => [Component, name])
);

/**
 * Exercises `getComponentIcon` across every branch of its class-name
 * dispatcher so the icon-picking logic (not just the individual icons) is
 * covered. Each cell renders the icon returned for the given className.
 */
export const PipelineIconDispatcherWrapper: React.FC<{
  classNames: string[];
}> = ({ classNames }) => (
  <div data-testid="pipeline-icon-dispatcher">
    {classNames.map((className) => {
      const Icon = getComponentIcon(className);
      const resolvedName = ICON_NAME_BY_REF.get(Icon) ?? "Unknown";
      return (
        <div
          key={className}
          data-testid={`dispatched-${className}`}
          data-resolved-icon={resolvedName}
        >
          <Icon size={32} />
          <span>{getComponentDisplayName(className)}</span>
        </div>
      );
    })}
  </div>
);

/**
 * Exercises `getComponentDisplayName` including the `title` override and the
 * acronym replacement path. Renders the resulting label into the DOM so the
 * test can assert on visible text.
 */
export const PipelineDisplayNameWrapper: React.FC<{
  samples: { className: string; title?: string }[];
}> = ({ samples }) => (
  <div data-testid="pipeline-display-names">
    {samples.map(({ className, title }, idx) => (
      <div
        key={`${className}-${idx}`}
        data-testid={`display-name-${idx}`}
        data-source-class={className}
      >
        {getComponentDisplayName(className, title)}
      </div>
    ))}
  </div>
);
