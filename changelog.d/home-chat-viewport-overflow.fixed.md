- **Home-tab corpus chat overflowed the viewport, leaving the composer slightly offscreen.**
  Starting a chat from the corpus **Home** tab (clicking the inline chat bar,
  typing a query, and pressing Enter) expanded `CorpusQueryView` into its
  immersive chat layout, which sizes the chat container to
  `calc(100dvh - var(--oc-navbar-height, 4.5rem))` with the input pinned to the
  bottom (`frontend/src/views/CorpusQueryView.tsx:28,362-394`). However,
  `Corpuses.tsx` only stripped `CardLayout`'s default outer padding for the
  dedicated **Chats** tab (`frontend/src/views/Corpuses.tsx:1716`), so on the
  Home tab that full-height container was wrapped in `CardLayout`'s default
  padding (`~0.75rem` per side on desktop,
  `frontend/src/components/layout/CardLayout.tsx:122-135`). The extra `~1.5rem`
  of vertical padding pushed the total height past the viewport, leaving the
  pinned chat input partially clipped at the bottom and requiring a slight
  scroll. Reaching the same chat "from the chat list" (Chats tab) worked only
  because that tab's padding was already zeroed. Fix: zero `CardLayout`'s outer
  padding for the `home` tab as well as `chats`
  (`frontend/src/views/Corpuses.tsx:1716`), since both are viewport-bounded
  immersive layouts. This also removes a previously-invisible phantom overflow
  on the Home dashboard (its `position: fixed` chat bar and `overflow: hidden`
  content had hidden the same `~1.5rem` page scroll). The landing/details/article
  views center their own `max-width` content with internal padding, so they are
  unaffected by losing the thin outer frame.
