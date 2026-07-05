import { PipelineComponentType } from "../../../types/graphql-api";

/**
 * Determine whether a pipeline component is enabled.
 *
 * The canonical rule is: an empty `enabledComponents` list means
 * "all components are enabled"; otherwise the component must be
 * present in the list.  Private helper used by `isComponentAvailable`.
 */
const isComponentEnabled = (
  className: string,
  enabledComponents: string[]
): boolean =>
  enabledComponents.length === 0 || enabledComponents.includes(className);

/**
 * Determine whether a pipeline component is available for a given
 * MIME type.  "Available" means the component is enabled **and** its
 * `supportedFileTypes` includes the short label (e.g. "PDF") — or it
 * has no `supportedFileTypes` (universal component).
 *
 * @param mimeShortLabel  Short label such as "PDF", "TXT", "DOCX".
 *   When the label cannot be resolved from the MIME-type map, pass
 *   the full MIME string as a secondary fallback so components whose
 *   `supportedFileTypes` list the full value still match.
 */
export const isComponentAvailable = (
  component: PipelineComponentType & { className: string },
  mimeShortLabel: string,
  enabledComponents: string[]
): boolean => {
  if (!isComponentEnabled(component.className, enabledComponents)) {
    return false;
  }

  const fileTypes = (component.supportedFileTypes || [])
    .filter((ft): ft is NonNullable<typeof ft> => Boolean(ft))
    .map((ft) => String(ft).toLowerCase());

  if (fileTypes.length === 0) return true; // Universal component
  return fileTypes.includes(mimeShortLabel.toLowerCase());
};

/**
 * Swap the enricher at `index` with its neighbor in `direction`. Returns the
 * SAME array reference (not a copy) when the move is out of bounds, so
 * callers can skip firing a mutation with `next === chain`.
 *
 * Pulled out of `EnricherChainEditor`'s `handleMove` so the bounds guard —
 * otherwise only reachable from a disabled `<IconButton>` that Playwright
 * can't click — is directly unit-testable.
 */
export const reorderChain = (
  chain: string[],
  index: number,
  direction: -1 | 1
): string[] => {
  const target = index + direction;
  if (target < 0 || target >= chain.length) return chain;
  const next = [...chain];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
};

/**
 * Append `className` to `chain` unless it's empty or already present.
 * Returns the SAME array reference when no change is made, for the same
 * reason as `reorderChain` above.
 */
export const appendToChain = (chain: string[], className: string): string[] => {
  if (!className || chain.includes(className)) return chain;
  return [...chain, className];
};
