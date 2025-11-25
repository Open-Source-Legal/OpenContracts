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

import { Container } from "semantic-ui-react";

import { toast, ToastContainer } from "react-toastify";

import { useQuery, useReactiveVar } from "@apollo/client";

import {
  authToken,
  authStatusVar,
  showAnnotationLabels,
  showExportModal,
  userObj,
  showCookieAcceptModal,
  openedDocument,
  openedCorpus,
  openedExtract,
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

import "semantic-ui-css/semantic.min.css";
import "./App.css";
import "react-toastify/dist/ReactToastify.css";
import useWindowDimensions from "./components/hooks/WindowDimensionHook";
import { MobileNavMenu } from "./components/layout/MobileNavMenu";
import { LabelDisplayBehavior } from "./types/graphql-api";
import { CookieConsentDialog } from "./components/cookies/CookieConsent";
import { Extracts } from "./views/Extracts";
import { BadgeManagement } from "./components/badges/BadgeManagement";
import { useEnv } from "./components/hooks/UseEnv";
import { EditExtractModal } from "./components/widgets/modals/EditExtractModal";
import { SelectAnalyzerOrFieldsetModal } from "./components/widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer";
import { DocumentUploadModal } from "./components/widgets/modals/DocumentUploadModal";
import { FileUploadPackageProps } from "./components/widgets/modals/DocumentUploadModal";
import { DocumentLandingRoute } from "./components/routes/DocumentLandingRoute";
import { ExtractLandingRoute } from "./components/routes/ExtractLandingRoute";
import { NotFound } from "./components/routes/NotFound";
import { CorpusLandingRoute } from "./components/routes/CorpusLandingRoute";
import { CorpusThreadRoute } from "./components/routes/CorpusThreadRoute";
import { UserProfileRoute } from "./components/routes/UserProfileRoute";
import { LeaderboardRoute } from "./components/routes/LeaderboardRoute";
import { GlobalDiscussionsRoute } from "./components/routes/GlobalDiscussionsRoute";
import { ThreadSearchRoute } from "./views/ThreadSearchRoute";
import { CentralRouteManager } from "./routing/CentralRouteManager";
import { CRUDModal } from "./components/widgets/CRUD/CRUDModal";
import { updateAnnotationDisplayParams } from "./utils/navigationUtils";
import {
  editDocForm_Schema,
  editDocForm_Ui_Schema,
} from "./components/forms/schemas";
import { useBadgeNotifications } from "./hooks/useBadgeNotifications";
import { useBadgeCelebration } from "./hooks/useBadgeCelebration";
import { BadgeCelebrationModal } from "./components/badges/BadgeCelebrationModal";

export const App = () => {
  const { REACT_APP_USE_AUTH0, REACT_APP_AUDIENCE } = useEnv();
  const auth_token = useReactiveVar(authToken);
  const show_export_modal = useReactiveVar(showExportModal);
  const show_cookie_modal = useReactiveVar(showCookieAcceptModal);
  const knowledge_base_modal = useReactiveVar(showKnowledgeBaseModal);
  const opened_corpus = useReactiveVar(openedCorpus);
  const opened_extract = useReactiveVar(openedExtract);
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

  // Auth0 hooks for conditional rendering only
  const { isLoading } = useAuth0();

  const handleKnowledgeBaseModalClose = useCallback(() => {
    showKnowledgeBaseModal({
      isOpen: false,
      documentId: null,
      corpusId: null,
    });
  }, []);

  // For now, our responsive layout is a bit hacky, but it's working well enough to
  // provide a passable UI on mobile. Your results not guaranteed X-)
  const { width } = useWindowDimensions();
  const show_mobile_menu = width <= 1000;

  const navigate = useNavigate();
  const location = useLocation();

  // Track if we've applied mobile display settings to prevent infinite loop
  const mobileSettingsAppliedRef = useRef(false);

  const {
    data: meData,
    loading: meLoading,
    error: meError,
  } = useQuery<GetMeOutputs>(GET_ME, {
    skip: !auth_token,
    fetchPolicy: "network-only",
  });

  useEffect(() => {
    if (isLoading) return; // wait until Auth0 SDK has decided

    if (meData?.me) {
      backendUserObj(meData.me);
    } else if (!meLoading && auth_token && meError) {
      console.error("Error fetching backend user:", meError);
      toast.error("Could not get user details from server");
    } else if (!auth_token) {
      backendUserObj(null);
    }
  }, [isLoading, meData, meLoading, meError, auth_token]);

  // Badge notification system
  const { newBadges } = useBadgeNotifications(30000); // Poll every 30 seconds
  const { showModal, currentBadge, closeModal } = useBadgeCelebration(
    newBadges,
    {
      showToast: true,
      showModal: true,
    }
  );

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
  /* Cookie consent initialization                                          */
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
            {show_mobile_menu ? <MobileNavMenu /> : <NavMenu />}
            <Container
              id="AppContainer"
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                justifyContent: "flex-start",
                width: "100% !important",
                margin: "0px !important",
                padding: "0px !important",
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
              {opened_extract && (
                <EditExtractModal
                  ext={opened_extract}
                  open={opened_extract !== null}
                  toggleModal={() => openedExtract(null)}
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
                uiSchema={editDocForm_Ui_Schema}
                dataSchema={editDocForm_Schema}
                onSubmit={() => {
                  editingDocument(null);
                }}
                onClose={() => editingDocument(null)}
                acceptedFileTypes="pdf"
                hasFile={true}
                fileField="pdfFile"
                fileLabel="PDF File"
                fileIsImage={false}
              />
              <CRUDModal
                open={document_to_view !== null}
                mode="VIEW"
                oldInstance={document_to_view ? document_to_view : {}}
                modelName="document"
                uiSchema={editDocForm_Ui_Schema}
                dataSchema={editDocForm_Schema}
                onClose={() => viewingDocument(null)}
                acceptedFileTypes="pdf"
                hasFile={true}
                fileField="pdfFile"
                fileLabel="PDF File"
                fileIsImage={false}
              />
              {/* Central routing state manager - handles ALL URL ↔ State sync */}
              <CentralRouteManager />

              <AuthGate
                useAuth0={REACT_APP_USE_AUTH0}
                audience={REACT_APP_AUDIENCE}
              >
                <Routes>
                  <Route
                    path="/"
                    element={
                      isLoading ? <div /> : <Navigate to="/corpuses" replace />
                    }
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

                  {/* Auth */}
                  {!REACT_APP_USE_AUTH0 ? (
                    <Route path="/login" element={<Login />} />
                  ) : (
                    <></>
                  )}
                  <Route path="/label_sets" element={<Labelsets />} />
                  <Route path="/annotations" element={<Annotations />} />
                  <Route path="/privacy" element={<PrivacyPolicy />} />
                  <Route
                    path="/terms_of_service"
                    element={<TermsOfService />}
                  />
                  <Route path="/extracts" element={<Extracts />} />
                  <Route path="/admin/badges" element={<BadgeManagement />} />

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
            </Container>
          </div>
          <div
            style={{
              flexShrink: 0,
              position: "relative",
              marginTop: "-1.5rem",
            }}
          >
            <Footer />
          </div>
        </div>
      </ThemeProvider>
    </div>
  );
};
