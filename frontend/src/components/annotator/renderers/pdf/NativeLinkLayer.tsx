import { useEffect, useMemo, useState, type FC } from "react";
import styled from "styled-components";
import { PDFPageProxy } from "pdfjs-dist/types/src/display/api";

import { Z_INDEX } from "../../../../assets/configurations/constants";

/**
 * Renders PDF.js native link annotations (URLs embedded in the PDF) as
 * transparent <a> elements positioned over their canvas-painted rectangles.
 *
 * The custom annotation system intercepts every mouse event on a page via the
 * full-page SelectionLayer overlay, so native links — which exist only as
 * pixels in the canvas raster — would otherwise be unclickable. Stacking
 * real anchors above the SelectionLayer lets the browser handle the click
 * before the selection logic ever sees it, and gives us right-click "open in
 * new tab", keyboard focus, and screen-reader support for free.
 */
interface NativeLink {
  id: string;
  url: string;
  left: number;
  top: number;
  width: number;
  height: number;
}

interface NativeLinkLayerProps {
  page: PDFPageProxy;
  scale: number;
}

const SAFE_URL_PROTOCOLS = ["http:", "https:", "mailto:"];

const isSafeUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    return SAFE_URL_PROTOCOLS.includes(parsed.protocol);
  } catch {
    return false;
  }
};

type PdfRect = [number, number, number, number];

export const NativeLinkLayer: FC<NativeLinkLayerProps> = ({ page, scale }) => {
  const [rawLinks, setRawLinks] = useState<
    { id: string; url: string; rect: PdfRect }[]
  >([]);

  useEffect(() => {
    // Clear stale positions immediately so a recycled component instance
    // (or a future page-prop swap) does not briefly render the previous
    // page's links before the async fetch resolves.
    setRawLinks([]);
    let cancelled = false;
    (async () => {
      try {
        const annotations = (await page.getAnnotations()) as Array<{
          id: string;
          subtype?: string;
          url?: string;
          rect?: number[];
        }>;
        if (cancelled) return;
        const collected: { id: string; url: string; rect: PdfRect }[] = [];
        for (const ann of annotations) {
          // ``ann.url`` absent → dest-based intra-document link, out of
          // scope for this overlay (no external navigation target).
          // TODO: hook in dest-based navigation here so PDF table-of-contents
          // links can scroll to their target page.
          if (
            ann.subtype !== "Link" ||
            !ann.url ||
            !ann.rect ||
            ann.rect.length !== 4 ||
            !isSafeUrl(ann.url)
          ) {
            continue;
          }
          collected.push({
            id: ann.id,
            url: ann.url,
            rect: ann.rect as PdfRect,
          });
        }
        setRawLinks(collected);
      } catch (err) {
        console.warn("Failed to read native PDF link annotations:", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [page]);

  const links: NativeLink[] = useMemo(() => {
    if (rawLinks.length === 0) return [];
    const viewport = page.getViewport({ scale });
    return rawLinks.map(({ id, url, rect }) => {
      const [x1, y1, x2, y2] = viewport.convertToViewportRectangle(rect);
      return {
        id,
        url,
        left: Math.min(x1, x2),
        top: Math.min(y1, y2),
        width: Math.abs(x2 - x1),
        height: Math.abs(y2 - y1),
      };
    });
  }, [rawLinks, page, scale]);

  if (links.length === 0) return null;

  return (
    <LinkOverlay data-testid="native-link-layer">
      {links.map((link) => (
        <NativeLinkAnchor
          key={link.id}
          href={link.url}
          target="_blank"
          rel="noopener noreferrer"
          title={link.url}
          aria-label={link.url}
          style={{
            left: link.left,
            top: link.top,
            width: link.width,
            height: link.height,
          }}
        />
      ))}
    </LinkOverlay>
  );
};

const LinkOverlay = styled.div`
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: ${Z_INDEX.PDF_NATIVE_LINK_LAYER};
`;

const NativeLinkAnchor = styled.a`
  position: absolute;
  pointer-events: auto;
  cursor: pointer;
  background: transparent;
  text-decoration: none;

  &:hover {
    background: rgba(0, 120, 215, 0.12);
    outline: 1px solid rgba(0, 120, 215, 0.4);
  }

  &:focus-visible {
    outline: 2px solid rgba(0, 120, 215, 0.7);
    outline-offset: 1px;
  }
`;
