import { css } from "styled-components";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";

/**
 * Base border + padding for .oc-modal-footer.
 * Import and interpolate inside any modal's .oc-modal-footer block
 * so the treatment stays consistent across all modals.
 */
export const modalFooterBorder = css`
  border-top: 1px solid var(--oc-border-default);
  padding-top: var(--oc-spacing-lg);
`;

/**
 * Mobile-responsive sticky footer with column-reverse button layout.
 * Pairs with modalFooterBorder for the standard modal footer pattern.
 */
export const modalFooterMobile = css`
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: sticky;
    bottom: 0;
    flex-direction: column-reverse;
    gap: var(--oc-spacing-sm);
    padding-bottom: calc(
      var(--oc-spacing-lg) + env(safe-area-inset-bottom, 0px)
    );

    button {
      width: 100%;
      justify-content: center;
    }
  }
`;
