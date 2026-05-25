import styled, { css } from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SHADOWS,
  OS_LEGAL_SPACING,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import {
  COOKIE_CONSENT_GRID_BREAKPOINT,
  MOBILE_VIEW_BREAKPOINT,
} from "../../assets/configurations/constants";
import { useMutation, useReactiveVar } from "@apollo/client";
import { toast } from "react-toastify";
import {
  AlertTriangle,
  Users,
  Settings,
  Monitor,
  BarChart3,
  MousePointer,
  Bug,
  Check,
  Shield,
  FileText,
  Share2,
} from "lucide-react";
import {
  Button,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";

import { showCookieAcceptModal, userObj } from "../../graphql/cache";
import {
  ACCEPT_COOKIE_CONSENT,
  AcceptCookieConsentInputs,
  AcceptCookieConsentOutputs,
} from "../../graphql/mutations";
import {
  setAnalyticsConsent,
  isPostHogConfigured,
} from "../../utils/analytics";
import { CiteMark } from "../brand/CiteMark";

/**
 * CookieConsentDialog — cite rebrand.
 *
 * The modal retains every piece of information from the OpenContracts-era
 * version (demo-system caveat, cookie usage explainer, "data we collect",
 * "data you agree to share", analytics breakdown when PostHog is wired
 * up, MIT-style disclaimer). The visual language was rewritten against
 * the cite brand system: Source Serif 4 for display copy, slate/teal/
 * warm-paper palette only, sentence-case titles, the [•] icon mark
 * instead of decorative badges, no warning-yellow demo banner, and a
 * navy primary button per the brand spec (navy chrome for primary CTAs,
 * teal reserved for accent / links / active states).
 */

// Brand-correct typography stacks. OS_LEGAL_TYPOGRAPHY.fontFamilySerif
// now carries the cite Source Serif 4 / Source Serif Pro / Georgia chain
// (the legacy Georgia-first stack was upgraded as part of the v3 rebrand
// so this dialog inherits the new wordmark style automatically). The
// sans block adds "Segoe UI" before the system fallback to match the
// Windows rendering target the original dialog targeted.
const sansFont = css`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
`;

const serifFont = css`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
`;

/**
 * Global CSS overrides for the @os-legal/ui Modal classes when used by
 * the cookie consent dialog. The Modal renders its body via
 * `createPortal(content, document.body)` — that takes the rendered DOM
 * out of any styled-components wrapper, so selectors like
 * `.oc-modal-overlay` or `.oc-button--primary` can't be scoped to a
 * styled.div parent the way styled-components 6 normally arranges them.
 * Inline these as a plain stylesheet (NavMenu uses the same pattern
 * for its `.oc-navbar` overrides) and they apply correctly to the
 * portaled DOM.
 *
 * Scoped via the `cookie-consent-modal` / `cookie-consent-overlay`
 * classes passed through the Modal's `className` / `overlayClassName`
 * props (see the JSX below). Every selector here is qualified with one
 * of those classes so these rules can never bleed into another consumer
 * of the same @os-legal/ui Modal.
 */
const cookieModalCss = `
  /* Overlay is the modal's parent in the portal tree, scoped via the
     overlayClassName prop on <Modal> below. */
  .cookie-consent-overlay {
    z-index: 2000;
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-overlay { padding: 0; }
  }

  .cookie-consent-modal.oc-modal {
    max-width: ${OS_LEGAL_SPACING.modalMaxWidth};
    width: calc(100vw - ${OS_LEGAL_SPACING.modalSideGutter});
    border-radius: 8px;
    box-shadow: ${OS_LEGAL_SHADOWS.modalOverlay};
    background: ${OS_LEGAL_COLORS.warmPaper};
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-modal.oc-modal {
      width: 100%;
      max-width: 100%;
      max-height: 100vh;
      max-height: 100dvh;
      border-radius: 0;
      display: flex;
      flex-direction: column;
    }
  }

  .cookie-consent-modal .oc-modal-header {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
    padding: 1.5rem 1.75rem 1.25rem;
    background: ${OS_LEGAL_COLORS.warmPaper};
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-modal .oc-modal-header {
      padding: 1.125rem 1.125rem 1rem;
      flex-shrink: 0;
    }
  }

  .cookie-consent-modal .oc-modal-header__title {
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
    font-size: 1.625rem;
    font-weight: 400;
    line-height: 1.15;
    letter-spacing: -0.5px;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-modal .oc-modal-header__title {
      font-size: 1.3125rem;
      letter-spacing: -0.4px;
    }
  }

  .cookie-consent-modal .oc-modal-body {
    padding: 1.5rem 1.75rem 1.5rem;
    background: ${OS_LEGAL_COLORS.warmPaper};
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-modal .oc-modal-body {
      padding: 1.125rem 1.125rem 1.25rem;
      flex: 1 1 auto;
      overflow-y: auto;
    }
  }

  .cookie-consent-modal .oc-modal-footer {
    padding: 1rem 1.75rem;
    display: flex;
    justify-content: flex-end;
    background: ${OS_LEGAL_COLORS.warmPaper};
    border-top: 1px solid ${OS_LEGAL_COLORS.border};
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-modal .oc-modal-footer {
      padding: 0.875rem 1.125rem;
      padding-bottom: calc(0.875rem + env(safe-area-inset-bottom, 0px));
      box-shadow: ${OS_LEGAL_SHADOWS.footerLiftMobile};
      flex-shrink: 0;
    }
  }

  /* Override the @os-legal/ui primary Button to the brand navy chrome.
     Teal stays reserved for accent / links / active states per the cite
     brand system. */
  .cookie-consent-modal .oc-modal-footer .oc-button.oc-button--primary {
    background: ${OS_LEGAL_COLORS.ink};
    color: ${OS_LEGAL_COLORS.warmPaper};
    font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
    font-weight: 500;
    letter-spacing: 0;
    border-radius: 6px;
    padding: 0.625rem 1.125rem;
    transition: background 0.15s ease;
  }
  .cookie-consent-modal .oc-modal-footer .oc-button.oc-button--primary:hover:not(:disabled):not(.oc-button--loading),
  .cookie-consent-modal .oc-modal-footer .oc-button.oc-button--primary:focus-visible {
    background: ${OS_LEGAL_COLORS.inkHover};
  }
  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    .cookie-consent-modal .oc-modal-footer .oc-button.oc-button--primary {
      width: 100%;
      height: 48px;
      font-size: 0.9375rem;
    }
  }
`;

const TitleColumn = styled.span`
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
`;

const Eyebrow = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 10px;
    letter-spacing: 0.5px;
  }
`;

const DemoBanner = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 0.875rem 1rem;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-left: 3px solid ${OS_LEGAL_COLORS.accent};
  border-radius: 6px;
  margin-bottom: 1.5rem;

  > svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.textPrimary};
    margin-top: 2px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.75rem 0.875rem;
    gap: 10px;
    margin-bottom: 1.25rem;
  }
`;

const DemoBannerText = styled.p`
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
  ${sansFont}

  strong {
    font-weight: 500;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const LeadSection = styled.section`
  margin: 0 0 1.5rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin: 0 0 1.25rem;
  }
`;

const SectionLabel = styled.h4`
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 0.5rem;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: ${OS_LEGAL_COLORS.textMuted};
  ${sansFont}

  svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 10px;
    letter-spacing: 0.5px;
  }
`;

const LeadBody = styled.p`
  margin: 0;
  ${serifFont}
  font-size: 1rem;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textPrimary};

  em {
    font-style: italic;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.9375rem;
    line-height: 1.55;
  }
`;

const TwoColumnGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.5rem;

  @media (max-width: ${COOKIE_CONSENT_GRID_BREAKPOINT}px) {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-bottom: 1.25rem;
  }
`;

const DataCard = styled.section`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 1rem 1.125rem 1.125rem;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;

  &.cookie-consent__analytics {
    margin-bottom: 1.5rem;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.875rem 0.875rem 0.9375rem;
    gap: 0.5rem;
    /* Brand: shadows are subtle to absent. Cards sit on the page
       with a 1px border only — no elevation. */

    &.cookie-consent__analytics {
      margin-bottom: 1.25rem;
    }
  }
`;

const DataCardLead = styled.p`
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
  ${sansFont}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.8125rem;
    line-height: 1.45;
  }
`;

const DataList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    gap: 5px;
  }
`;

const DataListItem = styled.li`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  line-height: 1.4;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: transparent;
  border-radius: 4px;
  ${sansFont}

  svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    /* On mobile, soften with a slate-tinted surface so the rows
       remain scannable inside the body. */
    padding: 0.5625rem 0.625rem;
    gap: 8px;
    background: ${OS_LEGAL_COLORS.surfaceLight};

    svg {
      width: 14px;
      height: 14px;
    }
  }
`;

const AnalyticsNote = styled.p`
  margin: 0.125rem 0 0;
  font-size: 0.75rem;
  line-height: 1.55;
  color: ${OS_LEGAL_COLORS.textMuted};
  ${sansFont}
`;

const DisclaimerBlock = styled.aside`
  padding: 0.875rem 1rem;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.75rem 0.875rem;
  }
`;

const DisclaimerLabel = styled.span`
  display: block;
  margin-bottom: 0.375rem;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const Disclaimer = styled.p`
  margin: 0;
  /* 12px keeps the legal disclaimer at the WCAG-recommended minimum.
     ALL CAPS is preserved here — it's a legal-text convention used in
     the MIT-style warranty disclaimer the project ships under, not
     emphatic marketing copy. */
  font-size: 0.75rem;
  line-height: 1.6;
  letter-spacing: 0.02em;
  color: ${OS_LEGAL_COLORS.textMuted};
  ${sansFont}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.6875rem;
    line-height: 1.55;
  }
`;

export const CookieConsentDialog = () => {
  const currentUser = useReactiveVar(userObj);
  // Use userObj for auth check - consistent with NavMenu pattern
  const isAuthenticated = Boolean(currentUser);
  const analyticsEnabled = isPostHogConfigured();

  const [acceptCookieConsent, { loading }] = useMutation<
    AcceptCookieConsentOutputs,
    AcceptCookieConsentInputs
  >(ACCEPT_COOKIE_CONSENT, {
    onCompleted: (data) => {
      if (data.acceptCookieConsent.ok) {
        toast.success("Consent recorded");
        // Enable analytics tracking
        setAnalyticsConsent(true);
        showCookieAcceptModal(false);
      } else {
        toast.error(
          `Failed to record consent: ${data.acceptCookieConsent.message}`
        );
        // Still close the modal and set localStorage as fallback
        localStorage.setItem("oc_cookieAccepted", "true");
        setAnalyticsConsent(true);
        showCookieAcceptModal(false);
      }
    },
    onError: (error) => {
      toast.error(`Error recording consent: ${error.message}`);
      // Still close the modal and set localStorage as fallback
      localStorage.setItem("oc_cookieAccepted", "true");
      setAnalyticsConsent(true);
      showCookieAcceptModal(false);
    },
  });

  const handleAccept = () => {
    if (isAuthenticated) {
      // For authenticated users, call the mutation
      acceptCookieConsent();
    } else {
      // For anonymous users, use localStorage only
      localStorage.setItem("oc_cookieAccepted", "true");
      setAnalyticsConsent(true);
      showCookieAcceptModal(false);
    }
  };

  return (
    <>
      <style>{cookieModalCss}</style>
      <Modal
        open
        onClose={() => {}}
        className="cookie-consent-modal"
        overlayClassName="cookie-consent-overlay"
      >
        <ModalHeader
          title={
            <TitleColumn>
              <Eyebrow>
                <CiteMark size={12} ariaLabel="" />
                Privacy
              </Eyebrow>
              Cookies and terms
            </TitleColumn>
          }
        />
        <ModalBody>
          {/* role="note" surfaces the demo-system caveat as an ancillary
              advisory inside the dialog's reading order. role="alert"
              would double-announce on top of the dialog open event — the
              banner is informational, not time-sensitive. */}
          <DemoBanner role="note">
            <AlertTriangle size={18} aria-hidden="true" />
            <DemoBannerText>
              <strong>Demo system.</strong> No guarantee of uptime or data
              retention — accounts and data may be deleted at any time.
            </DemoBannerText>
          </DemoBanner>

          <LeadSection>
            <SectionLabel>
              <Shield size={14} />
              Cookie usage
            </SectionLabel>
            <LeadBody>
              <em>cite</em> uses cookies to enhance your experience and help us
              improve the platform. We do not sell or share user information.
            </LeadBody>
          </LeadSection>

          <TwoColumnGrid>
            <DataCard>
              <SectionLabel>
                <FileText size={14} />
                Data we collect
              </SectionLabel>
              <DataList>
                <DataListItem>
                  <Users size={14} />
                  User information (email, name, IP)
                </DataListItem>
                <DataListItem>
                  <Settings size={14} />
                  Usage information
                </DataListItem>
                <DataListItem>
                  <Monitor size={14} />
                  System information
                </DataListItem>
              </DataList>
            </DataCard>

            <DataCard>
              <SectionLabel>
                <Share2 size={14} />
                Data you agree to share
              </SectionLabel>
              <DataCardLead>
                By using this demo, you agree to share the following under a CC0
                1.0 Universal license:
              </DataCardLead>
              <DataList>
                <DataListItem>
                  <Users size={14} />
                  Labelsets &amp; labels
                </DataListItem>
                <DataListItem>
                  <Monitor size={14} />
                  Configured data extractors
                </DataListItem>
              </DataList>
            </DataCard>
          </TwoColumnGrid>

          {analyticsEnabled && (
            <DataCard className="cookie-consent__analytics">
              <SectionLabel>
                <BarChart3 size={14} />
                Analytics
              </SectionLabel>
              <DataCardLead>
                We use PostHog to collect anonymous usage analytics:
              </DataCardLead>
              <DataList>
                <DataListItem>
                  <BarChart3 size={14} />
                  Page views and navigation patterns
                </DataListItem>
                <DataListItem>
                  <MousePointer size={14} />
                  Feature usage statistics
                </DataListItem>
                <DataListItem>
                  <Bug size={14} />
                  Error tracking for debugging
                </DataListItem>
              </DataList>
              <AnalyticsNote>
                Analytics data is used solely to improve <em>cite</em> and is
                never sold or shared with third parties. You can opt out at any
                time through your browser settings or by using Do Not Track.
              </AnalyticsNote>
            </DataCard>
          )}

          <DisclaimerBlock>
            <DisclaimerLabel>Warranty disclaimer</DisclaimerLabel>
            <Disclaimer>
              THE SOFTWARE IS PROVIDED &ldquo;AS IS&rdquo;, WITHOUT WARRANTY OF
              ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
              WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE
              AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
              HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
              WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
              OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
              DEALINGS IN THE SOFTWARE.
            </Disclaimer>
          </DisclaimerBlock>
        </ModalBody>
        <ModalFooter>
          <Button
            variant="primary"
            loading={loading}
            disabled={loading}
            leftIcon={<Check size={16} />}
            onClick={handleAccept}
          >
            Accept and continue
          </Button>
        </ModalFooter>
      </Modal>
    </>
  );
};
