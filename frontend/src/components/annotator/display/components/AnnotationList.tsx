import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import "../../sidebar/AnnotatorSidebar.css";
import { useAnnotationRefs } from "../../hooks/useAnnotationRefs";
import { usePdfAnnotations } from "../../hooks/AnnotationHooks";
import {
  useAnnotationControls,
  useAnnotationDisplay,
  useAnnotationSelection,
} from "../../context/UISettingsAtom";
import { useDeleteAnnotation } from "../../hooks/AnnotationHooks";
import { HighlightItem } from "../../sidebar/HighlightItem";
import { FetchMoreOnVisible } from "../../../widgets/infinite_scroll/FetchMoreOnVisible";
import { PlaceholderCard } from "../../../placeholders/PlaceholderCard";
import { useVisibleAnnotations } from "../../hooks/useVisibleAnnotations";
import { useAllRelations } from "../../hooks/useAllRelations";

interface AnnotationListProps {
  /** read-only mode flag */
  read_only: boolean;
  /** fetch next page when list bottom becomes visible */
  fetchMore?: () => Promise<void>;
}

/* --- presentation ---------------------------------------------------- */
const ListViewport = styled.div`
  flex: 1 1 auto;
  overflow-y: auto;

  /* pretty scrollbar */
  &::-webkit-scrollbar {
    width: 8px;
  }
  &::-webkit-scrollbar-track {
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 4px;
    &:hover {
      background: ${OS_LEGAL_COLORS.textMuted};
    }
  }
`;

const DEFAULT_ROW_HEIGHT = 64; // px – used until we can measure
const OVERSCAN_ROWS = 4; // rows rendered above / below viewport

/* --------------------------------------------------------------------- */
/* main component                                                        */
/* --------------------------------------------------------------------- */
export const AnnotationList: React.FC<AnnotationListProps> = ({
  read_only,
  fetchMore,
}) => {
  /* ------------ data -------------------------------------------------- */
  const { pdfAnnotations } = usePdfAnnotations();
  // Includes structural relations once they're lazily loaded — needed by
  // HighlightItem to render the input/output relation badges for structural
  // annotations the user may have toggled on.
  const allRelations = useAllRelations();
  const { selectedAnnotations, setSelectedAnnotations } =
    useAnnotationSelection();
  const { showStructural } = useAnnotationDisplay();
  const { spanLabelsToView } = useAnnotationControls();

  const visibleAnnotations = useVisibleAnnotations();
  const rowCount = visibleAnnotations.length + (fetchMore ? 1 : 0);

  /* ------------ size bookkeeping ------------------------------------- */
  const [rowHeights, setRowHeights] = useState<number[]>(
    new Array(rowCount).fill(DEFAULT_ROW_HEIGHT)
  );

  /* keep the array length in sync with rowCount */
  useEffect(() => {
    setRowHeights((prev) => {
      if (prev.length === rowCount) return prev;
      const next = [...prev];
      while (next.length < rowCount) next.push(DEFAULT_ROW_HEIGHT);
      return next.slice(0, rowCount); // shrink if necessary
    });
  }, [rowCount]);

  const cumulative = useMemo<number[]>(() => {
    const out: number[] = [0];
    for (let i = 0; i < rowHeights.length; i++) {
      out.push(out[i] + rowHeights[i]);
    }
    return out;
  }, [rowHeights]);

  const containerHeight = cumulative[cumulative.length - 1];

  /* ------------ visible-range calculation ----------------------------- */
  const viewportRef = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState<[number, number]>([0, 15]); // initial

  const updateRange = useCallback(() => {
    const vp = viewportRef.current;
    if (!vp) return;

    const scrollTop = vp.scrollTop;
    const vpHeight = vp.clientHeight;

    /* first & last fully / partially visible rows */
    let first = 0;
    while (first < rowCount && cumulative[first + 1] <= scrollTop) first++;

    let last = first;
    while (last < rowCount && cumulative[last] < scrollTop + vpHeight) last++;
    last = Math.min(last, rowCount - 1);

    const start = Math.max(0, first - OVERSCAN_ROWS);
    const end = Math.min(rowCount - 1, last + OVERSCAN_ROWS);

    if (start !== range[0] || end !== range[1]) setRange([start, end]);
  }, [cumulative, rowCount, range]);

  /* attach scroll listener */
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    updateRange(); // initial
    const onScroll = () => requestAnimationFrame(updateRange);

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [updateRange]);

  /* recalc when heights change */
  useEffect(updateRange, [cumulative, updateRange]);

  /* ------------ helpers ---------------------------------------------- */
  const { annotationElementRefs } = useAnnotationRefs();
  const handleDeleteAnnotation = useDeleteAnnotation();

  const scrollToRow = (idx: number) => {
    const vp = viewportRef.current;
    if (!vp) return;
    vp.scrollTo({
      top: Math.max(0, cumulative[idx] - 0.5 * vp.clientHeight),
      behavior: "smooth",
    });
  };

  const toggleSelection = (id: string) => {
    if (selectedAnnotations.includes(id)) {
      setSelectedAnnotations(selectedAnnotations.filter((x) => x !== id));
    } else {
      setSelectedAnnotations([...selectedAnnotations, id]);
      const idx = visibleAnnotations.findIndex((a) => a.id === id);
      if (idx !== -1) scrollToRow(idx);
    }
  };

  /* ------------ row component ---------------------------------------- */
  const Row: React.FC<{ index: number }> = ({ index }) => {
    /* infinite-scroll sentinel */
    if (index === visibleAnnotations.length && fetchMore) {
      return (
        <FetchMoreOnVisible fetchNextPage={fetchMore} fetchWithoutMotion />
      );
    }

    const annotation = visibleAnnotations[index];

    const ref = useCallback(
      (el: HTMLLIElement | null) => {
        if (!el) return;
        const measured = Math.round(el.getBoundingClientRect().height);

        // update ONLY if row had not been measured before
        setRowHeights((prev) => {
          if (index >= prev.length) return prev;
          if (prev[index] !== DEFAULT_ROW_HEIGHT) return prev; // already stable
          if (Math.abs(prev[index] - measured) < 1) return prev; // same
          const next = [...prev];
          next[index] = measured;
          return next;
        });
      },
      [index]
    );

    return (
      <li ref={ref} style={{ width: "100%" }}>
        <HighlightItem
          annotation={annotation}
          relations={allRelations}
          read_only={read_only}
          onSelect={toggleSelection}
          onDelete={handleDeleteAnnotation}
        />
      </li>
    );
  };

  /* ------------------------------------------------------------------ */
  /* render                                                             */
  /* ------------------------------------------------------------------ */
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <ListViewport ref={viewportRef}>
        {/* ---------------- case: no matching annotations --------------- */}
        {visibleAnnotations.length === 0 ? (
          <PlaceholderCard
            style={{ margin: "1rem" }}
            title="No Matching Annotations Found"
            description="No annotations match the currently selected labels or filters."
          />
        ) : (
          /* --------------- case: virtualised list --------------------- */
          <div style={{ position: "relative", height: containerHeight }}>
            {Array.from({ length: range[1] - range[0] + 1 }, (_, i) => {
              const rowIdx = range[0] + i;
              if (
                rowIdx >= visibleAnnotations.length &&
                !(rowIdx === visibleAnnotations.length && fetchMore)
              ) {
                return null;
              }
              return (
                <div
                  key={rowIdx}
                  style={{
                    position: "absolute",
                    top: cumulative[rowIdx],
                    width: "100%",
                  }}
                >
                  <Row index={rowIdx} />
                </div>
              );
            })}
          </div>
        )}
      </ListViewport>
    </div>
  );
};
