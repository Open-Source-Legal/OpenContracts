import React, { useEffect, useMemo } from "react";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import {
  ChevronRight,
  Users,
  Calendar,
  Globe,
  Shield,
  FileText,
  ArrowRight,
  Plus,
  Menu,
  BookOpen,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";

import {
  GET_CORPUS_WITH_HISTORY,
  GetCorpusWithHistoryQuery,
  GetCorpusWithHistoryQueryVariables,
} from "../../../graphql/queries";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { CorpusType } from "../../../types/graphql-api";
import { PermissionTypes } from "../../types";
import { getPermissions } from "../../../utils/transform";
import { getCreatorDisplay } from "../../../utils/userDisplay";
import { InlineChatBar } from "../CorpusHero/InlineChatBar";
import { MCPShareButton } from "../../common/MCPShareButton";
import { RecentDiscussions } from "./RecentDiscussions";

import {
  LandingContainer,
  LandingContent,
  LandingHero,
  CenteredBreadcrumbs,
  CorpusBadge,
  TitleRow,
  LandingTitle,
  LandingDescription,
  HeroImageBand,
  NoDescriptionContainer,
  NoDescriptionText,
  AddDescriptionLink,
  CenteredMetadataRow,
  MetadataItem,
  MetadataSeparator,
  AccessBadge,
  ChatSection,
  ViewDetailsButton,
  HeaderRow,
  MobileMenuButton,
} from "./styles";

const CreateArticleCTA = styled.button`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 1rem 1.25rem;
  margin-top: 0.5rem;
  background: none;
  border: 2px dashed ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.accent};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

const CTAIconCircle = styled.div`
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${OS_LEGAL_COLORS.textMuted};
  flex-shrink: 0;
`;

const CTATextGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
`;

const CTATitle = styled.span`
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const CTASubtitle = styled.span`
  font-size: 0.6875rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

export interface CorpusLandingViewProps {
  /** The corpus object */
  corpus: CorpusType;
  /** Whether a Readme.CAML article exists — provided by parent to avoid redundant query */
  hasArticle?: boolean;
  /** Callback when "View Details" is clicked */
  onViewDetails: () => void;
  /** Callback when edit description is clicked */
  onEditDescription: () => void;
  /** Callback to navigate back to corpus list */
  onNavigateToCorpuses?: () => void;
  /** Chat integration props */
  chatQuery?: string;
  onChatQueryChange?: (value: string) => void;
  onChatSubmit?: (query: string) => void;
  onViewChatHistory?: () => void;
  /** Callback to open mobile navigation menu */
  onOpenMobileMenu?: () => void;
  /** Callback when "View All Discussions" is clicked */
  onViewDiscussions?: () => void;
  /** Callback when "Read Article" is clicked */
  onViewArticle?: () => void;
  /** Callback when "Create Article" CTA is clicked */
  onOpenArticleEditor?: () => void;
  /** Callback when a specific thread is clicked from the feed */
  onThreadClick?: (threadId: string) => void;
  /** @deprecated Mode toggle is now rendered as a floating element by CorpusHome */
  onModeToggle?: () => void;
  /**
   * Whether the view is rendered from the power-user sidebar's home tab
   * (true) vs the clean/focus landing mode (false). Controls the toggle
   * button label ("Explore" vs "Manage").
   */
  isPowerUserMode?: boolean;
  /** Test ID for the component */
  testId?: string;
}

/**
 * CorpusLandingView - Centered landing page for corpus
 *
 * Features:
 * - Centered layout with max-width constraint
 * - CORPUS badge above title
 * - Large serif title
 * - Description as subtitle (or "no description" with add action)
 * - Metadata row (access badge, creator, date, doc count)
 * - InlineChatBar for querying
 * - "View Details" button to switch to details view
 */
export const CorpusLandingView: React.FC<CorpusLandingViewProps> = ({
  corpus,
  hasArticle: hasArticleProp,
  onViewDetails,
  onEditDescription,
  onNavigateToCorpuses,
  chatQuery = "",
  onChatQueryChange,
  onChatSubmit,
  onViewChatHistory,
  onOpenMobileMenu,
  onViewDiscussions,
  onViewArticle,
  onOpenArticleEditor,
  onThreadClick,
  isPowerUserMode = false,
  testId = "corpus-landing",
}) => {
  const [mdContent, setMdContent] = React.useState<string | null>(null);

  // CRITICAL: Memoize variables object to prevent Apollo refetch on every render
  const historyVariables = useMemo(() => ({ id: corpus.id }), [corpus.id]);

  // Fetch corpus with description history
  const { data: corpusData } = useQuery<
    GetCorpusWithHistoryQuery,
    GetCorpusWithHistoryQueryVariables
  >(GET_CORPUS_WITH_HISTORY, {
    variables: historyVariables,
  });

  const hasArticle = hasArticleProp ?? false;

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

  // Get plain text description - prefer markdown content, fallback to plain description
  // For hero subtitle, we use plain text only (no markdown rendering)
  const descriptionText = mdContent
    ? mdContent.split("\n")[0].slice(0, 200) // First line, max 200 chars
    : fullCorpus.description;

  const hasDescription = Boolean(descriptionText);

  return (
    <LandingContainer data-testid={testId}>
      <LandingContent>
        <LandingHero>
          <HeaderRow>
            <CenteredBreadcrumbs
              aria-label="Breadcrumb navigation"
              data-testid={`${testId}-breadcrumbs`}
            >
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onNavigateToCorpuses?.();
                }}
              >
                Corpuses
              </a>
              <ChevronRight aria-hidden="true" />
              <span className="current">
                {fullCorpus.title || "Untitled Corpus"}
              </span>
            </CenteredBreadcrumbs>
          </HeaderRow>

          {/* Metadata row — context first, before the title */}
          <CenteredMetadataRow data-testid={`${testId}-metadata`}>
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

            {/* MCP Share button — always shown for consistent discovery;
                popover content adapts based on whether the corpus is public. */}
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

          {/* Corpus badge */}
          <CorpusBadge>CORPUS</CorpusBadge>

          {/* Large title — with optional hamburger on mobile */}
          <TitleRow>
            {onOpenMobileMenu && isPowerUserMode && (
              <MobileMenuButton
                onClick={onOpenMobileMenu}
                aria-label="Open navigation menu"
                data-testid={`${testId}-mobile-menu`}
              >
                <Menu />
              </MobileMenuButton>
            )}
            <LandingTitle data-testid={`${testId}-title`}>
              {fullCorpus.title || "Untitled Corpus"}
            </LandingTitle>
          </TitleRow>

          {/* Hero image band — only rendered when corpus has an icon */}
          {fullCorpus.icon && (
            <HeroImageBand data-testid={`${testId}-hero-image`}>
              <img
                src={fullCorpus.icon}
                alt={`${fullCorpus.title || "Corpus"} cover image`}
                loading="lazy"
              />
            </HeroImageBand>
          )}

          {/* Description as subtitle or "no description" with action */}
          {hasDescription ? (
            <LandingDescription data-testid={`${testId}-description`}>
              {descriptionText}
            </LandingDescription>
          ) : (
            <NoDescriptionContainer data-testid={`${testId}-no-description`}>
              <NoDescriptionText>No description yet.</NoDescriptionText>
              {canEdit && (
                <AddDescriptionLink
                  onClick={onEditDescription}
                  data-testid={`${testId}-add-description-btn`}
                >
                  <Plus size={14} />
                  Add one now
                </AddDescriptionLink>
              )}
            </NoDescriptionContainer>
          )}
        </LandingHero>

        {/* Create article CTA — shown when no Readme.CAML and user can edit */}
        {!hasArticle && canEdit && onOpenArticleEditor && (
          <CreateArticleCTA
            onClick={onOpenArticleEditor}
            data-testid={`${testId}-create-article-cta`}
          >
            <CTAIconCircle>
              <BookOpen size={16} />
            </CTAIconCircle>
            <CTATextGroup>
              <CTATitle>Create an introductory article</CTATitle>
              <CTASubtitle>
                Write a rich article for this corpus using CAML
              </CTASubtitle>
            </CTATextGroup>
          </CreateArticleCTA>
        )}

        {/* Chat section */}
        <ChatSection>
          <InlineChatBar
            value={chatQuery}
            onChange={onChatQueryChange || (() => {})}
            onSubmit={onChatSubmit || (() => {})}
            onViewHistory={onViewChatHistory || (() => {})}
            autoFocus={true}
            showQuickActions={true}
            testId={`${testId}-chat`}
          />
        </ChatSection>

        {/* Read article — shown when Readme.CAML exists */}
        {hasArticle && onViewArticle && (
          <ViewDetailsButton
            onClick={onViewArticle}
            data-testid={`${testId}-view-article-btn`}
          >
            <BookOpen size={16} />
            Read the article
            <ArrowRight />
          </ViewDetailsButton>
        )}

        {/* Browse documents — subtle text link */}
        <ViewDetailsButton
          onClick={onViewDetails}
          data-testid={`${testId}-view-details-btn`}
        >
          Browse documents
          <ArrowRight />
        </ViewDetailsButton>

        {/* Recent discussions feed */}
        <RecentDiscussions
          corpusId={corpus.id}
          onThreadClick={onThreadClick}
          onViewAll={onViewDiscussions}
          testId={`${testId}-discussions`}
        />
      </LandingContent>
    </LandingContainer>
  );
};
