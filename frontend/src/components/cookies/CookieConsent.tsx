import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { modalFooterBorder } from "../widgets/modals/sharedModalStyles";
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
} from "lucide-react";
import { Button, Modal, ModalBody, ModalFooter } from "@os-legal/ui";

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

const StyledModalWrapper = styled.div`
  .oc-modal-overlay {
    z-index: 2000;
  }

  .oc-modal {
    max-width: 600px;
    color: ${OS_LEGAL_COLORS.darkSurfaceText};
    background: ${OS_LEGAL_COLORS.darkSurface};
  }

  .oc-modal-body {
    background: ${OS_LEGAL_COLORS.darkSurface};
    padding: 1.5rem;
  }

  .oc-modal-footer {
    ${modalFooterBorder}
    background: ${OS_LEGAL_COLORS.darkSurface};
    border-top-color: ${OS_LEGAL_COLORS.darkSurfaceBorder};
    display: flex;
    justify-content: center;
  }
`;

const ModalHeaderSection = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 1rem;
`;

const IconWrapper = styled.div`
  color: #fbbf24;
  margin-bottom: 0.5rem;
`;

const ModalTitle = styled.h2`
  font-size: 1.25rem;
  font-weight: 700;
  color: white;
  margin: 0;
`;

const SectionHeading = styled.h4`
  text-align: center;
  color: white;
  margin: 1.25rem 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;

  u {
    text-decoration-color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const DataList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0.5rem 0;
`;

const DataListItem = styled.li`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.4rem 0;
  font-size: 0.95rem;
  color: ${OS_LEGAL_COLORS.darkSurfaceText};

  svg {
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.darkSurfaceBorder};
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
        <ModalBody>
          <ModalHeaderSection>
            <IconWrapper>
              <AlertTriangle size={48} />
            </IconWrapper>
            <ModalTitle>DEMO SYSTEM</ModalTitle>
          </ModalHeaderSection>

          <SectionHeading>
            <u>Cookie Policy</u>
          </SectionHeading>
          <p>
            This website uses cookies to enhance the user experience and help us
            refine OpenContracts. We do not sell or share user information.
            Please accept the cookie to continue.
          </p>

          <SectionHeading>
            <u>NO REPRESENTATIONS OR WARRANTIES</u>
          </SectionHeading>
          <p>
            This is a demo system with <b>NO</b> guarantee of uptime or data
            retention. We may delete accounts and data{" "}
            <u>AT ANY TIME AND FOR ANY REASON</u>. THE SOFTWARE IS PROVIDED "AS
            IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
            NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
            PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
            AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
            OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
            OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
            OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
          </p>

          <SectionHeading>
            <u>Data We Collect</u>
          </SectionHeading>
          <DataList>
            <DataListItem>
              <Users size={16} />
              <span>User Information (email, name, ip)</span>
            </DataListItem>
            <DataListItem>
              <Settings size={16} />
              <span>Usage Information</span>
            </DataListItem>
            <DataListItem>
              <Monitor size={16} />
              <span>System Information</span>
            </DataListItem>
          </DataList>

          <SectionHeading>
            <u>Data You Agree to Share</u>
          </SectionHeading>
          <p>
            By interacting with this demo system, you agree to share the
            following under a CC0 1.0 Universal license:
          </p>
          <DataList>
            <DataListItem>
              <Users size={16} />
              <span>Labelsets &amp; Labels</span>
            </DataListItem>
            <DataListItem>
              <Monitor size={16} />
              <span>Configured Data Extractors</span>
            </DataListItem>
          </DataList>

          {analyticsEnabled && (
            <>
              <SectionHeading>
                <u>Analytics &amp; Usage Tracking</u>
              </SectionHeading>
              <p>
                We use PostHog to collect anonymous usage analytics to help us
                understand how OpenContracts is used and improve the experience.
                This includes:
              </p>
              <DataList>
                <DataListItem>
                  <BarChart3 size={16} />
                  <span>Page views and navigation patterns</span>
                </DataListItem>
                <DataListItem>
                  <MousePointer size={16} />
                  <span>Feature usage statistics</span>
                </DataListItem>
                <DataListItem>
                  <Bug size={16} />
                  <span>Error tracking for debugging</span>
                </DataListItem>
              </DataList>
              <p style={{ fontSize: "0.9em", opacity: 0.8 }}>
                Analytics data is used solely to improve OpenContracts and is
                never sold or shared with third parties. You can opt out at any
                time through your browser settings or by using Do Not Track.
              </p>
            </>
          )}
        </ModalBody>
        <ModalFooter>
          <Button
            variant="primary"
            loading={loading}
            disabled={loading}
            leftIcon={<Check size={16} />}
            onClick={handleAccept}
          >
            Accept
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};
