- **Corpus Chat (Home tab) — reset the conversation-expanded flag on ASK -> VIEW
  entry.** `CorpusQueryView` suppresses its outer "Conversation History" header
  while a single conversation is open by reading `chatExpandedInConversation`
  (`frontend/src/views/CorpusQueryView.tsx`). `backToAskFromView` already cleared
  that flag on the VIEW -> ASK exit, but the symmetric ASK -> VIEW entry
  (`openHistoryView`) did not, so a `true` left by an ASK-flow conversation could
  carry into VIEW and momentarily hide the outer header before `CorpusChat`
  mounts and re-reports list mode via `onViewModeChange`. `openHistoryView` now
  clears the flag on entry, mirroring `backToAskFromView`. Follow-up to the
  PR #1890 review (#1911); the existing VIEW header-suppression regression test
  (`frontend/src/views/__tests__/CorpusQueryView.handlers.test.tsx`) continues to
  pin the clean-entry contract.
- **Corpus Chat — scroll-mode comments.** Clarified the scroll-to-bottom effect
  in `frontend/src/components/corpuses/CorpusChat.tsx`: documented that a first
  mount with a pre-loaded transcript resolves to an instant `"auto"` jump (never
  smooth), and dropped a redundant comment over `scrollToBottom` whose default is
  self-evident from the `behavior: ScrollBehavior = "auto"` signature.
