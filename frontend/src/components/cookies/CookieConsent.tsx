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
import {
  modalFooterBorder,
  modalFooterMobile,
} from "../widgets/modals/sharedModalStyles";
import { useMutation, useReactiveVar } from "@apollo/client";
import { toast } from "react-toastify";
import {
  AlertTriangle,
  Cookie,
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

const sansFont = css`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
`;

const serifFont = css`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
`;

const StyledModalWrapper = styled.div`
  .oc-modal-overlay {
    z-index: 2000;
    backdrop-filter: blur(4px);

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: 0;
    }
  }

  .oc-modal {
    max-width: ${OS_LEGAL_SPACING.modalMaxWidth};
    width: calc(100vw - ${OS_LEGAL_SPACING.modalSideGutter});
    border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};
    box-shadow: ${OS_LEGAL_SHADOWS.modalOverlay};

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      width: 100%;
      max-width: 100%;
      max-height: 100vh;
      max-height: 100dvh;
      border-radius: 0;
      display: flex;
      flex-direction: column;
    }
  }

  .oc-modal-header {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
    padding: 1.5rem 1.75rem;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: 1rem 1.125rem;
      flex-shrink: 0;
    }
  }

  .oc-modal-header__title {
    ${serifFont}
    font-size: 1.5rem;
    font-weight: 400;
    line-height: 1.2;
    color: ${OS_LEGAL_COLORS.textPrimary};

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      font-size: 1.1875rem;
      letter-spacing: -0.005em;
    }
  }

  .oc-modal-body {
    padding: 1.5rem 1.75rem 1.25rem;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: 1rem 1.125rem 1.25rem;
      flex: 1 1 auto;
      overflow-y: auto;
      background: ${OS_LEGAL_COLORS.background};
    }
  }

  .oc-modal-footer {
    ${modalFooterBorder}
    ${modalFooterMobile}
    padding: 1rem 1.75rem;
    display: flex;
    justify-content: flex-end;

    @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
      padding: 0.875rem 1.125rem;
      /* bottom intentionally overrides the shorthand to extend into the
         safe-area inset on notched devices */
      padding-bottom: calc(0.875rem + env(safe-area-inset-bottom, 0px));
      background: ${OS_LEGAL_COLORS.surface};
      box-shadow: ${OS_LEGAL_SHADOWS.footerLiftMobile};
      flex-shrink: 0;

      button {
        height: 48px;
        font-size: 0.9375rem;
        font-weight: 600;
        border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
      }
    }
  }
`;

const HeaderTitleRow = styled.span`
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-width: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    gap: 0.625rem;
  }
`;

const IconBadge = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: ${OS_LEGAL_SPACING.iconBadgeDesktop};
  height: ${OS_LEGAL_SPACING.iconBadgeDesktop};
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.accentSurface};
  color: ${OS_LEGAL_COLORS.accent};
  flex-shrink: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: ${OS_LEGAL_SPACING.iconBadgeMobile};
    height: ${OS_LEGAL_SPACING.iconBadgeMobile};
    /* Crisp 1px outline on the smaller mobile badge so the accent ring
       remains visible against the light surface — desktop badge is large
       enough not to need it. */
    box-shadow: inset 0 0 0 1px ${OS_LEGAL_COLORS.accentMedium};
  }
`;

const DemoBanner = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  background: ${OS_LEGAL_COLORS.warningSurface};
  border: 1px solid ${OS_LEGAL_COLORS.warningBorder};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  margin-bottom: 1.5rem;

  > svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.warningText};
    margin-top: 1px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.75rem 0.875rem;
    gap: 0.625rem;
    margin-bottom: 1.125rem;
    /* Add a left accent stripe to make the demo callout pop in the
       higher-information-density mobile layout. */
    border-left: ${OS_LEGAL_SPACING.borderAccentWidth} solid
      ${OS_LEGAL_COLORS.warningText};
  }
`;

const DemoBannerText = styled.p`
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.warningText};
  ${sansFont}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.8125rem;
    line-height: 1.45;
  }
`;

const LeadSection = styled.section`
  margin: 0 0 1.25rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin: 0 0 1rem;
  }
`;

const SectionLabel = styled.h4`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: ${OS_LEGAL_COLORS.textTertiary};
  ${sansFont}

  svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.6875rem;
    letter-spacing: 0.07em;
  }
`;

const LeadBody = styled.p`
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  ${sansFont}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.875rem;
    line-height: 1.55;
  }
`;

const TwoColumnGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.25rem;

  @media (max-width: ${COOKIE_CONSENT_GRID_BREAKPOINT}px) {
    grid-template-columns: 1fr;
    gap: 0.75rem;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-bottom: 1rem;
  }
`;

const DataCard = styled.section`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 1rem 1.125rem 1.125rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusCard};

  &.cookie-consent__analytics {
    margin-bottom: 1.25rem;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.875rem 0.875rem 0.9375rem;
    gap: 0.5rem;
    border-radius: ${OS_LEGAL_SPACING.borderRadiusCardMobile};
    /* Subtle elevation pulls the card off the body background; only
       needed at the higher visual density of the mobile layout. */
    box-shadow: ${OS_LEGAL_SHADOWS.card};

    &.cookie-consent__analytics {
      margin-bottom: 1rem;
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
  gap: 0.375rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    gap: 0.3125rem;
  }
`;

const DataListItem = styled.li`
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  line-height: 1.4;
  // textSecondary used over textTertiary so prose meets WCAG AA on surfaceLight.
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusListItem};
  ${sansFont}

  svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.5rem 0.625rem;
    gap: 0.5rem;
    font-size: 0.8125rem;
    background: ${OS_LEGAL_COLORS.accentSurface};
    color: ${OS_LEGAL_COLORS.textPrimary};

    svg {
      width: ${OS_LEGAL_SPACING.iconInlineMobile};
      height: ${OS_LEGAL_SPACING.iconInlineMobile};
    }
  }
`;

const AnalyticsNote = styled.p`
  margin: 0.125rem 0 0;
  font-size: 0.75rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textMuted};
  ${sansFont}
`;

const DisclaimerBlock = styled.aside`
  padding: 0.75rem 0.875rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-left: ${OS_LEGAL_SPACING.borderAccentWidth} solid
    ${OS_LEGAL_COLORS.borderHover};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.625rem 0.75rem;
  }
`;

const Disclaimer = styled.p`
  margin: 0;
  // 0.75rem (12px) keeps legal disclaimer text at the WCAG-recommended minimum.
  font-size: 0.75rem;
  line-height: 1.55;
  letter-spacing: 0.01em;
  color: ${OS_LEGAL_COLORS.textMuted};
  ${sansFont}

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 0.6875rem;
    line-height: 1.5;
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
    <StyledModalWrapper>
      <Modal open onClose={() => {}}>
        <ModalHeader
          title={
            <HeaderTitleRow>
              <IconBadge>
                <Cookie size={20} />
              </IconBadge>
              Cookie Policy &amp; Terms
            </HeaderTitleRow>
          }
        />
        <ModalBody>
          <DemoBanner>
            <AlertTriangle size={18} />
            <DemoBannerText>
              <strong>Demo system</strong> — no guarantee of uptime or data
              retention. Accounts and data may be deleted at any time.
            </DemoBannerText>
          </DemoBanner>

          <LeadSection>
            <SectionLabel>
              <Shield size={14} />
              Cookie Usage
            </SectionLabel>
            <LeadBody>
              This site uses cookies to enhance your experience and help us
              improve OpenContracts. We do not sell or share user information.
            </LeadBody>
          </LeadSection>

          <TwoColumnGrid>
            <DataCard>
              <SectionLabel>
                <FileText size={14} />
                Data We Collect
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
                Data You Agree to Share
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
                Analytics data is used solely to improve OpenContracts and is
                never sold or shared with third parties. You can opt out at any
                time through your browser settings or by using Do Not Track.
              </AnalyticsNote>
            </DataCard>
          )}

          <DisclaimerBlock>
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
            Accept &amp; Continue
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};
