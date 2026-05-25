/**
 * GraphQL metadata fetching for OG previews
 *
 * Fetches minimal metadata from the cite backend API
 * for generating Open Graph tags. Only returns data for public entities.
 */

import type {
  Env,
  EntityType,
  ParsedRoute,
  OGMetadata,
  LabeledData,
  GraphQLResponse,
  OGCorpusData,
  OGDocumentData,
  OGThreadData,
  OGExtractData,
} from "./types";

/**
 * GraphQL query definitions for each entity type
 */
const QUERIES: Record<EntityType, string> = {
  corpus: `
    query OGCorpus($userSlug: String!, $corpusSlug: String!) {
      ogCorpusMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug) {
        title
        description
        iconUrl
        documentCount
        creatorName
        isPublic
      }
    }
  `,

  document: `
    query OGDocument($userSlug: String!, $documentSlug: String!) {
      ogDocumentMetadata(userSlug: $userSlug, documentSlug: $documentSlug) {
        title
        description
        iconUrl
        corpusTitle
        creatorName
        isPublic
      }
    }
  `,

  document_in_corpus: `
    query OGDocumentInCorpus($userSlug: String!, $corpusSlug: String!, $documentSlug: String!) {
      ogDocumentInCorpusMetadata(
        userSlug: $userSlug
        corpusSlug: $corpusSlug
        documentSlug: $documentSlug
      ) {
        title
        description
        iconUrl
        corpusTitle
        corpusDescription
        creatorName
        isPublic
      }
    }
  `,

  thread: `
    query OGThread($userSlug: String!, $corpusSlug: String!, $threadId: String!) {
      ogThreadMetadata(userSlug: $userSlug, corpusSlug: $corpusSlug, threadId: $threadId) {
        title
        corpusTitle
        messageCount
        creatorName
        isPublic
      }
    }
  `,

  extract: `
    query OGExtract($extractId: String!) {
      ogExtractMetadata(extractId: $extractId) {
        name
        corpusTitle
        fieldsetName
        creatorName
        isPublic
      }
    }
  `,
};

/**
 * Build GraphQL variables from parsed route
 */
function buildVariables(route: ParsedRoute): Record<string, string> {
  const vars: Record<string, string> = {};

  if (route.userSlug) vars.userSlug = route.userSlug;
  if (route.corpusSlug) vars.corpusSlug = route.corpusSlug;
  if (route.documentSlug) vars.documentSlug = route.documentSlug;
  if (route.extractId) vars.extractId = route.extractId;
  if (route.threadId) vars.threadId = route.threadId;

  return vars;
}

/**
 * Fetch OG metadata from the backend API
 *
 * @param route - Parsed route information
 * @param env - Worker environment bindings
 * @returns OG metadata or null if entity not found/not public
 */
export async function fetchOGMetadata(
  route: ParsedRoute,
  env: Env
): Promise<OGMetadata | null> {
  const query = QUERIES[route.type];
  if (!query) {
    console.error(`No query defined for entity type: ${route.type}`);
    return null;
  }

  const variables = buildVariables(route);

  try {
    const response = await fetch(`${env.API_URL}/graphql/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        // No auth header - these are public queries
      },
      body: JSON.stringify({ query, variables }),
    });

    if (!response.ok) {
      console.error(`GraphQL request failed with status ${response.status}`);
      return null;
    }

    const json = (await response.json()) as GraphQLResponse;

    if (json.errors && json.errors.length > 0) {
      console.error("GraphQL errors:", json.errors);
      return null;
    }

    return extractMetadata(route.type, json.data, env);
  } catch (error) {
    console.error("Failed to fetch OG metadata:", error);
    return null;
  }
}

/**
 * Build a pluralized document count string (e.g. "1 document", "5 documents")
 */
function formatDocCount(count: number): string {
  return `${count} document${count !== 1 ? "s" : ""}`;
}

/**
 * Compose a corpus description that leads with the user-provided description
 * and appends the document count for additional context.
 */
function composeCorpusDescription(
  userDescription: string | undefined | null,
  documentCount: number
): string {
  const docCountStr = formatDocCount(documentCount);
  const desc = userDescription?.trim();
  if (desc) {
    return `${desc} \u2014 ${docCountStr}`;
  }
  return `A corpus with ${docCountStr}`;
}

/**
 * Compose a document-in-corpus description that provides corpus context
 * when the document itself lacks a description.
 */
function composeDocInCorpusDescription(
  docDescription: string | undefined | null,
  corpusTitle: string | undefined | null,
  corpusDescription: string | undefined | null
): string {
  const docDesc = docDescription?.trim();
  const corpusDesc = corpusDescription?.trim();

  if (docDesc) {
    // Document has its own description; append corpus context
    if (corpusTitle) {
      return `${docDesc} \u2014 from ${corpusTitle}`;
    }
    return docDesc;
  }

  // No document description — use corpus context
  if (corpusTitle && corpusDesc) {
    return `From ${corpusTitle}: ${corpusDesc}`;
  }
  if (corpusTitle) {
    return `Document in ${corpusTitle}`;
  }
  return "Document on cite.opensource.legal";
}

/**
 * Extract and normalize metadata from GraphQL response
 */
function extractMetadata(
  type: EntityType,
  data: unknown,
  env: Env
): OGMetadata | null {
  switch (type) {
    case "corpus": {
      const corpus = (data as OGCorpusData).ogCorpusMetadata;
      if (!corpus || !corpus.isPublic) return null;

      const labeledData: LabeledData[] = [
        { label: "Documents", value: formatDocCount(corpus.documentCount) },
        { label: "Author", value: corpus.creatorName },
      ];

      return {
        title: corpus.title,
        description: composeCorpusDescription(
          corpus.description,
          corpus.documentCount
        ),
        image: corpus.iconUrl || `${env.OG_IMAGE_BASE}/corpus-og.png`,
        type,
        entityName: corpus.title,
        creatorName: corpus.creatorName,
        documentCount: corpus.documentCount,
        labeledData,
      };
    }

    case "document": {
      const doc = (data as OGDocumentData).ogDocumentMetadata;
      if (!doc || !doc.isPublic) return null;

      const labeledData: LabeledData[] = [
        { label: "Author", value: doc.creatorName },
      ];
      if (doc.corpusTitle) {
        labeledData.unshift({ label: "Corpus", value: doc.corpusTitle });
      }

      return {
        title: doc.title,
        description: doc.description || "Document on cite.opensource.legal",
        image: doc.iconUrl || `${env.OG_IMAGE_BASE}/document-og.png`,
        type,
        entityName: doc.title,
        creatorName: doc.creatorName,
        corpusTitle: doc.corpusTitle || undefined,
        labeledData,
      };
    }

    case "document_in_corpus": {
      // Uses same response type as document
      const doc = (
        data as { ogDocumentInCorpusMetadata: OGDocumentData["ogDocumentMetadata"] }
      ).ogDocumentInCorpusMetadata;
      if (!doc || !doc.isPublic) return null;

      const labeledData: LabeledData[] = [
        { label: "Author", value: doc.creatorName },
      ];
      if (doc.corpusTitle) {
        labeledData.unshift({ label: "Corpus", value: doc.corpusTitle });
      }

      return {
        title: doc.title,
        description: composeDocInCorpusDescription(
          doc.description,
          doc.corpusTitle,
          doc.corpusDescription
        ),
        image: doc.iconUrl || `${env.OG_IMAGE_BASE}/document-og.png`,
        type,
        entityName: doc.title,
        creatorName: doc.creatorName,
        corpusTitle: doc.corpusTitle || undefined,
        labeledData,
      };
    }

    case "thread": {
      const thread = (data as OGThreadData).ogThreadMetadata;
      if (!thread || !thread.isPublic) return null;

      const messageStr = `${thread.messageCount} message${thread.messageCount !== 1 ? "s" : ""}`;
      const labeledData: LabeledData[] = [
        { label: "Corpus", value: thread.corpusTitle },
        { label: "Messages", value: messageStr },
      ];

      return {
        title: thread.title || "Discussion",
        description: `Discussion in ${thread.corpusTitle} \u2014 ${messageStr}`,
        image: `${env.OG_IMAGE_BASE}/discussion-og.png`,
        type,
        entityName: thread.title || "Discussion",
        creatorName: thread.creatorName,
        corpusTitle: thread.corpusTitle,
        labeledData,
      };
    }

    case "extract": {
      const extract = (data as OGExtractData).ogExtractMetadata;
      if (!extract || !extract.isPublic) return null;

      const labeledData: LabeledData[] = [
        { label: "Fieldset", value: extract.fieldsetName },
        { label: "Corpus", value: extract.corpusTitle },
      ];

      return {
        title: extract.name,
        description: `Data extraction using ${extract.fieldsetName} on ${extract.corpusTitle}`,
        image: `${env.OG_IMAGE_BASE}/extract-og.png`,
        type,
        entityName: extract.name,
        creatorName: extract.creatorName,
        corpusTitle: extract.corpusTitle,
        labeledData,
      };
    }

    default:
      return null;
  }
}
