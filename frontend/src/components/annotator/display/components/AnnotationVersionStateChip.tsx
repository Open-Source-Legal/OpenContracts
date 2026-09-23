/**
 * AnnotationVersionStateChip — the quiet state chip a human annotation wears
 * when it lives on a superseded document version: Stale until a reviewer
 * re-approves, corrects or drops it against the newer text.
 *
 * Shared by the PDF and text renderers' label chips and by the carried-over
 * annotations review panel so the vocabulary stays identical everywhere.
 */
import React from "react";
import styled from "styled-components";
import { ANNOTATION_VERSION_STATE_META } from "../../../../assets/configurations/constants";

const Chip = styled.span<{ $color: string; $background: string }>`
  display: inline-flex;
  align-items: center;
  padding: 0 0.4rem;
  border-radius: 999px;
  font-size: 0.625rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1.5;
  color: ${(p) => p.$color};
  background: ${(p) => p.$background};
  white-space: nowrap;
`;

interface AnnotationVersionStateChipProps {
  state?: string | null;
  className?: string;
}

export const AnnotationVersionStateChip: React.FC<
  AnnotationVersionStateChipProps
> = ({ state, className }) => {
  if (!state) return null;
  const meta = ANNOTATION_VERSION_STATE_META[state];
  if (!meta) return null;
  return (
    <Chip
      className={className}
      $color={meta.color}
      $background={meta.background}
      title={meta.title}
      data-testid={`annotation-version-state-${state.toLowerCase()}`}
    >
      {meta.label}
    </Chip>
  );
};
