/**
 * The PDF viewer: `@os-legal/react-contract-annotate`'s `PdfAnnotator` on the
 * document and PAWLS tokens OpenContracts has already loaded
 * (`useDocumentLoader`), bound to OpenContracts' state by
 * `useViewerBindings`.
 */
import React, { useEffect, useMemo } from "react";
import { useAtom } from "jotai";
import { PdfAnnotator } from "@os-legal/react-contract-annotate/pdf";

import { computeFitToWidthZoom } from "../../../../utils/pdfZoom";
import { toViewerPawls } from "../../bindings/convert";
import { useViewerBindings } from "../../bindings/useViewerBindings";
import { ViewerFrame } from "../../bindings/ViewerFrame";
import { usePages, usePdfDoc } from "../../context/DocumentAtom";
import { initialZoomSetAtom, useZoomLevel } from "../../context/UISettingsAtom";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../../types/annotations";

interface PdfAnnotatorWrapperProps {
  readOnly: boolean;
  /** Measured width of the viewer container, for the initial fit-to-width. */
  containerWidth?: number | null;
  createAnnotation: (
    annotation: ServerTokenAnnotation | ServerSpanAnnotation
  ) => Promise<void>;
  /** Creates an OC_URL link annotation; enables "Add link…". */
  createUrlAnnotation?: (
    annotation: ServerTokenAnnotation,
    url: string
  ) => Promise<void>;
}

const PdfAnnotatorWrapper: React.FC<PdfAnnotatorWrapperProps> = ({
  readOnly,
  containerWidth,
  createAnnotation,
  createUrlAnnotation,
}) => {
  const { pdfDoc } = usePdfDoc();
  const { pages } = usePages();
  const { setZoomLevel } = useZoomLevel();
  const [initialZoomSet, setInitialZoomSet] = useAtom(initialZoomSetAtom);

  const { props, handleRef, dialogs } = useViewerBindings({
    format: "pdf",
    readOnly,
    createAnnotation,
    createUrlAnnotation,
  });

  const pageInfos = useMemo(
    () =>
      Object.values(pages).sort(
        (a, b) => a.page.pageNumber - b.page.pageNumber
      ),
    [pages]
  );
  const pawls = useMemo(() => toViewerPawls(pageInfos), [pageInfos]);
  const source = useMemo(
    () => (pdfDoc ? { document: pdfDoc } : null),
    [pdfDoc]
  );

  // The first fit to the container's width, once both are known. Uses
  // OpenContracts' margin (issue #1736), which the library's own
  // "fit-width" does not know about.
  const firstPage = pageInfos[0]?.page;
  useEffect(() => {
    if (initialZoomSet || !containerWidth || !firstPage) return;
    const zoom = computeFitToWidthZoom(
      firstPage.getViewport({ scale: 1 }).width,
      containerWidth
    );
    if (zoom !== null) {
      setZoomLevel(zoom);
      setInitialZoomSet(true);
    }
  }, [
    initialZoomSet,
    containerWidth,
    firstPage,
    setZoomLevel,
    setInitialZoomSet,
  ]);

  if (!source || pageInfos.length === 0) return null;

  return (
    <ViewerFrame data-testid="pdf-annotator">
      <PdfAnnotator ref={handleRef} source={source} pawls={pawls} {...props} />
      {dialogs}
    </ViewerFrame>
  );
};

export default React.memo(PdfAnnotatorWrapper);
