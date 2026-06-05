- **Mobile annotation deep-link loader: closed a one-frame not-found flash for structural deep-links and made the loader screen-reader-announced (PR #1903 follow-up, #1918).**
  Two refinements to the mobile `?ann=<id>` loader added in #1903:
  - **One-frame flash for structural deep-links.** `useStructuralAnnotations`
    (`frontend/src/components/knowledge_base/document/document_kb/useStructuralAnnotations.ts`)
    dispatches the targeted lazy fetch from an effect that runs *after* the
    render that needs it, so for one frame its result is
    `{ called: false, loading: false }` — long enough for
    `MobileAnnotationDetail` to flash "This annotation is no longer available."
    before the spinner appeared. The returned `loading` now also reports the
    pre-dispatch window (mirroring the effect's own guard, gated on
    `!called` so it self-heals once the fetch fires and never sticks — the
    targeted path deliberately leaves `structuralAnnotationsLoaded` false).
    The loader is now continuous from the first render until the fetch settles.
  - **Accessibility.** The mobile loader (`LoadingState` in
    `frontend/src/components/knowledge_base/document/layouts/mobile/MobileAnnotationDetail.tsx`)
    is now a `role="status"` live region, so assistive technology announces
    "Loading annotation…" when a deep-link opens the sheet. The spinner icon
    stays `aria-hidden`.
  - **Defensive API.** `MobileAnnotationDetail`'s `loading` prop is now optional
    (defaults to `false`), so a future callsite that forgets to thread it
    degrades safely to the not-found state instead of breaking the build.
