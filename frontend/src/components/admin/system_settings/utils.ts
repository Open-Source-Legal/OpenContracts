import { FileTypeEnum, PipelineComponentType } from "../../../types/graphql-api";

/**
 * Convert a file type value (enum value or MIME type) to a short display label.
 *
 * The backend sends file types as short enum values ("pdf", "txt", "docx")
 * via the FileTypeEnum GraphQL enum. This helper uppercases them for display,
 * with a MIME-type fallback for any unexpected values.
 */
export const fileTypeToShortLabel = (ft: FileTypeEnum | string): string => {
  const s = String(ft);
  // Short-form enum values like "pdf", "txt", "docx"
  if (!s.includes("/")) return s.toUpperCase();
  // MIME type fallback: extract last segment
  return s.split("/").pop()?.toUpperCase() || s;
};

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
