import styled from "styled-components";

export const PDFContainer = styled.div<{ width?: number }>(
  ({ width }) => `
    overflow-y: scroll;
    overflow-x: scroll;
    height: calc(100vh - 120px);
    min-height: 0;
    box-sizing: border-box;
    background: #f7f9f9;
    padding: 1rem;
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 1;
    -webkit-overflow-scrolling: touch; /* Enable smooth scrolling on iOS */

    @media (max-width: 768px) {
      padding: 0.5rem;
      width: 100%;
      min-width: 100%;
      height: 100%; /* Use full height of parent container on mobile */
      max-height: 100%;
      min-height: 0;
      flex: 1 1 0;
      overflow-x: auto;
      overflow-y: auto;
      /* Ensure content can be scrolled fully into view */
      scroll-padding: 1rem;
      /* Prevent any horizontal bounce/rubber-band effect */
      overscroll-behavior-x: none;
    }
  `
);
