import { useEffect, useRef } from "react";
import { useLazyQuery } from "@apollo/client";

import {
  GET_ANALYSES_FOR_CORPUS_ENRICHMENT,
  GET_ANNOTATIONS_FOR_ANALYSIS,
  GetAnalysesForCorpusEnrichmentInputType,
  GetAnalysesForCorpusEnrichmentOutputType,
} from "../../../../graphql/queries";
import { ENRICHMENT_ANALYZER_TASK_NAME } from "../../../../assets/configurations/constants";
import { usePdfAnnotations } from "../../../annotator/hooks/AnnotationHooks";
import { convertToServerAnnotation } from "../../../../utils/transform";

/**
 * Auto-merge the corpus's reference-mention annotations into the document's
 * annotation layer.
 *
 * Analysis-created annotations are deliberately excluded from the default
 * document load (`AnnotationService.get_document_annotations` filters
 * `analysis__isnull=True` unless an analysis is explicitly selected) — the
 * right default for ML analyzer output the user opts into. Reference
 * mentions are different: they ARE the document's citation hyperlinks
 * (OC_REF_LAW / OC_REF_DOC spans whose `link_url` routes to the cited
 * statute section or exhibit), and a reader expects a statute's
 * cross-references to be visible and clickable without hunting for an
 * analysis selector.
 *
 * Flow: discover the corpus's reference-enrichment Analyses (matched on
 * `analyzer.taskName` — the corpus filter on the analyses query is loose, so
 * every matching analysis is tried; `fullAnnotationList(documentId)` scopes
 * each to this document), fetch their annotations via the existing
 * per-analysis query (which enforces analysis visibility server-side), and
 * merge them into `pdfAnnotations` — id-deduped, and gated one-shot per
 * (document, corpus) so Apollo's cache/network double emissions can't
 * double-insert.
 *
 * `ready` must be the document loader's settled state: the loader's
 * onCompleted REPLACES pdfAnnotations wholesale, so a merge dispatched
 * before it completes is silently wiped.
 */
export function useReferenceMentions(
  documentId: string,
  corpusId: string | undefined,
  ready: boolean
): void {
  const { pdfAnnotations, addMultipleAnnotations } = usePdfAnnotations();

  // One-shot gate per (document, corpus): "" means not yet merged.
  const mergedForRef = useRef<string>("");
  const mergeKey = `${documentId}:${corpusId ?? ""}`;

  const [discoverAnalyses] = useLazyQuery<
    GetAnalysesForCorpusEnrichmentOutputType,
    GetAnalysesForCorpusEnrichmentInputType
  >(GET_ANALYSES_FOR_CORPUS_ENRICHMENT, { fetchPolicy: "cache-first" });

  const [fetchMentions] = useLazyQuery(GET_ANNOTATIONS_FOR_ANALYSIS, {
    fetchPolicy: "cache-first",
  });

  // Keep a live ref of current annotations for the async merge below —
  // depending on `pdfAnnotations` directly would re-run the effect on every
  // annotation change (including our own merge).
  const annotationsRef = useRef(pdfAnnotations.annotations);
  annotationsRef.current = pdfAnnotations.annotations;

  useEffect(() => {
    if (!ready || !corpusId || !documentId) return;
    if (mergedForRef.current === mergeKey) return;
    mergedForRef.current = mergeKey;

    let cancelled = false;
    let succeeded = false;
    (async () => {
      try {
        const { data } = await discoverAnalyses({ variables: { corpusId } });
        const enrichmentAnalyses = (data?.analyses?.edges ?? [])
          .map((e) => e.node)
          .filter(
            (n) => n.analyzer?.taskName === ENRICHMENT_ANALYZER_TASK_NAME
          );
        if (cancelled) return;
        if (enrichmentAnalyses.length === 0) {
          // No enrichment analyses yet (e.g. still running). Release the
          // one-shot gate so a later effect run retries — committing it here
          // would strand the citations until a full remount.
          mergedForRef.current = "";
          return;
        }

        const fresh: ReturnType<typeof convertToServerAnnotation>[] = [];
        const existingIds = new Set(annotationsRef.current.map((a) => a.id));
        for (const analysis of enrichmentAnalyses) {
          const { data: annData } = await fetchMentions({
            variables: { analysisId: analysis.id, documentId },
          });
          if (cancelled) return;
          for (const ann of annData?.analysis?.fullAnnotationList ?? []) {
            if (!existingIds.has(ann.id)) {
              existingIds.add(ann.id);
              fresh.push(convertToServerAnnotation(ann));
            }
          }
        }
        if (fresh.length > 0) addMultipleAnnotations(fresh);
        succeeded = true;
      } catch (err) {
        // Transient failure (network / Apollo). Release the gate so the merge
        // can be retried rather than silently stuck.
        if (!cancelled) mergedForRef.current = "";
        console.warn(
          "useReferenceMentions: mention merge failed, will retry",
          err
        );
      }
    })();

    return () => {
      cancelled = true;
      // Release the gate if we tear down before the merge completed — covers a
      // fetch that hangs without resolving or throwing (the catch above never
      // fires), which would otherwise leave the gate committed and block any
      // retry while the component stays mounted.
      if (!succeeded) mergedForRef.current = "";
    };
  }, [
    ready,
    mergeKey,
    corpusId,
    documentId,
    discoverAnalyses,
    fetchMentions,
    addMultipleAnnotations,
  ]);
}
