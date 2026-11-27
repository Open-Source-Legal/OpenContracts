import { DocTypeAnnotation } from "../components/annotator/types/annotations";
import { ServerTokenAnnotation } from "../components/annotator/types/annotations";
import { ServerSpanAnnotation } from "../components/annotator/types/annotations";
import {
  BoundingBox,
  MultipageAnnotationJson,
  PageTokens,
  PermissionTypes,
  SpanAnnotationJson,
  Token,
} from "../components/types";
import {
  AnalyzerManifestType,
  LabelType,
  RawServerAnnotationType,
  ServerAnnotationType,
} from "../types/graphql-api";
import { PAWLS_COORDINATE_EPSILON } from "../assets/configurations/constants";
import { isSpanAnnotation } from "./annotationGuards";

// https://gist.github.com/JamieMason/0566f8412af9fe6a1d470aa1e089a752
export function groupBy<T extends Record<string, any>, K extends keyof T>(
  array: T[],
  key: K | { (obj: T): string }
): Record<string, T[]> {
  const keyFn = key instanceof Function ? key : (obj: T) => obj[key];
  return array.reduce(
    (objectsByKeyValue, obj) => {
      const value = keyFn(obj);
      objectsByKeyValue[value] = (objectsByKeyValue[value] || []).concat(obj);
      return objectsByKeyValue;
    },
    {} as Record<string, T[]>
  );
}

export function getPermissions(
  permissions: string[] | undefined
): PermissionTypes[] {
  // console.log("Get permissions represented by obj permissions", permissions);
  let base_permissions: PermissionTypes[] = [];
  if (permissions !== undefined) {
    for (var permission of permissions) {
      if (permission === "superuser") {
        base_permissions.push(PermissionTypes.CAN_UPDATE);
        base_permissions.push(PermissionTypes.CAN_CREATE);
        base_permissions.push(PermissionTypes.CAN_PUBLISH);
        base_permissions.push(PermissionTypes.CAN_READ);
        base_permissions.push(PermissionTypes.CAN_REMOVE);
        base_permissions.push(PermissionTypes.CAN_PERMISSION);
        base_permissions.push(PermissionTypes.CAN_COMMENT);
        break;
      } else if (
        (permission.includes("update_") || permission.includes("change_")) &&
        !base_permissions.includes(PermissionTypes.CAN_UPDATE)
      ) {
        // console.log("Include update");
        base_permissions.push(PermissionTypes.CAN_UPDATE);
      } else if (
        permission.includes("remove_") &&
        !base_permissions.includes(PermissionTypes.CAN_REMOVE)
      ) {
        base_permissions.push(PermissionTypes.CAN_REMOVE);
      } else if (
        (permission.includes("create_") || permission.includes("add_")) &&
        !base_permissions.includes(PermissionTypes.CAN_CREATE)
      ) {
        base_permissions.push(PermissionTypes.CAN_CREATE);
      } else if (
        permission.includes("publish_") &&
        !base_permissions.includes(PermissionTypes.CAN_PUBLISH)
      ) {
        base_permissions.push(PermissionTypes.CAN_PUBLISH);
      } else if (
        (permission.includes("read_") || permission.includes("view_")) &&
        !base_permissions.includes(PermissionTypes.CAN_READ)
      ) {
        base_permissions.push(PermissionTypes.CAN_READ);
      } else if (
        permission.includes("permission_") &&
        !base_permissions.includes(PermissionTypes.CAN_PERMISSION)
      ) {
        base_permissions.push(PermissionTypes.CAN_PERMISSION);
      } else if (
        permission.includes("comment_") &&
        !base_permissions.includes(PermissionTypes.CAN_COMMENT)
      ) {
        base_permissions.push(PermissionTypes.CAN_COMMENT);
      }
    }
  }
  // console.log("Resulting permissions", base_permissions);
  return base_permissions;
}

export function convertToDocTypeAnnotation(
  serverAnnotation: RawServerAnnotationType
): DocTypeAnnotation {
  // Check if the annotation is of the correct type
  if (serverAnnotation.annotationLabel.labelType !== "DOC_TYPE_LABEL") {
    throw new Error("Invalid annotation type. Expected DOC_TYPE_LABEL.");
  }

  // Transform raw permissions to frontend PermissionTypes
  const transformedPermissions = getPermissions(serverAnnotation.myPermissions);

  // Create and return a new DocTypeAnnotation instance
  return new DocTypeAnnotation(
    serverAnnotation.annotationLabel,
    transformedPermissions,
    serverAnnotation.id,
    serverAnnotation.versionState
  );
}

export function convertToDocTypeAnnotations(
  annotations: RawServerAnnotationType[]
): DocTypeAnnotation[] {
  return annotations
    .filter((ann) => ann.annotationLabel.labelType === LabelType.DocTypeLabel)
    .map((ann) => convertToDocTypeAnnotation(ann));
}

export function convertToServerAnnotation(
  annotation: RawServerAnnotationType,
  allowComments?: boolean
): ServerTokenAnnotation | ServerSpanAnnotation {
  const permissions = getPermissions(annotation.myPermissions);

  let approved = false;
  let rejected = false;
  if (annotation.userFeedback?.edges.length === 1) {
    approved =
      Boolean(annotation.userFeedback.edges[0]?.node?.approved) ?? false;
    rejected =
      Boolean(annotation.userFeedback.edges[0]?.node?.rejected) ?? false;
  }

  if (isSpanAnnotation(annotation)) {
    return new ServerSpanAnnotation(
      annotation.page,
      annotation.annotationLabel,
      annotation.rawText ?? "",
      annotation.structural ?? false,
      annotation.json,
      permissions,
      approved,
      rejected,
      allowComments ?? false,
      annotation.id,
      annotation.contentModalities,
      annotation.linkUrl ?? null,
      annotation.versionState
    );
  }

  // Fallback: treat as token annotation (MultipageAnnotationJson)
  // ServerTokenAnnotation handles v1/v2 format normalization internally.
  return new ServerTokenAnnotation(
    annotation.page,
    annotation.annotationLabel,
    annotation.rawText ?? "",
    annotation.structural ?? false,
    annotation.json ?? {},
    permissions,
    approved,
    rejected,
    allowComments ?? false,
    annotation.id,
    annotation.contentModalities,
    annotation.linkUrl ?? null,
    annotation.versionState
  );
}

// Helper function to convert an array of ServerAnnotationType to ServerAnnotation
export function convertToServerAnnotations(
  annotations: ServerAnnotationType[],
  allowComments?: boolean
): (ServerTokenAnnotation | ServerSpanAnnotation)[] {
  return annotations.map((annot) =>
    convertToServerAnnotation(annot, allowComments)
  );
}

export function getPageBoundsFromCanvas(
  canvas: HTMLCanvasElement
): BoundingBox {
  if (canvas.parentElement === null) {
    throw new Error("No canvas parent");
  }
  const parent = canvas.parentElement;
  const parentStyles = getComputedStyle(canvas.parentElement);

  const leftPadding = parseFloat(parentStyles.paddingLeft || "0");
  const left = parent.offsetLeft + leftPadding;

  const topPadding = parseFloat(parentStyles.paddingTop || "0");
  const top = parent.offsetTop + topPadding;

  const parentWidth =
    parent.clientWidth -
    leftPadding -
    parseFloat(parentStyles.paddingRight || "0");
  const parentHeight =
    parent.clientHeight -
    topPadding -
    parseFloat(parentStyles.paddingBottom || "0");
  return {
    left,
    top,
    right: left + parentWidth,
    bottom: top + parentHeight,
  };
}

/**
 * Normalizes PAWLs token coordinates to match PDF.js viewport coordinates.
 *
 * PAWLs tokens are extracted by the parser (e.g. Docling, pdfplumber) using its
 * own page dimension measurements. PDF.js computes its own page dimensions from
 * the PDF's MediaBox/CropBox/rotation. If these differ, token bounding boxes
 * drift progressively from the rendered PDF content.
 *
 * This function rescales token x/y/width/height so they align with the PDF.js
 * coordinate system at scale 1.
 *
 * @param pawlsPage  - The PAWLs page data containing `page` dimensions and `tokens`.
 * @param viewportWidth  - PDF.js viewport width at scale 1.
 * @param viewportHeight - PDF.js viewport height at scale 1.
 * @returns A new array of tokens with coordinates rescaled to the PDF.js
 *          coordinate system. If no rescaling is needed the original array is
 *          returned as-is (no unnecessary copies).
 */
export function normalizeTokensToPdfViewport(
  pawlsPage: PageTokens,
  viewportWidth: number,
  viewportHeight: number
): Token[] {
  const pawlsWidth = pawlsPage.page.width;
  const pawlsHeight = pawlsPage.page.height;

  // Cannot rescale if PAWLs or viewport reports zero dimensions (malformed data).
  if (
    pawlsWidth === 0 ||
    pawlsHeight === 0 ||
    viewportWidth === 0 ||
    viewportHeight === 0
  ) {
    return pawlsPage.tokens;
  }

  // If dimensions match (within a tiny epsilon) no rescaling is needed.
  if (
    Math.abs(pawlsWidth - viewportWidth) < PAWLS_COORDINATE_EPSILON &&
    Math.abs(pawlsHeight - viewportHeight) < PAWLS_COORDINATE_EPSILON
  ) {
    return pawlsPage.tokens;
  }

  const scaleX = viewportWidth / pawlsWidth;
  const scaleY = viewportHeight / pawlsHeight;

  return pawlsPage.tokens.map((t) => ({
    ...t,
    x: t.x * scaleX,
    y: t.y * scaleY,
    width: t.width * scaleX,
    height: t.height * scaleY,
  }));
}

/**
 * Resolves the token array for a single PDF page given the full PAWLs dataset.
 *
 * Validates the PAWLs data for the requested page index and, when valid,
 * normalizes token coordinates to the PDF.js viewport coordinate space via
 * {@link normalizeTokensToPdfViewport}.
 *
 * @param pawlsData - The full PAWLs dataset (array of per-page token data).
 * @param pageIndex - Zero-based page index into `pawlsData`.
 * @param viewportWidth  - PDF.js viewport width at scale 1.
 * @param viewportHeight - PDF.js viewport height at scale 1.
 * @param pageNum - One-based page number (used only for log messages).
 * @returns The resolved (and possibly rescaled) token array for the page.
 */
export function resolvePageTokens(
  pawlsData: PageTokens[] | null | undefined,
  pageIndex: number,
  viewportWidth: number,
  viewportHeight: number,
  pageNum: number
): Token[] {
  if (
    !pawlsData ||
    !Array.isArray(pawlsData) ||
    pageIndex >= pawlsData.length
  ) {
    console.warn(
      `Page ${pageNum}: PAWLS data index out of bounds. Index: ${pageIndex}, Length: ${
        pawlsData?.length ?? 0
      }`
    );
    return [];
  }

  const pageData = pawlsData[pageIndex];

  if (!pageData) {
    return [];
  }
  if (typeof pageData.tokens === "undefined") {
    return [];
  }
  if (!Array.isArray(pageData.tokens)) {
    console.error(
      `Page ${pageNum}: CRITICAL - pageData.tokens is not an array at index ${pageIndex}! Type: ${typeof pageData.tokens}`
    );
    return [];
  }

  return normalizeTokensToPdfViewport(pageData, viewportWidth, viewportHeight);
}
