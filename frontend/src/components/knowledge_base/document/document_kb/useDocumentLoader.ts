import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@apollo/client";
import { unstable_batchedUpdates } from "react-dom";
import { toast } from "react-toastify";
import { getDocument, PDFDocumentLoadingTask } from "pdfjs-dist";
import {
  PDFDocumentProxy,
  PDFPageProxy,
} from "pdfjs-dist/types/src/display/api";
import { useAtom } from "jotai";
import {
  GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS,
  GetDocumentKnowledgeAndAnnotationsInput,
  GetDocumentKnowledgeAndAnnotationsOutput,
  GET_DOCUMENT_WITH_STRUCTURE,
  GetDocumentWithStructureInput,
  GetDocumentWithStructureOutput,
  GET_DOCUMENT_ANNOTATIONS_ONLY,
  GetDocumentAnnotationsOnlyInput,
  GetDocumentAnnotationsOnlyOutput,
  GET_CONVERSATIONS,
  GetConversationsInputs,
  GetConversationsOutputs,
} from "../../../../graphql/queries";
import { CorpusType, LabelType } from "../../../../types/graphql-api";
import {
  getDocumentRawText,
  getDocxBytes,
  getPawlsLayer,
  getCachedPDFUrl,
} from "../../../annotator/api/cachedRest";
import {
  useDocText,
  useDocumentPermissions,
  useDocumentState,
  useDocumentType,
  usePages,
  usePageTokenTextMaps,
  usePdfDoc,
  useDocxBytes,
} from "../../../annotator/context/DocumentAtom";
import { pdfAnnotationsAtom } from "../../../annotator/context/AnnotationAtoms";
import {
  CorpusState,
  useCorpusState,
} from "../../../annotator/context/CorpusAtom";
import { useInitialAnnotations } from "../../../annotator/hooks/AnnotationHooks";
import { useUISettings } from "../../../annotator/hooks/useUISettings";
import {
  PdfAnnotations,
  RelationGroup,
} from "../../../annotator/types/annotations";
import { PDFPageInfo } from "../../../annotator/types/pdf";
import { PageTokens } from "../../../types";
import { ViewState } from "../../../types";
import {
  convertToDocTypeAnnotations,
  convertToServerAnnotation,
  getPermissions,
  resolvePageTokens,
} from "../../../../utils/transform";
import { createTokenStringSearch } from "../../../annotator/utils";
import {
  isDocxFileType,
  isPdfFileType,
  isTextFileType,
} from "../../../../utils/files";
import { routingLogger } from "../../../../utils/routingLogger";
import { relationToGroup } from "./helpers";

/**
 * Sentinel rejection used to short-circuit the PDF promise chain when a
 * mid-flight load is cancelled (doc switch / unmount). Carrying this through
 * a typed rejection lets the catch handler distinguish cancellation from a
 * real load failure without having to inspect the global ``cancelled`` flag.
 */
class DocumentLoadCancelled extends Error {
  constructor() {
    super("Document body load cancelled");
    this.name = "DocumentLoadCancelled";
  }
}

interface UseDocumentLoaderParams {
  documentId: string;
  corpusId?: string;
  authReady: boolean;
  zoomLevel: number;
  setProgress: ReturnType<typeof useUISettings>["setProgress"];
  selectedAnalysisId: string | null;
  selectedExtractId: string | null;
}

type DocumentBodyData = {
  id: string;
  fileType?: string | null;
  pdfFile?: string | null;
  pdfFileHash?: string | null;
  pawlsParseFile?: string | null;
  txtExtractFile?: string | null;
};

interface UseDocumentLoaderReturn {
  /** Apollo query result for the corpus-context query (undefined when no corpusId) */
  corpusData: GetDocumentKnowledgeAndAnnotationsOutput | undefined;
  /** Apollo query result for the no-corpus query (undefined when corpusId provided) */
  documentOnlyData: GetDocumentWithStructureOutput | undefined;
  /** Currently active dataset — either `corpusData` or `documentOnlyData` */
  combinedData:
    | GetDocumentKnowledgeAndAnnotationsOutput
    | GetDocumentWithStructureOutput
    | undefined;
  /** True while either main document query is in flight */
  loading: boolean;
  /** First non-benign error from either main query */
  queryError: Error | undefined;
  /** Refetch handle for whichever main query is active */
  refetch: () => Promise<unknown>;
  /** Document body load state — separate from query loading */
  viewState: ViewState;
  /** Number of discussion threads on the document (for the badge) */
  threadCount: number;
}

/**
 * Owns every async fetch + side-effect needed to populate the
 * DocumentKnowledgeBase view:
 *
 * 1. Corpus query (`GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS`) — when a
 *    corpusId is present, this brings down annotations, relationships, notes,
 *    and the corpus label set in one shot.
 * 2. Document-only query (`GET_DOCUMENT_WITH_STRUCTURE`) — fallback when no
 *    corpus is bound; brings down document metadata + structural
 *    relationships (no annotations).
 * 3. Annotations-only query (`GET_DOCUMENT_ANNOTATIONS_ONLY`) — refetched
 *    whenever the user switches between analyses or extracts so we don't
 *    re-pay for the heavy corpus-context query.
 * 4. Thread count query (`GET_CONVERSATIONS`) — feeds the discussions tab
 *    badge.
 *
 * Both main queries share the same dispatch path for loading the document
 * body (PDF / TXT / DOCX) — see `loadDocumentBody`. PDF loading differs only
 * in that the corpus path can route through the cached-URL helper, while the
 * no-corpus path goes direct to `getDocument(pdfFile)`. All other branches
 * are identical.
 */
export function useDocumentLoader({
  documentId,
  corpusId,
  authReady,
  zoomLevel,
  setProgress,
  selectedAnalysisId,
  selectedExtractId,
}: UseDocumentLoaderParams): UseDocumentLoaderReturn {
  const [viewState, setViewState] = useState<ViewState>(ViewState.LOADING);
  // Single cancellation handle shared across PDF / TXT / DOCX body loads:
  // a doc switch (or unmount) mid-load must prevent the in-flight promise
  // chain from writing into the *next* document's atoms. Each branch
  // installs a fresh canceller before kicking off its fetch and reads the
  // captured ``cancelled`` flag inside every settle handler.
  const bodyLoadCancelRef = useRef<() => void>(() => {});

  const { setDocumentType } = useDocumentType();
  const { setDocument } = useDocumentState();
  const { setDocText } = useDocText();
  const { setDocxBytes } = useDocxBytes();
  const {
    pageTokenTextMaps: pageTextMaps,
    setPageTokenTextMaps: setPageTextMaps,
  } = usePageTokenTextMaps();
  const { setPages } = usePages();
  const { setPdfDoc } = usePdfDoc();
  const { setPermissions } = useDocumentPermissions();
  const { setCorpus } = useCorpusState();
  const { setInitialAnnotations, setInitialRelations } =
    useInitialAnnotations();
  const [, setPdfAnnotations] = useAtom(pdfAnnotationsAtom);

  /**
   * DOCX body loader. Cancellable via `bodyLoadCancelRef` so a doc switch
   * mid-load doesn't write stale bytes/text into the new document's atoms.
   */
  const loadDocxDocument = useCallback(
    (doc: DocumentBodyData) => {
      if (!doc.pdfFile) return;

      bodyLoadCancelRef.current();
      let cancelled = false;
      bodyLoadCancelRef.current = () => {
        cancelled = true;
      };

      setViewState(ViewState.LOADING);
      setDocxBytes(null);

      const docxPromise = getDocxBytes(doc.pdfFile);
      const textPromise = doc.txtExtractFile
        ? getDocumentRawText(
            doc.txtExtractFile,
            doc.id,
            doc.pdfFileHash ?? undefined
          )
        : Promise.resolve("");

      Promise.all([docxPromise, textPromise])
        .then(([bytes, txt]) => {
          if (cancelled) return;
          routingLogger.debug(
            "[DOCX Load] Batching DOCX completion state updates"
          );
          unstable_batchedUpdates(() => {
            setDocxBytes(bytes);
            setDocText(txt);
            setViewState(ViewState.LOADED);
          });
          routingLogger.debug("=== DOCUMENT LOAD COMPLETE ===");
        })
        .catch((err) => {
          if (cancelled) return;
          setViewState(ViewState.ERROR);
          routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
          toast.error(
            `Error loading DOCX content: ${
              err instanceof Error ? err.message : String(err)
            }`
          );
        });
    },
    [setDocxBytes, setDocText]
  );

  /**
   * Apply the bulk corpus payload — annotations, doc-type annotations,
   * relationships, corpus permissions, and the corpus label set — to all
   * of the relevant atoms in one go.
   */
  const processAnnotationsData = useCallback(
    (data: GetDocumentKnowledgeAndAnnotationsOutput) => {
      if (!data?.document) return;

      const processedAnnotations =
        data.document.allAnnotations?.map((annotation) =>
          convertToServerAnnotation(annotation)
        ) ?? [];

      const processedDocTypeAnnotations = convertToDocTypeAnnotations(
        data.document.allAnnotations?.filter(
          (ann) => ann.annotationLabel.labelType === LabelType.DocTypeLabel
        ) ?? []
      );

      // Backend filters out analysis relationships when analysisId is unset.
      const processedRelationships =
        data.document.allRelationships?.map((rel) => relationToGroup(rel)) ??
        [];

      setInitialAnnotations(processedAnnotations);
      setInitialRelations(processedRelationships);

      // Single setPdfAnnotations call merges non-structural annotations,
      // relationships and doc-types — avoids the intermediate render that a
      // split annotations-then-relationships update would cause when this
      // runs in Apollo's onCompleted (outside React's automatic batching).
      // Structural annotations are loaded lazily — see useStructuralAnnotations.
      setPdfAnnotations(
        () =>
          new PdfAnnotations(
            processedAnnotations,
            processedRelationships,
            processedDocTypeAnnotations,
            true
          )
      );

      const corpusUpdatePayload: Partial<CorpusState> = {};
      if (data.corpus?.myPermissions) {
        corpusUpdatePayload.myPermissions = getPermissions(
          data.corpus.myPermissions
        );
      }
      if (data.corpus?.labelSet) {
        const allLabels = data.corpus.labelSet.allAnnotationLabels ?? [];
        corpusUpdatePayload.spanLabels = allLabels.filter(
          (label) => label.labelType === LabelType.SpanLabel
        );
        corpusUpdatePayload.humanSpanLabels = corpusUpdatePayload.spanLabels;
        corpusUpdatePayload.relationLabels = allLabels.filter(
          (label) => label.labelType === LabelType.RelationshipLabel
        );
        corpusUpdatePayload.docTypeLabels = allLabels.filter(
          (label) => label.labelType === LabelType.DocTypeLabel
        );
        corpusUpdatePayload.humanTokenLabels = allLabels.filter(
          (label) => label.labelType === LabelType.TokenLabel
        );
      }
      if (data.corpus) {
        corpusUpdatePayload.selectedCorpus = data.corpus as CorpusType;
      }
      if (Object.keys(corpusUpdatePayload).length > 0) {
        setCorpus(corpusUpdatePayload);
      }

      setPermissions(getPermissions(data.document.myPermissions));
    },
    [
      setPdfAnnotations,
      setInitialAnnotations,
      setInitialRelations,
      setCorpus,
      setPermissions,
    ]
  );

  /**
   * Lightweight refresh used when switching analyses/extracts — replaces
   * non-structural annotations + relationships without re-fetching the rest
   * of the corpus payload. Doc-types and structural annotations are
   * preserved across the swap.
   */
  const processAnnotationsOnlyData = useCallback(
    (data: GetDocumentAnnotationsOnlyOutput) => {
      if (!data?.document) return;

      const processedAnnotations =
        data.document.allAnnotations?.map((annotation) =>
          convertToServerAnnotation(annotation)
        ) ?? [];

      const processedRelationships =
        data.document.allRelationships?.map((rel) => relationToGroup(rel)) ??
        [];

      // Preserve previously-loaded doc-type annotations across analysis /
      // extract switches — only annotations + relationships are replaced.
      // Single setPdfAnnotations call avoids the intermediate render that
      // splitting annotations-then-relationships would cause when this runs
      // in Apollo's onCompleted (outside React's automatic batching).
      setPdfAnnotations(
        (prev) =>
          new PdfAnnotations(
            processedAnnotations,
            processedRelationships,
            prev.docTypes,
            true
          )
      );
    },
    [setPdfAnnotations]
  );

  /**
   * Build the page-list from a loaded `pdfDocProxy` + decoded PAWLS data.
   * Both query paths share the page-construction loop — the only delta is
   * upstream (cached URL vs direct).
   */
  const buildPdfPages = useCallback(
    (
      pdfDocProxy: PDFDocumentProxy,
      pawlsData: PageTokens[] | null | undefined
    ): Promise<PDFPageInfo[]> => {
      const loadPagesPromises: Promise<PDFPageInfo>[] = [];
      for (let i = 1; i <= pdfDocProxy.numPages; i++) {
        const pageNum = i;
        // pdfjs-dist's `.getPage(...).then(...)` declares its return as
        // `PDFPromise` (a non-thenable wrapper) instead of a real `Promise`,
        // so TS rejects assigning it to `Promise<PDFPageInfo>`. The runtime
        // value IS Promise-shaped; the double cast bridges the type system.
        loadPagesPromises.push(
          pdfDocProxy.getPage(pageNum).then((p: PDFPageProxy) => {
            const viewport = p.getViewport({ scale: 1 });
            const pageTokens = resolvePageTokens(
              pawlsData,
              p.pageNumber - 1,
              viewport.width,
              viewport.height,
              pageNum
            );
            return new PDFPageInfo(p, pageTokens, zoomLevel);
          }) as unknown as Promise<PDFPageInfo>
        );
      }
      return Promise.all(loadPagesPromises);
    },
    [zoomLevel]
  );

  const finalizePdfLoad = useCallback(
    (loadedPages: PDFPageInfo[]) => {
      routingLogger.debug(
        "[PDF Load] 🔄 Batching PDF completion state updates"
      );
      unstable_batchedUpdates(() => {
        setPages(loadedPages);
        const { doc_text, string_index_token_map } =
          createTokenStringSearch(loadedPages);
        // Functional updater so we always merge against the current map even
        // if a stale closure capture slipped in across the async PDF load —
        // also keeps `pageTextMaps` out of the dep array.
        setPageTextMaps((prev) => ({ ...string_index_token_map, ...prev }));
        setDocText(doc_text);
        setDocxBytes(null);
        setViewState(ViewState.LOADED);
      });
      routingLogger.debug("=== DOCUMENT LOAD COMPLETE ===");
    },
    [setPages, setPageTextMaps, setDocText, setDocxBytes]
  );

  /**
   * Branch-by-filetype dispatcher shared between both `onCompleted` handlers.
   * `useCachedFetch` picks between the corpus-aware cached helpers
   * (`getCachedPDFUrl` / `getDocumentRawText` with hash) and the direct
   * fetches used by the no-corpus query path.
   */
  const loadDocumentBody = useCallback(
    (doc: DocumentBodyData, useCachedFetch: boolean) => {
      const fileType = doc.fileType ?? "";

      if (isPdfFileType(fileType) && doc.pdfFile) {
        routingLogger.debug("\n=== DOCUMENT LOAD START ===");
        routingLogger.debug("Type: PDF");
        routingLogger.debug("Document ID:", doc.id);
        routingLogger.debug("Hash:", doc.pdfFileHash || "no hash");

        bodyLoadCancelRef.current();
        let cancelled = false;
        bodyLoadCancelRef.current = () => {
          cancelled = true;
        };

        setViewState(ViewState.LOADING);

        const pawlsPath = doc.pawlsParseFile || "";
        const pdfHash = doc.pdfFileHash || "";
        const pdfUrlPromise = useCachedFetch
          ? getCachedPDFUrl(doc.pdfFile, doc.id, pdfHash)
          : Promise.resolve(doc.pdfFile);
        const pawlsPromise = useCachedFetch
          ? getPawlsLayer(pawlsPath, doc.id)
          : getPawlsLayer(pawlsPath);

        pdfUrlPromise
          .then((pdfUrl) => {
            if (cancelled) return Promise.reject(new DocumentLoadCancelled());
            const loadingTask: PDFDocumentLoadingTask = getDocument(pdfUrl);
            loadingTask.onProgress = (p: { loaded: number; total: number }) => {
              if (cancelled) return;
              setProgress(Math.round((p.loaded / p.total) * 100));
            };
            return Promise.all([loadingTask.promise, pawlsPromise]);
          })
          .then(([pdfDocProxy, pawlsData]) => {
            if (cancelled) return;
            if (!pawlsData) {
              console.error(
                "onCompleted: PAWLS data received is null or undefined!"
              );
            }
            if (!pdfDocProxy) {
              throw new Error("PDF document proxy is null or undefined.");
            }
            setPdfDoc(pdfDocProxy);
            return buildPdfPages(pdfDocProxy, pawlsData);
          })
          .then((pages) => {
            if (cancelled || !pages) return;
            finalizePdfLoad(pages);
          })
          .catch((err) => {
            if (cancelled || err instanceof DocumentLoadCancelled) return;
            console.error("Error during PDF/PAWLS loading Promise.all:", err);
            routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
            setViewState(ViewState.ERROR);
            toast.error(
              `Error loading PDF details: ${
                err instanceof Error ? err.message : String(err)
              }`
            );
          });
        return;
      }

      if (isTextFileType(fileType) && doc.txtExtractFile) {
        routingLogger.debug("\n=== DOCUMENT LOAD START ===");
        routingLogger.debug("Type: TEXT");
        routingLogger.debug("Document ID:", doc.id);
        routingLogger.debug("Hash:", doc.pdfFileHash || "no hash");
        routingLogger.debug("File URL:", doc.txtExtractFile);

        bodyLoadCancelRef.current();
        let cancelled = false;
        bodyLoadCancelRef.current = () => {
          cancelled = true;
        };

        setViewState(ViewState.LOADING);
        const textPromise = useCachedFetch
          ? getDocumentRawText(
              doc.txtExtractFile,
              doc.id,
              doc.pdfFileHash ?? undefined
            )
          : getDocumentRawText(doc.txtExtractFile);

        textPromise
          .then((txt) => {
            if (cancelled) return;
            routingLogger.debug(
              "[Text Load] Batching text completion state updates"
            );
            unstable_batchedUpdates(() => {
              setDocText(txt);
              setDocxBytes(null);
              setViewState(ViewState.LOADED);
            });
            routingLogger.debug("=== DOCUMENT LOAD COMPLETE ===");
          })
          .catch((err) => {
            if (cancelled) return;
            setViewState(ViewState.ERROR);
            routingLogger.debug("=== DOCUMENT LOAD FAILED ===");
            toast.error(
              `Error loading text content: ${
                err instanceof Error ? err.message : String(err)
              }`
            );
          });
        return;
      }

      if (isDocxFileType(fileType) && doc.pdfFile) {
        routingLogger.debug("\n=== DOCUMENT LOAD START ===");
        routingLogger.debug("Type: DOCX");
        routingLogger.debug("Document ID:", doc.id);
        routingLogger.debug("Hash:", doc.pdfFileHash || "no hash");
        routingLogger.debug("DOCX URL:", doc.pdfFile);
        loadDocxDocument(doc);
        return;
      }

      console.warn(
        "onCompleted: Unsupported file type or missing file path.",
        fileType
      );
      setViewState(ViewState.ERROR);
    },
    [
      buildPdfPages,
      finalizePdfLoad,
      loadDocxDocument,
      setDocText,
      setDocxBytes,
      setPdfDoc,
      setProgress,
    ]
  );

  /**
   * Apply the document metadata + permissions atoms in a single batched
   * update. Shared prelude for both query paths.
   */
  const applyDocumentMetadata = useCallback(
    (
      doc: NonNullable<GetDocumentKnowledgeAndAnnotationsOutput["document"]>
    ) => {
      unstable_batchedUpdates(() => {
        setDocumentType(doc.fileType ?? "");
        const processedDocData = {
          ...doc,
          myPermissions: doc.myPermissions ?? [],
        };
        // The `selectedDocument` atom takes the legacy nested DocumentType
        // shape that includes Apollo edges/__typename — the cast bridges the
        // GraphQL query result (a partial subset) into that legacy shape
        // without rebuilding every consumer. Replace once the atom is
        // re-typed to accept the lean GraphQL shape directly.
        setDocument(processedDocData as any);
        setPermissions(getPermissions(doc.myPermissions));
      });
    },
    [setDocumentType, setDocument, setPermissions]
  );

  // Corpus-context query.
  const {
    data: corpusData,
    loading: corpusLoading,
    error: corpusError,
    refetch: refetchWithCorpus,
  } = useQuery<
    GetDocumentKnowledgeAndAnnotationsOutput,
    GetDocumentKnowledgeAndAnnotationsInput
  >(GET_DOCUMENT_KNOWLEDGE_AND_ANNOTATIONS, {
    skip: !authReady || !documentId || !corpusId,
    variables: {
      documentId,
      corpusId: corpusId!,
      analysisId: undefined,
    },
    onCompleted: (data) => {
      if (!data?.document) {
        console.error("onCompleted: No document data received.");
        setViewState(ViewState.ERROR);
        toast.error("Failed to load document details.");
        return;
      }
      routingLogger.debug("[onCompleted] 🔄 Batching initial state updates");
      applyDocumentMetadata(data.document);
      // processAnnotationsData re-runs setPermissions; harmless and matches
      // the original ordering inside the same batched update window.
      unstable_batchedUpdates(() => processAnnotationsData(data));
      loadDocumentBody(data.document, /* useCachedFetch */ true);
    },
    onError: (error) => {
      // The first request after auth handoff may come back with
      // "Document matching query does not exist." — Apollo retries with the
      // correct headers and onCompleted takes over. Stay LOADING so the
      // spinner doesn't flash an error in the meantime.
      const benign404 =
        error?.graphQLErrors?.length === 1 &&
        error.graphQLErrors[0].message.includes(
          "Document matching query does not exist"
        );
      if (benign404) {
        console.warn("Initial 404 for document – will retry automatically");
        return;
      }
      console.error("GraphQL Query Error fetching document data:", error);
      toast.error(`Failed to load document details: ${error.message}`);
      setViewState(ViewState.ERROR);
    },
    fetchPolicy: "network-only",
    nextFetchPolicy: "no-cache",
  });

  // Document-only query (no corpus bound).
  const {
    data: documentOnlyData,
    loading: documentLoading,
    error: documentError,
    refetch: refetchDocumentOnly,
  } = useQuery<GetDocumentWithStructureOutput, GetDocumentWithStructureInput>(
    GET_DOCUMENT_WITH_STRUCTURE,
    {
      skip: !authReady || !documentId || Boolean(corpusId),
      variables: { documentId },
      onCompleted: (data) => {
        routingLogger.debug(
          "[GraphQL] ✅ DocumentKnowledgeBase: GET_DOCUMENT_WITH_STRUCTURE completed",
          { documentId, hasDocument: !!data?.document }
        );
        if (!data?.document) {
          console.error("onCompleted: No document data received.");
          setViewState(ViewState.ERROR);
          toast.error("Failed to load document details.");
          return;
        }
        routingLogger.debug(
          "[onCompleted] 🔄 Batching initial state updates (document-only)"
        );
        applyDocumentMetadata(data.document);
        loadDocumentBody(data.document, /* useCachedFetch */ false);

        // No-corpus path has no annotations to seed, but relationships are
        // few enough to load eagerly. Structural annotations are still lazy.
        const processedRelationships =
          data.document.allRelationships?.map((rel) => relationToGroup(rel)) ??
          [];
        unstable_batchedUpdates(() => {
          setPdfAnnotations(
            new PdfAnnotations([], processedRelationships, [], true)
          );
        });
      },
      onError: (error) => {
        console.error("GraphQL Query Error fetching document data:", error);
        toast.error(`Failed to load document details: ${error.message}`);
        setViewState(ViewState.ERROR);
      },
      fetchPolicy: "network-only",
      nextFetchPolicy: "no-cache",
    }
  );

  // Lightweight refetch handle for analysis/extract switching.
  const { refetch: refetchAnnotationsOnly } = useQuery<
    GetDocumentAnnotationsOnlyOutput,
    GetDocumentAnnotationsOnlyInput
  >(GET_DOCUMENT_ANNOTATIONS_ONLY, {
    skip: true, // manually triggered from the effects below
    fetchPolicy: "network-only",
  });

  const loading = corpusLoading || documentLoading;

  // Re-fetch annotations when the active analysis changes.
  // Deps intentionally omit `refetchAnnotationsOnly` and
  // `processAnnotationsOnlyData`. ``refetch`` from ``useQuery`` is in fact
  // identity-stable; the omission is for ``processAnnotationsOnlyData``,
  // whose ``setPdfAnnotations`` dependency rebuilds the callback each
  // render and would re-fire this effect on every parent render. Listing
  // ``refetch`` alongside it keeps the dep array honest about what we
  // intentionally omit instead of pretending only one is the problem.
  useEffect(() => {
    if (!loading && corpusId) {
      refetchAnnotationsOnly({
        documentId,
        corpusId,
        analysisId: selectedAnalysisId || null,
      }).then(({ data }) => {
        if (data) processAnnotationsOnlyData(data);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAnalysisId, corpusId, loading, documentId]);

  // Re-fetch annotations when the active extract changes.
  // Same dep-array rationale as the analysis-id effect above.
  useEffect(() => {
    if (!loading && corpusId) {
      refetchAnnotationsOnly({
        documentId,
        corpusId,
        analysisId: selectedExtractId || null,
      }).then(({ data }) => {
        if (data) processAnnotationsOnlyData(data);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedExtractId, corpusId, loading, documentId]);

  // Reset DOCX bytes on unmount to avoid stale WASM data when navigating away.
  useEffect(() => {
    return () => {
      bodyLoadCancelRef.current();
      setDocxBytes(null);
    };
  }, [setDocxBytes]);

  // Thread count for the discussions tab badge.
  const { data: threadCountData } = useQuery<
    GetConversationsOutputs,
    GetConversationsInputs
  >(GET_CONVERSATIONS, {
    variables: {
      documentId,
      conversationType: "THREAD",
      limit: 1,
    },
    skip: !documentId,
    fetchPolicy: "cache-and-network",
  });

  return {
    corpusData,
    documentOnlyData,
    combinedData: corpusId ? corpusData : documentOnlyData,
    loading,
    queryError: corpusError || documentError,
    refetch: corpusId ? refetchWithCorpus : refetchDocumentOnly,
    viewState,
    threadCount: threadCountData?.conversations?.totalCount ?? 0,
  };
}

export type {
  GetDocumentKnowledgeAndAnnotationsOutput,
  GetDocumentWithStructureOutput,
};
