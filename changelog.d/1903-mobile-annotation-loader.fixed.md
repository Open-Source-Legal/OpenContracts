- **Mobile annotation deep-link showed "no longer available" instead of a loader during the initial uncached load.**
  Navigating directly to an annotation on mobile (e.g. `cite.opensource.legal/d/...?ann=<id>`)
  before anything is cached takes a few seconds while the document and its
  annotations are fetched. During that window the mobile "Annotation" sheet
  (`frontend/src/components/knowledge_base/document/layouts/mobile/MobileAnnotationDetail.tsx`)
  resolved the selected id against an empty annotation set and rendered
  "This annotation is no longer available." — wrongly implying the annotation
  was gone. The component had no access to a loading signal, so it could not
  distinguish "still fetching" from "not found". Fix: thread the document
  loader's `loading` flag from `MobileDocumentLayout.tsx` into
  `MobileAnnotationDetail`, and surface a combined `loading` boolean from
  `useStructuralAnnotations` (all-structural + targeted lazy fetch) so that
  structural-annotation deep-links — which resolve via a targeted fetch that
  runs *after* the corpus/document queries settle — also show the loader rather
  than flashing the not-found message. The not-found state now only appears once
  both the document load and any targeted structural fetch settle and the
  annotation is still unresolved.
