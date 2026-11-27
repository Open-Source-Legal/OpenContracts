import styled from "styled-components";

/**
 * The box a PDF/DOCX viewer fills. The viewer's root (`[data-rca-root]`) is
 * its own scroll container and takes the frame's height, so the frame's
 * parent (`ViewerContainer` with `$frame`) gives height without scrolling.
 * The root carries the padding the scrolling container used to have.
 */
export const ViewerFrame = styled.div`
  position: relative;
  flex: 1 1 0;
  min-height: 0;
  height: 100%;

  > [data-rca-root] {
    box-sizing: border-box;
    padding: 1rem;
    -webkit-overflow-scrolling: touch;

    @media (max-width: 768px) {
      padding: 0.75rem;
      scroll-padding: 1rem;
      overscroll-behavior-x: none;
    }
  }
`;
