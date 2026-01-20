import { Modal } from "semantic-ui-react";
import { Button } from "@os-legal/ui";
import { useMutation, useReactiveVar } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
import {
  AlertTriangle,
  Users,
  Settings,
  Monitor,
  LineChart,
  MousePointer,
  Bug,
  Check,
} from "lucide-react";

const InfoList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0.5rem 0;
`;

const InfoListItem = styled.li`
  display: flex;
  align-items: center;
  padding: 0.25rem 0;
`;

const InfoListContent = styled.span`
  margin-left: 0;
`;

const ModalHeaderIcon = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  color: white;
`;

const ModalHeaderTitle = styled.div`
  font-size: 1.5rem;
  font-weight: 600;
  margin-top: 0.5em;
  color: white;
`;

const SectionTitle = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: white;
  text-align: center;
  margin: 1rem 0 0.5rem 0;
`;

import { showCookieAcceptModal, authToken } from "../../graphql/cache";
import {
  ACCEPT_COOKIE_CONSENT,
  AcceptCookieConsentInputs,
  AcceptCookieConsentOutputs,
} from "../../graphql/mutations";
import {
  setAnalyticsConsent,
  isPostHogConfigured,
} from "../../utils/analytics";

export const CookieConsentDialog = () => {
  const auth_token = useReactiveVar(authToken);
  const isAuthenticated = Boolean(auth_token);
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
    <Modal basic size="small" open>
      <ModalHeaderIcon>
        <AlertTriangle size={32} />
        <ModalHeaderTitle>DEMO SYSTEM</ModalHeaderTitle>
      </ModalHeaderIcon>
      <Modal.Content style={{ marginTop: "0", paddingTop: "0" }}>
        <SectionTitle>
          <u>Cookie Policy</u>
        </SectionTitle>
        <p>
          This website uses cookies to enhance the user experience and help us
          refine OpenContracts. We do not sell or share user information. Please
          accept the cookie to continue.
        </p>
        <SectionTitle>
          <u>NO REPRESENTATIONS OR WARRANTIES</u>
        </SectionTitle>
        <p>
          This is a demo system with <b>NO</b> guarantee of uptime or data
          retention. We may delete accounts and data{" "}
          <u>AT ANY TIME AND FOR ANY REASON</u>. THE SOFTWARE IS PROVIDED "AS
          IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
          NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
          PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS
          OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
          LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
          ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
          OTHER DEALINGS IN THE SOFTWARE.
        </p>
        <SectionTitle>
          <u>Data We Collect</u>
        </SectionTitle>
        <InfoList>
          <InfoListItem>
            <span style={{ marginRight: "0.5em" }}>
              <Users size={16} />
            </span>
            <InfoListContent>
              User Information (email, name, ip)
            </InfoListContent>
          </InfoListItem>
          <InfoListItem>
            <span style={{ marginRight: "0.5em" }}>
              <Settings size={16} />
            </span>
            <InfoListContent>Usage Information</InfoListContent>
          </InfoListItem>
          <InfoListItem>
            <span style={{ marginRight: "0.5em" }}>
              <Monitor size={16} />
            </span>
            <InfoListContent>System Information</InfoListContent>
          </InfoListItem>
        </InfoList>
        <SectionTitle>
          <u>Data You Agree to Share</u>
        </SectionTitle>
        <p>
          By interacting with this demo system, you agree to share the following
          under a CC0 1.0 Universal license:
        </p>
        <InfoList>
          <InfoListItem>
            <span style={{ marginRight: "0.5em" }}>
              <Users size={16} />
            </span>
            <InfoListContent>Labelsets & Labels</InfoListContent>
          </InfoListItem>
          <InfoListItem>
            <span style={{ marginRight: "0.5em" }}>
              <Monitor size={16} />
            </span>
            <InfoListContent>Configured Data Extractors</InfoListContent>
          </InfoListItem>
        </InfoList>
        {analyticsEnabled && (
          <>
            <SectionTitle>
              <u>Analytics & Usage Tracking</u>
            </SectionTitle>
            <p>
              We use PostHog to collect anonymous usage analytics to help us
              understand how OpenContracts is used and improve the experience.
              This includes:
            </p>
            <InfoList>
              <InfoListItem>
                <span style={{ marginRight: "0.5em" }}>
                  <LineChart size={16} />
                </span>
                <InfoListContent>
                  Page views and navigation patterns
                </InfoListContent>
              </InfoListItem>
              <InfoListItem>
                <span style={{ marginRight: "0.5em" }}>
                  <MousePointer size={16} />
                </span>
                <InfoListContent>Feature usage statistics</InfoListContent>
              </InfoListItem>
              <InfoListItem>
                <span style={{ marginRight: "0.5em" }}>
                  <Bug size={16} />
                </span>
                <InfoListContent>Error tracking for debugging</InfoListContent>
              </InfoListItem>
            </InfoList>
            <p style={{ fontSize: "0.9em", opacity: 0.8 }}>
              Analytics data is used solely to improve OpenContracts and is
              never sold or shared with third parties. You can opt out at any
              time through your browser settings or by using Do Not Track.
            </p>
          </>
        )}
      </Modal.Content>
      <Modal.Actions>
        <Button
          variant="primary"
          loading={loading}
          disabled={loading}
          onClick={handleAccept}
          leftIcon={<Check size={16} />}
        >
          Accept
        </Button>
      </Modal.Actions>
    </Modal>
  );
};
