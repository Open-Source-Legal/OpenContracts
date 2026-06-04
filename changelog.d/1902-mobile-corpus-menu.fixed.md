- **Mobile: corpus tab menu was unreachable when a `Readme.CAML` article is present.**
  When a corpus has a `Readme.CAML`, `CorpusArticleView` replaces the corpus
  home. On mobile, the navigation sidebar (corpus tab menu) is only reachable
  via a menu button wired to `onOpenMobileMenu`, but `CorpusHome.tsx` never
  passed that callback to `CorpusArticleView` and the article toolbar rendered
  no menu button at all — so power-user mode on a phone left users with no way
  to navigate within the corpus. Fix: `CorpusHome.tsx` now forwards
  `onOpenMobileMenu` to both `CorpusArticleView` render sites
  (`frontend/src/components/corpuses/CorpusHome.tsx`), and the article toolbar
  renders a compact, mobile-only circular menu button styled in the os-legal
  design language to match the article toolbar
  (`frontend/src/components/corpuses/CorpusHome/CorpusArticleView.tsx`). The
  button is gated on `isPowerUserMode` to match `CorpusLandingView` /
  `CorpusDetailsView`, since the sidebar only exists in power-user mode
  (`frontend/src/views/Corpuses.tsx`). Added component tests
  (`frontend/tests/CorpusArticleView.ct.tsx`) covering both the power-user
  (button visible, click fires `onOpenMobileMenu`) and explore-mode (button
  absent) cases.
