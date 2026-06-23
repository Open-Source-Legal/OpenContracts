/**
 * Shared styled-components for the Authority Console.
 *
 * These are lifted verbatim from the AuthorityMappings / AuthoritySourcesMonitor
 * panels (page shell, search box, facet select, icon buttons, badges, inputs)
 * so the console reuses the exact design-system chrome rather than re-deriving
 * it. The console-specific layout (left sidebar + tab nav) is defined here too,
 * as the single front-door shell that replaces the three panels' separate
 * Container/BackLink/PageHeader chrome.
 */
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { CORPUS_RADII } from "../../../corpuses/styles/corpusDesignTokens";
import { TONE_COLORS, Tone } from "./tones";

/* ---- page shell ---------------------------------------------------------- */

export const Container = styled.div`
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem 1.5rem 3rem;
`;

export const BackLink = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: none;
  background: none;
  padding: 0;
  margin-bottom: 1.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;

  &:hover {
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

export const PageHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
`;

export const PageTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin: 0;
  font-size: 1.5rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const PageSubtitle = styled.p`
  margin: 0.35rem 0 0;
  max-width: 46rem;
  font-size: 0.875rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/* ---- console layout: left tab rail + content ----------------------------- */

export const ConsoleLayout = styled.div`
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 1.75rem;

  @media (max-width: 880px) {
    grid-template-columns: 1fr;
  }
`;

export const TabRail = styled.nav`
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  position: sticky;
  top: 1rem;
  align-self: start;

  @media (max-width: 880px) {
    flex-direction: row;
    flex-wrap: wrap;
    position: static;
  }
`;

export const TabButton = styled.button<{ $active: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.55rem;
  width: 100%;
  text-align: left;
  padding: 0.55rem 0.75rem;
  font-size: 0.84rem;
  font-weight: ${(p) => (p.$active ? 700 : 500)};
  color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.textPrimary : OS_LEGAL_COLORS.textSecondary};
  background: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.surfaceLight : "transparent"};
  border: 1px solid
    ${(p) => (p.$active ? OS_LEGAL_COLORS.border : "transparent")};
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s ease, color 0.12s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }
`;

export const TabContent = styled.div`
  min-width: 0;
`;

/* ---- filter bar / search / select ---------------------------------------- */

export const FilterBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 1rem;
`;

export const SearchBox = styled.div`
  position: relative;
  display: flex;
  align-items: center;
  min-width: 220px;

  svg.lead {
    position: absolute;
    left: 0.55rem;
    width: 14px;
    height: 14px;
    color: ${OS_LEGAL_COLORS.textMuted};
    pointer-events: none;
  }

  input {
    width: 100%;
    padding: 0.45rem 1.6rem 0.45rem 1.8rem;
    font-size: 0.8125rem;
    color: ${OS_LEGAL_COLORS.textPrimary};
    background: ${OS_LEGAL_COLORS.surface};
    border: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 8px;
    outline: none;

    &:focus {
      border-color: ${OS_LEGAL_COLORS.primaryBlue};
    }
  }

  button.clear {
    position: absolute;
    right: 0.4rem;
    display: inline-flex;
    border: none;
    background: none;
    color: ${OS_LEGAL_COLORS.textMuted};
    cursor: pointer;
    padding: 2px;

    &:hover {
      color: ${OS_LEGAL_COLORS.textSecondary};
    }

    svg {
      width: 13px;
      height: 13px;
    }
  }
`;

export const Select = styled.select`
  padding: 0.45rem 0.6rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  cursor: pointer;

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

/* ---- inputs (create / edit) ---------------------------------------------- */

export const FieldLabel = styled.label`
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

export const KeyInput = styled.input`
  width: 100%;
  min-width: 120px;
  padding: 0.35rem 0.5rem;
  font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  outline: none;

  &:focus {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

export const TextInput = styled.input`
  width: 100%;
  min-width: 140px;
  padding: 0.35rem 0.5rem;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  outline: none;

  &:focus {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

export const CreateForm = styled.form`
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 0.6rem;
  margin-bottom: 1rem;
  padding: 0.85rem 1rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
`;

export const CreateField = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  flex: 1 1 150px;
`;

/* ---- row actions / icon button ------------------------------------------- */

export const IconButton = styled.button<{ $danger?: boolean }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
  border-radius: 6px;
  padding: 0.28rem;
  cursor: pointer;
  color: ${(p) =>
    p.$danger ? OS_LEGAL_COLORS.dangerText : OS_LEGAL_COLORS.textSecondary};
  transition: background 0.12s ease, border-color 0.12s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    border-color: ${(p) =>
      p.$danger ? OS_LEGAL_COLORS.dangerBorder : OS_LEGAL_COLORS.borderHover};
  }

  &:disabled {
    opacity: 0.5;
    cursor: default;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

export const RowActions = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
`;

/* ---- badges / cells ------------------------------------------------------ */

export const Badge = styled.span<{ $tone: Tone }>`
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.5rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.71875rem;
  font-weight: 600;
  white-space: nowrap;
  color: ${(p) => TONE_COLORS[p.$tone].fg};
  background: ${(p) => TONE_COLORS[p.$tone].bg};
  border: 1px solid ${(p) => TONE_COLORS[p.$tone].border};
`;

export const KeyCell = styled.span`
  font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const Muted = styled.span`
  color: ${OS_LEGAL_COLORS.textMuted};
  font-size: 0.8125rem;
`;

export const LoadMoreRow = styled.div`
  display: flex;
  justify-content: center;
  padding: 1rem 0 0;
`;

export const ClickableRowName = styled.button`
  border: none;
  background: none;
  padding: 0;
  font-weight: 600;
  font-size: 0.84rem;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  cursor: pointer;
  text-align: left;

  &:hover {
    text-decoration: underline;
  }
`;
