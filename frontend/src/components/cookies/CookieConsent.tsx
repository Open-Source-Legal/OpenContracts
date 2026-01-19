import { List, Modal, Header, Button } from "semantic-ui-react";
import { useMutation, useReactiveVar } from "@apollo/client";
import { toast } from "react-toastify";
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
      <Header icon>
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            justifyContent: "center",
          }}
        >
          <div>
            <AlertTriangle size={32} />
          </div>
        </div>
        <div style={{ marginTop: ".5em" }}>DEMO SYSTEM</div>
      </Header>
      <Modal.Content style={{ marginTop: "0", paddingTop: "0" }}>
        <Header inverted textAlign="center">
          <Header.Content as="h4">
            <u>Cookie Policy</u>
          </Header.Content>
        </Header>
        <p>
          This website uses cookies to enhance the user experience and help us
          refine OpenContracts. We do not sell or share user information. Please
          accept the cookie to continue.
        </p>
        <Header inverted textAlign="center">
          <Header.Content as="h4">
            <u>NO REPRESENTATIONS OR WARRANTIES</u>
          </Header.Content>
        </Header>
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
        <Header inverted textAlign="center">
          <Header.Content as="h4">
            <u>Data We Collect</u>
          </Header.Content>
        </Header>
        <List>
          <List.Item>
            <span style={{ marginRight: "0.5em" }}>
              <Users size={16} />
            </span>
            <List.Content>User Information (email, name, ip)</List.Content>
          </List.Item>
          <List.Item>
            <span style={{ marginRight: "0.5em" }}>
              <Settings size={16} />
            </span>
            <List.Content>Usage Information</List.Content>
          </List.Item>
          <List.Item>
            <span style={{ marginRight: "0.5em" }}>
              <Monitor size={16} />
            </span>
            <List.Content>System Information</List.Content>
          </List.Item>
        </List>
        <Header inverted textAlign="center">
          <Header.Content as="h4">
            <u>Data You Agree to Share</u>
          </Header.Content>
        </Header>
        <p>
          By interacting with this demo system, you agree to share the following
          under a CC0 1.0 Universal license:
        </p>
        <List>
          <List.Item>
            <span style={{ marginRight: "0.5em" }}>
              <Users size={16} />
            </span>
            <List.Content>Labelsets & Labels</List.Content>
          </List.Item>
          <List.Item>
            <span style={{ marginRight: "0.5em" }}>
              <Monitor size={16} />
            </span>
            <List.Content>Configured Data Extractors</List.Content>
          </List.Item>
        </List>
        {analyticsEnabled && (
          <>
            <Header inverted textAlign="center">
              <Header.Content as="h4">
                <u>Analytics & Usage Tracking</u>
              </Header.Content>
            </Header>
            <p>
              We use PostHog to collect anonymous usage analytics to help us
              understand how OpenContracts is used and improve the experience.
              This includes:
            </p>
            <List>
              <List.Item>
                <span style={{ marginRight: "0.5em" }}>
                  <LineChart size={16} />
                </span>
                <List.Content>Page views and navigation patterns</List.Content>
              </List.Item>
              <List.Item>
                <span style={{ marginRight: "0.5em" }}>
                  <MousePointer size={16} />
                </span>
                <List.Content>Feature usage statistics</List.Content>
              </List.Item>
              <List.Item>
                <span style={{ marginRight: "0.5em" }}>
                  <Bug size={16} />
                </span>
                <List.Content>Error tracking for debugging</List.Content>
              </List.Item>
            </List>
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
          color="green"
          inverted
          loading={loading}
          disabled={loading}
          onClick={handleAccept}
        >
          <Check size={16} style={{ marginRight: "0.5em" }} /> Accept
        </Button>
      </Modal.Actions>
    </Modal>
  );
};
