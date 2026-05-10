import React from "react";
import { Helmet } from "react-helmet-async";
import { useLocation } from "react-router-dom";
import { CorpusType, DocumentType, ExtractType } from "../../types/graphql-api";
import { buildCanonicalPath } from "../../utils/navigationUtils";
import { getCreatorDisplay } from "../../utils/userDisplay";

// Note: You'll need to install react-helmet-async:
// yarn add react-helmet-async
// And wrap your app with HelmetProvider in index.tsx

interface MetaTagsProps {
  title?: string;
  description?: string;
  canonicalPath?: string;
  entity?: CorpusType | DocumentType | ExtractType | null;
  entityType?: "corpus" | "document" | "extract";
}

/**
 * Centralized component for managing SEO meta tags.
 * Uses React Helmet for declarative meta tag management.
 */
export const MetaTags: React.FC<MetaTagsProps> = ({
  title,
  description,
  canonicalPath,
  entity,
  entityType,
}) => {
  const location = useLocation();
  const baseUrl = window.location.origin;

  // Derive meta values from entity if not explicitly provided
  let pageTitle = title || "OpenContracts";
  let pageDescription = description || "Legal document analysis platform";

  if (!title && entity) {
    if ("title" in entity) {
      pageTitle = entity.title || pageTitle;
    } else if ("name" in entity) {
      pageTitle = entity.name || pageTitle;
    }
  }

  if (!description && entity && "description" in entity) {
    pageDescription = entity.description || pageDescription;
  }

  // Build canonical URL using shared utility for consistency
  // Uses buildCanonicalPath from navigationUtils which handles /c/, /d/, /e/ prefixes
  let canonical = canonicalPath;
  if (!canonical && entity && entityType) {
    // Pass entity to buildCanonicalPath based on type
    switch (entityType) {
      case "corpus":
        canonical = buildCanonicalPath(null, entity as CorpusType, null);
        break;
      case "document":
        canonical = buildCanonicalPath(entity as DocumentType, null, null);
        break;
      case "extract":
        canonical = buildCanonicalPath(null, null, entity as ExtractType);
        break;
      default:
        // Warn in development if entityType is unexpected
        if (process.env.NODE_ENV === "development") {
          console.warn(
            `MetaTags: Unexpected entityType "${entityType}". ` +
              `Expected "corpus", "document", or "extract".`
          );
        }
    }
  }
  const canonicalUrl = canonical
    ? `${baseUrl}${canonical}`
    : `${baseUrl}${location.pathname}`;

  // OpenGraph image
  const ogImage = `${baseUrl}/og-image.png`; // You should add a default OG image

  return (
    <Helmet>
      {/* Primary Meta Tags */}
      <title>{pageTitle}</title>
      <meta name="title" content={pageTitle} />
      <meta name="description" content={pageDescription} />
      <link rel="canonical" href={canonicalUrl} />

      {/* Open Graph / Facebook */}
      <meta property="og:type" content="website" />
      <meta property="og:url" content={canonicalUrl} />
      <meta property="og:title" content={pageTitle} />
      <meta property="og:description" content={pageDescription} />
      <meta property="og:image" content={ogImage} />

      {/* Twitter */}
      <meta property="twitter:card" content="summary_large_image" />
      <meta property="twitter:url" content={canonicalUrl} />
      <meta property="twitter:title" content={pageTitle} />
      <meta property="twitter:description" content={pageDescription} />
      <meta property="twitter:image" content={ogImage} />

      {/* Additional meta tags for entity-specific pages */}
      {entity && (
        <>
          <meta name="author" content={getCreatorDisplay(entity.creator)} />
          {"isPublic" in entity && entity.isPublic === false && (
            <meta name="robots" content="noindex, nofollow" />
          )}
        </>
      )}
    </Helmet>
  );
};

/**
 * Hook to easily set meta tags from any component
 */
export function useMetaTags(props: MetaTagsProps) {
  return <MetaTags {...props} />;
}
