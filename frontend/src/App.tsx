import { useEffect, useCallback, useRef } from "react";

import { useAuth0 } from "@auth0/auth0-react";

import {
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
} from "react-router-dom";

import _ from "lodash";

import { toast, ToastContainer } from "react-toastify";

import { useMutation, useQuery, useReactiveVar } from "@apollo/client";

import {
  authToken,
  authStatusVar,
  authInitCompleteVar,
  showAnnotationLabels,
  showExportModal,
  userObj,
  showCookieAcceptModal,
  openedDocument,
  openedCorpus,
  showSelectCorpusAnalyzerOrFieldsetModal,
  showUploadNewDocumentsModal,
  uploadModalPreloadedFiles,
  showKnowledgeBaseModal,
  backendUserObj,
  editingDocument,
  viewingDocument,
  selectedFolderId,
} from "./graphql/cache";
import { GET_ME, GetMeOutputs } from "./graphql/queries";
import {
  UPDATE_DOCUMENT,
  UpdateDocumentInputs,
  UpdateDocumentOutputs,
} from "./graphql/mutations";

import { NavMenu } from "./components/layout/NavMenu";
import { Footer } from "./components/layout/Footer";
import { ExportModal } from "./components/widgets/modals/ExportModal";
import { DocumentKnowledgeBase } from "./components/knowledge_base";

import { PrivacyPolicy } from "./views/PrivacyPolicy";
import { TermsOfService } from "./views/TermsOfService";
import { Corpuses } from "./views/Corpuses";
import { Documents } from "./views/Documents";
import { Labelsets } from "./views/LabelSets";
import { Login } from "./views/Login";
import { AuthGate } from "./components/auth/AuthGate";
import { Annotations } from "./views/Annotations";

import { ThemeProvider } from "./theme/ThemeProvider";

import "./App.css";
import "react-toastify/dist/ReactToastify.css";
import useWindowDimensions from "./components/hooks/WindowDimensionHook";
import { LabelDisplayBehavior } from "./types/graphql-api";
import { CookieConsentDialog } from "./components/cookies/CookieConsent";
import { initializeAnalyticsOnLoad } from "./utils/analytics";
import { Extracts } from "./views/Extracts";
import { BadgeManagement } from "./components/badges/BadgeManagement";
import {
  GlobalSettingsPanel,
  GlobalAgentManagement,
  SystemSettings,
  WorkerAccountManagement,
} from "./components/admin";
import { useEnv } from "./components/hooks/UseEnv";
import { ExtractDetailRoute } from "./components/routes/ExtractDetailRoute";
import { SelectAnalyzerOrFieldsetModal } from "./components/widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer";
import { DocumentUploadModal } from "./components/widgets/modals/DocumentUploadModal";
import { FileUploadPackageProps } from "./components/widgets/modals/DocumentUploadModal";
import { DocumentLandingRoute } from "./components/routes/DocumentLandingRoute";
import { ExtractLandingRoute } from "./components/routes/ExtractLandingRoute";
import { LabelSetLandingRoute } from "./components/routes/LabelSetLandingRoute";
import { NotFound } from "./components/routes/NotFound";
import { CorpusLandingRoute } from "./components/routes/CorpusLandingRoute";
import { CorpusThreadRoute } from "./components/routes/CorpusThreadRoute";
import { UserProfileRoute } from "./components/routes/UserProfileRoute";
import { LeaderboardRoute } from "./components/routes/LeaderboardRoute";
import { GlobalDiscussionsRoute } from "./components/routes/GlobalDiscussionsRoute";
import { ThreadSearchRoute } from "./views/ThreadSearchRoute";
import { DiscoveryLanding } from "./views/DiscoveryLanding";
import { CentralRouteManager } from "./routing/CentralRouteManager";
import { CRUDModal } from "./components/widgets/CRUD/CRUDModal";
import { updateAnnotationDisplayParams } from "./utils/navigationUtils";
import { DocumentFormFields } from "./components/forms/DocumentFormFields";
import { validateTitleAndDescription } from "./components/forms/shared";
import { useBadgeNotifications } from "./hooks/useBadgeNotifications";
import { useBadgeCelebration } from "./hooks/useBadgeCelebration";
import { BadgeCelebrationModal } from "./components/badges/BadgeCelebrationModal";
import { useJobNotifications } from "./hooks/useJobNotifications";
import { useRefetchOnAuthChange } from "./hooks/useRefetchOnAuthChange";

export const App = () => {
  const { REACT_APP_USE_AUTH0, REACT_APP_AUDIENCE } = useEnv();
  const auth_token = useReactiveVar(authToken);
  const show_export_modal = useReactiveVar(showExportModal);
  const show_cookie_modal = useReactiveVar(showCookieAcceptModal);
  const knowledge_base_modal = useReactiveVar(showKnowledgeBaseModal);
  const opened_corpus = useReactiveVar(openedCorpus);
  const opened_document = useReactiveVar(openedDocument);
  const document_to_edit = useReactiveVar(editingDocument);
  const document_to_view = useReactiveVar(viewingDocument);
  const selected_folder_id = useReactiveVar(selectedFolderId);
  const show_corpus_analyzer_fieldset_modal = useReactiveVar(
    showSelectCorpusAnalyzerOrFieldsetModal
  );
  const show_upload_new_documents_modal = useReactiveVar(
    showUploadNewDocumentsModal
  );
  // Track when auth initialization (including cache clear) is complete
  const auth_init_complete = useReactiveVar(authInitCompleteVar);

  // useAuth0() must be called unconditionally (React hooks rules), but
  // its return values are only meaningful when Auth0 is enabled. Without
  // an Auth0Provider the hook returns the default context whose isLoading
  // is permanently true — guarding with REACT_APP_USE_AUTH0 matches the
  // pattern used by AuthGate and useNavMenu for the same reason.
  const { isLoading: auth0Loading } = useAuth0();
  const isLoading = REACT_APP_USE_AUTH0 ? auth0Loading : false;

  const [tryUpdateDocument] = useMutation<
    UpdateDocumentOutputs,
    UpdateDocumentInputs
  >(UPDATE_DOCUMENT, {
    onCompleted: () => {
      toast.success("Document updated successfully");
      editingDocument(null);
    },
    onError: (error) => {
      toast.error(`Failed to update document: ${error.message}`);
    },
    refetchQueries: "active",
  });

  const handleUpdateDocument = useCallback(
    (document_obj: Record<string, unknown>) => {
      tryUpdateDocument({
        variables: document_obj as unknown as UpdateDocumentInputs,
      });
    },
    [tryUpdateDocument]
  );

  const handleKnowledgeBaseModalClose = useCallback(() => {
    showKnowledgeBaseModal({
      isOpen: false,
      documentId: null,
      corpusId: null,
    });
  }, []);

  // For mobile display settings
  const { width } = useWindowDimensions();

  const navigate = useNavigate();
  const location = useLocation();

  // Track if we've applied mobile display settings to prevent infinite loop
  const mobileSettingsAppliedRef = useRef(false);

  // Track if we've shown the user fetch error toast to prevent duplicates
  // This can happen on mobile where network is slower and query may fail initially
  const meErrorShownRef = useRef(false);

  const {
    data: meData,
    loading: meLoading,
    error: meError,
  } = useQuery<GetMeOutputs>(GET_ME, {
    // Skip until BOTH: we have a token AND auth initialization (including cache clear) is complete.
    // This prevents the query from being aborted by clearStore() during auth initialization.
    skip: !auth_token || !auth_init_complete,
    fetchPolicy: "network-only",
  });

  // Reset error shown flag when auth_token changes (new login session)
  useEffect(() => {
    meErrorShownRef.current = false;
  }, [auth_token]);

  useEffect(() => {
    if (isLoading) return; // wait until Auth0 SDK has decided

    if (meData?.me) {
      backendUserObj(meData.me);
      // Clear error flag if we successfully got user data
      meErrorShownRef.current = false;
    } else if (
      !meLoading &&
      auth_token &&
      meError &&
      !meErrorShownRef.current
    ) {
      // Only show error once per session, and only if we don't already have user data
      console.error("Error fetching backend user:", meError);
      toast.error("Could not get user details from server");
      meErrorShownRef.current = true;
    } else if (!auth_token) {
      backendUserObj(null);
    }
  }, [isLoading, meData, meLoading, meError, auth_token]);

  // Badge notification system (real-time via WebSocket)
  const { newBadges } = useBadgeNotifications();
  const { showModal, currentBadge, closeModal } = useBadgeCelebration(
    newBadges,
    {
      showToast: true,
      showModal: true,
    }
  );

  // Job notification system (real-time via WebSocket) - Issue #624
  // Automatically shows toasts for document processing, extracts, analyses, exports
  useJobNotifications({ showToast: true });

  // Refetch all active queries after any cache clear (login, logout, token refresh)
  // so mounted components get data appropriate to the new auth context.
  useRefetchOnAuthChange();

  // Set mobile-friendly display settings once when narrow viewport detected
  // CRITICAL: Don't include location/navigate in deps - causes infinite loop!
  useEffect(() => {
    const isMobile = width <= 800;
    const currentLabels = showAnnotationLabels();

    // Only update if:
    // 1. We're on mobile AND
    // 2. Labels aren't already set to ALWAYS AND
    // 3. We haven't already applied mobile settings
    if (
      isMobile &&
      currentLabels !== LabelDisplayBehavior.ALWAYS &&
      !mobileSettingsAppliedRef.current
    ) {
      // Update display settings via URL - CentralRouteManager will set reactive vars
      updateAnnotationDisplayParams(location, navigate, {
        labelDisplay: LabelDisplayBehavior.ALWAYS,
      });
      mobileSettingsAppliedRef.current = true;
    }

    // Reset flag when returning to desktop width
    if (!isMobile) {
      mobileSettingsAppliedRef.current = false;
    }
  }, [width]); // Only depend on width, not location!

  // Auth logic has been moved to AuthGate component to ensure it completes
  // before any components that need authentication are rendered

  console.log("Cookie Accepted: ", show_cookie_modal);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const filePackages: FileUploadPackageProps[] = acceptedFiles.map(
      (file) => ({
        file,
        formData: {
          title: file.name,
          description: `Content summary for ${file.name}`,
        },
      })
    );
    showUploadNewDocumentsModal(true);
    uploadModalPreloadedFiles(filePackages);
  }, []);

  /* ---------------------------------------------------------------------- */
  /* Cookie consent and analytics initialization                            */
  /* ---------------------------------------------------------------------- */
  useEffect(() => {
    // Run once on mount in browser to determine whether to display the
    // cookie consent banner. We avoid touching `localStorage` during SSR or
    // in non-browser test environments.
    if (typeof window === "undefined") return;

    const accepted =
      window.localStorage?.getItem("oc_cookieAccepted") === "true";
    // Only update if we haven't explicitly set it elsewhere yet.
    if (showCookieAcceptModal() === false && !accepted) {
      showCookieAcceptModal(true);
    }

    // Initialize PostHog analytics if consent was previously given
    initializeAnalyticsOnLoad();
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        minHeight: "100vh",
      }}
    >
      <ToastContainer />
      {show_export_modal ? (
        <ExportModal
          visible={show_export_modal}
          toggleModal={() => showExportModal(!show_export_modal)}
        />
      ) : (
        <></>
      )}
      {knowledge_base_modal.isOpen &&
        knowledge_base_modal.documentId &&
        knowledge_base_modal.documentId !== "" && (
          <DocumentKnowledgeBase
            documentId={knowledge_base_modal.documentId}
            corpusId={knowledge_base_modal.corpusId ?? undefined}
            initialAnnotationIds={
              knowledge_base_modal.annotationIds ?? undefined
            }
            onClose={handleKnowledgeBaseModalClose}
          />
        )}
      {show_cookie_modal ? <CookieConsentDialog /> : <></>}
      {showModal && currentBadge && (
        <BadgeCelebrationModal
          badgeName={currentBadge.badgeName}
          badgeDescription={currentBadge.badgeDescription}
          badgeIcon={currentBadge.badgeIcon}
          badgeColor={currentBadge.badgeColor}
          isAutoAwarded={currentBadge.isAutoAwarded}
          awardedBy={currentBadge.awardedBy}
          onClose={closeModal}
          onViewBadges={() => navigate("/badges")}
        />
      )}
      <ThemeProvider>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            position: "relative",
            minHeight: "100vh",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              minHeight: "100vh",
              maxHeight: "100vh",
              height: "100vh",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            <NavMenu />
            <div
              id="AppContainer"
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-start",
                width: "100%",
                margin: "0px",
                padding: "0px",
                minWidth: "100vw",
                minHeight: 0,
                overflow: "hidden",
              }}
            >
              {opened_corpus && (
                <SelectAnalyzerOrFieldsetModal
                  open={show_corpus_analyzer_fieldset_modal}
                  corpus={opened_corpus}
                  document={opened_document ? opened_document : undefined}
                  onClose={() => showSelectCorpusAnalyzerOrFieldsetModal(false)}
                />
              )}
              <DocumentUploadModal
                refetch={() => {
                  showUploadNewDocumentsModal(false);
                  uploadModalPreloadedFiles([]);
                }}
                open={Boolean(show_upload_new_documents_modal)}
                onClose={() => {
                  showUploadNewDocumentsModal(false);
                  uploadModalPreloadedFiles([]);
                }}
                corpusId={opened_corpus?.id || null}
                folderId={selected_folder_id}
              />
              <CRUDModal
                open={document_to_edit !== null}
                mode="EDIT"
                oldInstance={document_to_edit ? document_to_edit : {}}
                modelName="document"
                onSubmit={handleUpdateDocument}
                onClose={() => editingDocument(null)}
                acceptedFileTypes="pdf"
                hasFile={true}
                fileField="pdfFile"
                fileLabel="PDF File"
                fileIsImage={false}
                validate={validateTitleAndDescription}
                renderForm={(formData, onChange, disabled) => (
                  <DocumentFormFields
                    formData={formData}
                    onChange={onChange}
                    disabled={disabled}
                  />
                )}
              />
              <CRUDModal
                open={document_to_view !== null}
                mode="VIEW"
                oldInstance={document_to_view ? document_to_view : {}}
                modelName="document"
                onClose={() => viewingDocument(null)}
                acceptedFileTypes="pdf"
                hasFile={true}
                fileField="pdfFile"
                fileLabel="PDF File"
                fileIsImage={false}
                renderForm={(formData, onChange, disabled) => (
                  <DocumentFormFields
                    formData={formData}
                    onChange={onChange}
                    disabled={disabled}
                  />
                )}
              />
              {/* Central routing state manager - handles ALL URL ↔ State sync */}
              <CentralRouteManager />

              <AuthGate
                useAuth0={REACT_APP_USE_AUTH0}
                audience={REACT_APP_AUDIENCE}
              >
                <Routes>
                  {/* Landing/Discovery Page - Main entry point */}
                  <Route
                    path="/"
                    element={isLoading ? <div /> : <DiscoveryLanding />}
                  />
                  {/* Simple declarative routes with explicit prefixes */}

                  {/* Document routes */}
                  <Route
                    path="/d/:userIdent/:corpusIdent/:docIdent"
                    element={<DocumentLandingRoute />}
                  />
                  <Route
                    path="/d/:userIdent/:docIdent"
                    element={<DocumentLandingRoute />}
                  />

                  {/* Corpus discussion thread route (Issue #621) - MUST come before general corpus route */}
                  <Route
                    path="/c/:userIdent/:corpusIdent/discussions/:threadId"
                    element={<CorpusThreadRoute />}
                  />
                  {/* Corpus routes */}
                  <Route
                    path="/c/:userIdent/:corpusIdent"
                    element={<CorpusLandingRoute />}
                  />

                  {/* Extract routes */}
                  <Route
                    path="/e/:userIdent/:extractIdent"
                    element={<ExtractLandingRoute />}
                  />

                  {/* List views */}
                  <Route path="/corpuses" element={<Corpuses />} />
                  <Route path="/documents" element={<Documents />} />

                  {/* Global Discussions Route (Issue #623) */}
                  <Route
                    path="/discussions"
                    element={<GlobalDiscussionsRoute />}
                  />

                  {/* Thread Search Route (Issue #580) */}
                  <Route path="/threads" element={<ThreadSearchRoute />} />

                  {/* User Profile Routes (Issue #611) */}
                  <Route path="/profile" element={<UserProfileRoute />} />
                  <Route path="/users/:slug" element={<UserProfileRoute />} />
                  {/* Convenience redirect for badge notifications (Issue #637) */}
                  <Route
                    path="/badges"
                    element={<Navigate to="/profile" replace />}
                  />

                  {/* Auth */}
                  {!REACT_APP_USE_AUTH0 ? (
                    <Route path="/login" element={<Login />} />
                  ) : (
                    <></>
                  )}
                  {/* LabelSet routes */}
                  <Route
                    path="/label_sets/:labelsetId"
                    element={<LabelSetLandingRoute />}
                  />
                  <Route path="/label_sets" element={<Labelsets />} />
                  <Route path="/annotations" element={<Annotations />} />
                  <Route path="/privacy" element={<PrivacyPolicy />} />
                  <Route
                    path="/terms_of_service"
                    element={<TermsOfService />}
                  />
                  <Route
                    path="/extracts/:extractId"
                    element={<ExtractDetailRoute />}
                  />
                  <Route path="/extracts" element={<Extracts />} />
                  <Route path="/admin/badges" element={<BadgeManagement />} />
                  <Route
                    path="/admin/settings"
                    element={<GlobalSettingsPanel />}
                  />
                  <Route
                    path="/admin/agents"
                    element={<GlobalAgentManagement />}
                  />
                  <Route
                    path="/admin/worker-accounts"
                    element={<WorkerAccountManagement />}
                  />
                  <Route path="/system_settings" element={<SystemSettings />} />

                  {/* Community Routes (Issue #613) */}
                  <Route path="/leaderboard" element={<LeaderboardRoute />} />
                  <Route
                    path="/community/leaderboard"
                    element={<LeaderboardRoute />}
                  />

                  {/* 404 explicit route and catch-all */}
                  <Route path="/404" element={<NotFound />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </AuthGate>
            </div>
          </div>
          {!opened_corpus && (
            <div
              style={{
                flexShrink: 0,
                position: "relative",
                // Negative margin collapses the gap between the content area
                // and the footer so they appear visually flush.
                marginTop: "-1.5rem",
              }}
            >
              <Footer />
            </div>
          )}
        </div>
      </ThemeProvider>
    </div>
  );
};
