/**
 * CorpusContextSidebar - Displays corpus context when viewing thread details inline
 *
 * Features:
 * - About section with corpus description (markdown rendered)
 * - Documents section with table of contents
 * - Quick stats (documents, threads, annotations)
 * - Collapsible sections and responsive behavior
 */

import React, { useState } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { useAtom } from "jotai";
import {
  BookOpen,
  FileText,
  BarChart3,
  ChevronDown,
  X,
  PanelRightClose,
  PanelRightOpen,
  MessageSquare,
  Tag,
} from "lucide-react";
import { AnimatePresence } from "framer-motion";

import {
  GET_CORPUS_STATS,
  GetCorpusStatsOutputType,
  CorpusStats,
} from "../../graphql/queries";
import { openedCorpus } from "../../graphql/cache";
import { threadContextSidebarExpandedAtom } from "../../atoms/threadAtoms";
import { DocumentTableOfContents } from "../corpuses/DocumentTableOfContents";
import { SafeMarkdown } from "../knowledge_base/markdown/SafeMarkdown";
import useWindowDimensions from "../hooks/WindowDimensionHook";

import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  ContextSidebarContainer,
  SidebarHeader,
  SidebarTitle,
  ContextSidebarToggle,
  CollapsedSidebar,
  ExpandSidebarButton,
  SidebarContent,
  SidebarSection,
  SectionHeader,
  SectionTitle,
  SectionChevron,
  SectionContent,
  SectionInner,
  StatsGrid,
  StatItem,
  StatValue,
  StatLabel,
  CompactAboutWrapper,
  CompactTocWrapper,
  EmptySectionState,
  SIDEBAR_BREAKPOINT_HIDE,
  SIDEBAR_BREAKPOINT_COLLAPSE,
} from "./styles/contextSidebarStyles";

interface CorpusContextSidebarProps {
  corpusId: string;
}

/**
 * CorpusContextSidebar - Shows corpus context alongside thread details
 */
export const CorpusContextSidebar: React.FC<CorpusContextSidebarProps> =
  React.memo(({ corpusId }) => {
    const { width } = useWindowDimensions();
    const corpus = useReactiveVar(openedCorpus);
    const [isExpanded, setIsExpanded] = useAtom(
      threadContextSidebarExpandedAtom
    );

    // Section expansion states
    const [aboutExpanded, setAboutExpanded] = useState(true);
    const [docsExpanded, setDocsExpanded] = useState(true);
    const [statsExpanded, setStatsExpanded] = useState(true);

    // Determine if we're in collapsible mode (medium screens)
    const isCollapsible =
      width >= SIDEBAR_BREAKPOINT_HIDE && width < SIDEBAR_BREAKPOINT_COLLAPSE;

    // Fetch corpus stats
    const { data: statsData } = useQuery<
      GetCorpusStatsOutputType,
      { corpusId: string }
    >(GET_CORPUS_STATS, {
      variables: { corpusId },
      skip: !corpusId,
      fetchPolicy: "cache-and-network",
    });

    const stats: CorpusStats | null = statsData?.corpusStats ?? null;

    // `description` is the inline markdown (canonical-CAML projection).
    const description = corpus?.description || null;

    // Don't render on small screens
    if (width < SIDEBAR_BREAKPOINT_HIDE) {
      return null;
    }

    // Collapsed state (on medium screens when user collapsed it)
    if (isCollapsible && !isExpanded) {
      return (
        <ContextSidebarContainer
          $isExpanded={false}
          $isCollapsible={isCollapsible}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
        >
          <CollapsedSidebar>
            <ExpandSidebarButton
              onClick={() => setIsExpanded(true)}
              aria-label="Expand corpus context sidebar"
              title="Expand sidebar"
            >
              <PanelRightOpen />
            </ExpandSidebarButton>
          </CollapsedSidebar>
        </ContextSidebarContainer>
      );
    }

    return (
      <ContextSidebarContainer
        $isExpanded={isExpanded}
        $isCollapsible={isCollapsible}
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.3 }}
      >
        <SidebarHeader>
          <SidebarTitle>{corpus?.title || "Corpus Info"}</SidebarTitle>
          {isCollapsible && (
            <ContextSidebarToggle
              onClick={() => setIsExpanded(false)}
              aria-label="Collapse sidebar"
              title="Collapse sidebar"
            >
              <PanelRightClose />
            </ContextSidebarToggle>
          )}
        </SidebarHeader>

        <SidebarContent>
          {/* About Section */}
          <SidebarSection>
            <SectionHeader
              $isExpanded={aboutExpanded}
              onClick={() => setAboutExpanded(!aboutExpanded)}
              aria-expanded={aboutExpanded}
              aria-controls="sidebar-about-content"
            >
              <SectionTitle>
                <BookOpen />
                About
              </SectionTitle>
              <SectionChevron $isExpanded={aboutExpanded}>
                <ChevronDown />
              </SectionChevron>
            </SectionHeader>
            <AnimatePresence initial={false}>
              {aboutExpanded && (
                <SectionContent
                  id="sidebar-about-content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <SectionInner>
                    {description ? (
                      <CompactAboutWrapper>
                        <SafeMarkdown>{description}</SafeMarkdown>
                      </CompactAboutWrapper>
                    ) : (
                      <EmptySectionState>
                        <BookOpen />
                        <p>No description available</p>
                      </EmptySectionState>
                    )}
                  </SectionInner>
                </SectionContent>
              )}
            </AnimatePresence>
          </SidebarSection>

          {/* Documents Section */}
          <SidebarSection>
            <SectionHeader
              $isExpanded={docsExpanded}
              onClick={() => setDocsExpanded(!docsExpanded)}
              aria-expanded={docsExpanded}
              aria-controls="sidebar-docs-content"
            >
              <SectionTitle>
                <FileText />
                Documents
                {stats?.totalDocs != null && (
                  <span
                    style={{
                      fontWeight: 400,
                      color: OS_LEGAL_COLORS.textMuted,
                    }}
                  >
                    ({stats.totalDocs})
                  </span>
                )}
              </SectionTitle>
              <SectionChevron $isExpanded={docsExpanded}>
                <ChevronDown />
              </SectionChevron>
            </SectionHeader>
            <AnimatePresence initial={false}>
              {docsExpanded && (
                <SectionContent
                  id="sidebar-docs-content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <SectionInner>
                    <CompactTocWrapper>
                      <DocumentTableOfContents
                        corpusId={corpusId}
                        embedded
                        maxDepth={2}
                      />
                    </CompactTocWrapper>
                  </SectionInner>
                </SectionContent>
              )}
            </AnimatePresence>
          </SidebarSection>

          {/* Stats Section */}
          <SidebarSection>
            <SectionHeader
              $isExpanded={statsExpanded}
              onClick={() => setStatsExpanded(!statsExpanded)}
              aria-expanded={statsExpanded}
              aria-controls="sidebar-stats-content"
            >
              <SectionTitle>
                <BarChart3 />
                Quick Stats
              </SectionTitle>
              <SectionChevron $isExpanded={statsExpanded}>
                <ChevronDown />
              </SectionChevron>
            </SectionHeader>
            <AnimatePresence initial={false}>
              {statsExpanded && (
                <SectionContent
                  id="sidebar-stats-content"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <SectionInner>
                    <StatsGrid>
                      <StatItem>
                        <StatValue>{stats?.totalDocs ?? 0}</StatValue>
                        <StatLabel>Documents</StatLabel>
                      </StatItem>
                      <StatItem>
                        <StatValue>{stats?.totalThreads ?? 0}</StatValue>
                        <StatLabel>Discussions</StatLabel>
                      </StatItem>
                      <StatItem>
                        <StatValue>{stats?.totalAnnotations ?? 0}</StatValue>
                        <StatLabel>Annotations</StatLabel>
                      </StatItem>
                      <StatItem>
                        <StatValue>{stats?.totalComments ?? 0}</StatValue>
                        <StatLabel>Comments</StatLabel>
                      </StatItem>
                    </StatsGrid>
                  </SectionInner>
                </SectionContent>
              )}
            </AnimatePresence>
          </SidebarSection>
        </SidebarContent>
      </ContextSidebarContainer>
    );
  });

// Display name for React DevTools
CorpusContextSidebar.displayName = "CorpusContextSidebar";

export default CorpusContextSidebar;
