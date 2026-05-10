import React, { useEffect, useMemo, useState } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Users,
  Calendar,
  Globe,
  Shield,
  FileText,
  BookOpen,
  ListTree,
  ChevronsUpDown,
  ChevronsDownUp,
  Edit,
  Menu,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import {
  GET_CORPUS_WITH_HISTORY,
  GetCorpusWithHistoryQuery,
  GetCorpusWithHistoryQueryVariables,
} from "../../../graphql/queries";
import { CorpusType } from "../../../types/graphql-api";
import { PermissionTypes } from "../../types";
import { getPermissions } from "../../../utils/transform";
import { getCreatorDisplay } from "../../../utils/userDisplay";
import { tocExpandAll } from "../../../graphql/cache";
import { updateTocExpandedParam } from "../../../utils/navigationUtils";
import { CorpusAbout } from "../CorpusAbout/CorpusAbout";
import { DocumentTableOfContents } from "../DocumentTableOfContents";
import { MCPShareButton } from "../../common/MCPShareButton";

import {
  DetailsContainer,
  DetailsPage,
  DetailsHeader,
  BackButton,
  DetailsTitleRow,
  DetailsTitleSection,
  DetailsTitle,
  CenteredMetadataRow,
  MetadataItem,
  MetadataSeparator,
  AccessBadge,
  DetailsMainContent,
  TwoColumnLayout,
  DocumentsSidebar,
  SidebarLabel,
  SectionLabel,
  SidebarContent,
  AboutMainContent,
  AboutHeader,
  AboutActions,
  TextButtonPrimary,
  AboutBody,
  ExpandButton,
  MobileTabContainer,
  MobileTabList,
  MobileTab,
  MobileTabContent,
  MobileAboutActions,
  MobileDocToolbar,
  MobileSearchInput,
  HeaderRow,
  MobileMenuButton,
} from "./styles";

type MobileTabType = "toc" | "about";

export interface CorpusDetailsViewProps {
  /** The corpus object */
  corpus: CorpusType;
  /** Callback when "< Overview" back button is clicked */
  onBack: () => void;
  /** Callback when edit description is clicked */
  onEditDescription: () => void;
  /** Callback to open mobile navigation menu */
  onOpenMobileMenu?: () => void;
  /** Test ID for the component */
  testId?: string;
}

/**
 * CorpusDetailsView - Minimalist two-column details layout
 *
 * Features:
 * - Clean typography-first design
 * - Narrow Documents sidebar (left)
 * - Full About content (right)
 * - No cards, just clean dividers
 * - Mobile: Tabbed interface
 */
export const CorpusDetailsView: React.FC<CorpusDetailsViewProps> = ({
  corpus,
  onBack,
  onEditDescription,
  onOpenMobileMenu,
  testId = "corpus-details",
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const [mdContent, setMdContent] = React.useState<string | null>(null);
  const [mobileTab, setMobileTab] = useState<MobileTabType>("about");
  // Intentionally preserved across tab switches so returning to Documents keeps the filter
  const [docSearchQuery, setDocSearchQuery] = useState("");

  // Get TOC expand state from URL-driven reactive var (set by CentralRouteManager)
  const isTocExpanded = useReactiveVar(tocExpandAll);

  // Toggle TOC expand state via URL utility
  // CentralRouteManager Phase 2 will detect URL change and set tocExpandAll reactive var
  const handleToggleExpandAll = () => {
    updateTocExpandedParam(location, navigate, !isTocExpanded);
  };

  // CRITICAL: Memoize variables object to prevent Apollo refetch on every render
  const historyVariables = useMemo(() => ({ id: corpus.id }), [corpus.id]);

  // Fetch corpus with description history
  const { data: corpusData, loading: corpusLoading } = useQuery<
    GetCorpusWithHistoryQuery,
    GetCorpusWithHistoryQueryVariables
  >(GET_CORPUS_WITH_HISTORY, {
    variables: historyVariables,
  });

  // Fetch markdown content from URL
  useEffect(() => {
    if (corpusData?.corpus?.mdDescription) {
      fetch(corpusData.corpus.mdDescription)
        .then((res) => {
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}: ${res.statusText}`);
          }
          return res.text();
        })
        .then((text) => setMdContent(text))
        .catch((err) => {
          console.error("Error fetching corpus description:", err);
          setMdContent(null);
        });
    }
  }, [corpusData]);

  // Use the fetched corpus data instead of the prop for description/history
  const fullCorpus = corpusData?.corpus || corpus;

  const canEdit = getPermissions(fullCorpus.myPermissions || []).includes(
    PermissionTypes.CAN_UPDATE
  );

  const creatorName = getCreatorDisplay(fullCorpus.creator);
  const createdDate = fullCorpus.created
    ? formatDistanceToNow(new Date(fullCorpus.created), { addSuffix: true })
    : "recently";

  // Get document count from corpus prop
  const docCount = corpus.documentCount;

  const hasContent = mdContent || fullCorpus.description;

  return (
    <DetailsContainer data-testid={testId}>
      <DetailsPage>
        {/* Header section - clean, minimal */}
        <DetailsHeader>
          <HeaderRow $justify="space-between">
            <BackButton
              onClick={onBack}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              data-testid={`${testId}-back-btn`}
            >
              <ArrowLeft />
              Overview
            </BackButton>
            {onOpenMobileMenu && (
              <MobileMenuButton
                onClick={onOpenMobileMenu}
                aria-label="Open navigation menu"
                data-testid={`${testId}-mobile-menu`}
              >
                <Menu />
              </MobileMenuButton>
            )}
          </HeaderRow>

          <DetailsTitleRow>
            <DetailsTitleSection>
              <DetailsTitle data-testid={`${testId}-title`}>
                {fullCorpus.title || "Untitled Corpus"}
              </DetailsTitle>

              {/* Metadata row - subtle, inline */}
              <CenteredMetadataRow
                style={{ justifyContent: "flex-start", marginTop: "0.75rem" }}
                data-testid={`${testId}-metadata`}
              >
                <AccessBadge $isPublic={fullCorpus.isPublic}>
                  {fullCorpus.isPublic ? (
                    <>
                      <Globe aria-hidden="true" />
                      Public
                    </>
                  ) : (
                    <>
                      <Shield aria-hidden="true" />
                      Private
                    </>
                  )}
                </AccessBadge>

                {fullCorpus.slug && (
                  <>
                    <MetadataSeparator />
                    <MCPShareButton
                      corpusSlug={fullCorpus.slug}
                      isPublic={Boolean(fullCorpus.isPublic)}
                      size="sm"
                      testId={`${testId}-mcp-share`}
                    />
                  </>
                )}

                <MetadataSeparator className="hide-mobile" />

                <MetadataItem className="hide-mobile">
                  <Users aria-hidden="true" />
                  <span>{creatorName}</span>
                </MetadataItem>

                <MetadataSeparator className="hide-mobile" />

                <MetadataItem className="hide-mobile">
                  <Calendar aria-hidden="true" />
                  <span>{createdDate}</span>
                </MetadataItem>

                {docCount != null && docCount > 0 && (
                  <>
                    <MetadataSeparator />
                    <MetadataItem>
                      <FileText aria-hidden="true" />
                      <span>
                        {docCount} {docCount === 1 ? "document" : "documents"}
                      </span>
                    </MetadataItem>
                  </>
                )}
              </CenteredMetadataRow>
            </DetailsTitleSection>
          </DetailsTitleRow>
        </DetailsHeader>

        {/* Main content - two columns with vertical divider */}
        <DetailsMainContent>
          <TwoColumnLayout>
            {/* Left: Documents sidebar */}
            <DocumentsSidebar>
              <SidebarLabel>
                <SectionLabel>Documents</SectionLabel>
                <ExpandButton
                  onClick={handleToggleExpandAll}
                  aria-label={isTocExpanded ? "Collapse all" : "Expand all"}
                >
                  {isTocExpanded ? (
                    <>
                      <ChevronsDownUp />
                      Collapse
                    </>
                  ) : (
                    <>
                      <ChevronsUpDown />
                      Expand
                    </>
                  )}
                </ExpandButton>
              </SidebarLabel>
              <SidebarContent>
                <DocumentTableOfContents
                  corpusId={corpus.id}
                  maxDepth={4}
                  embedded={true}
                />
              </SidebarContent>
            </DocumentsSidebar>

            {/* Right: About content */}
            <AboutMainContent>
              <AboutHeader>
                <SectionLabel>About</SectionLabel>
                <AboutActions>
                  {canEdit && (
                    <TextButtonPrimary
                      onClick={onEditDescription}
                      aria-label={
                        hasContent ? "Edit description" : "Add description"
                      }
                    >
                      <Edit />
                      {hasContent ? "Edit" : "Add"}
                    </TextButtonPrimary>
                  )}
                </AboutActions>
              </AboutHeader>
              <AboutBody>
                <CorpusAbout
                  corpus={fullCorpus}
                  mdContent={mdContent}
                  isLoading={corpusLoading}
                  canEdit={canEdit}
                  onEditDescription={onEditDescription}
                  hideHeader={true}
                  testId={`${testId}-about`}
                />
              </AboutBody>
            </AboutMainContent>
          </TwoColumnLayout>

          {/* Mobile: Tabbed interface */}
          <MobileTabContainer>
            <MobileTabList role="tablist" aria-label="Corpus details tabs">
              <MobileTab
                role="tab"
                $active={mobileTab === "about"}
                onClick={() => setMobileTab("about")}
                aria-selected={mobileTab === "about"}
                aria-controls="mobile-about-panel"
                id="mobile-about-tab"
              >
                <BookOpen size={16} />
                About
              </MobileTab>
              <MobileTab
                role="tab"
                $active={mobileTab === "toc"}
                onClick={() => setMobileTab("toc")}
                aria-selected={mobileTab === "toc"}
                aria-controls="mobile-toc-panel"
                id="mobile-toc-tab"
              >
                <ListTree size={16} />
                Documents
              </MobileTab>
            </MobileTabList>

            <MobileTabContent
              role="tabpanel"
              id={
                mobileTab === "toc" ? "mobile-toc-panel" : "mobile-about-panel"
              }
              aria-labelledby={
                mobileTab === "toc" ? "mobile-toc-tab" : "mobile-about-tab"
              }
            >
              {mobileTab === "toc" ? (
                <>
                  <MobileDocToolbar>
                    <MobileSearchInput
                      type="text"
                      placeholder="Filter documents..."
                      aria-label="Filter documents"
                      value={docSearchQuery}
                      onChange={(e) => setDocSearchQuery(e.target.value)}
                    />
                    <ExpandButton
                      onClick={handleToggleExpandAll}
                      aria-label={isTocExpanded ? "Collapse all" : "Expand all"}
                    >
                      {isTocExpanded ? (
                        <>
                          <ChevronsDownUp />
                          Collapse
                        </>
                      ) : (
                        <>
                          <ChevronsUpDown />
                          Expand
                        </>
                      )}
                    </ExpandButton>
                  </MobileDocToolbar>
                  <DocumentTableOfContents
                    corpusId={corpus.id}
                    maxDepth={4}
                    embedded={true}
                    filterQuery={docSearchQuery}
                  />
                </>
              ) : (
                <>
                  {canEdit && (
                    <MobileAboutActions>
                      <TextButtonPrimary
                        onClick={onEditDescription}
                        aria-label={
                          hasContent ? "Edit description" : "Add description"
                        }
                      >
                        <Edit />
                        {hasContent ? "Edit" : "Add"}
                      </TextButtonPrimary>
                    </MobileAboutActions>
                  )}
                  <CorpusAbout
                    corpus={fullCorpus}
                    mdContent={mdContent}
                    isLoading={corpusLoading}
                    canEdit={canEdit}
                    onEditDescription={onEditDescription}
                    hideHeader={true}
                    testId={`${testId}-about-mobile`}
                  />
                </>
              )}
            </MobileTabContent>
          </MobileTabContainer>
        </DetailsMainContent>
      </DetailsPage>
    </DetailsContainer>
  );
};
