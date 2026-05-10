import { useEffect, useState } from "react";

interface UseDocumentMarkdownReturn {
  /** Loaded MD summary text, or `null` if there's no summary or the fetch failed */
  markdownContent: string | null;
  /** True if the most recent fetch threw before resolving content */
  markdownError: boolean;
}

/**
 * Fetches the document's markdown summary file when one is published. The URL
 * comes from the GraphQL response (`document.mdSummaryFile`) — when it's
 * absent or the fetch fails, the content is cleared so the UI can fall back
 * to the corpus description / no-summary placeholder.
 */
export function useDocumentMarkdown(
  mdSummaryFile: string | null | undefined
): UseDocumentMarkdownReturn {
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [markdownError, setMarkdownError] = useState<boolean>(false);

  useEffect(() => {
    if (!mdSummaryFile) {
      setMarkdownContent(null);
      // Reset error state so a stale `true` from a previous document with a
      // broken summary URL doesn't bleed through after navigating to a
      // document that has no summary at all.
      setMarkdownError(false);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(mdSummaryFile);
        if (!response.ok) throw new Error("Failed to fetch markdown content");
        const text = await response.text();
        if (cancelled) return;
        setMarkdownContent(text);
        setMarkdownError(false);
      } catch (error) {
        if (cancelled) return;
        console.error("Error fetching markdown content:", error);
        setMarkdownContent(null);
        setMarkdownError(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mdSummaryFile]);

  return { markdownContent, markdownError };
}
