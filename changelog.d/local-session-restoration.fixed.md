- **Restored local username/password sessions across browser refreshes.** Local
  JWT sessions now persist for up to 24 hours, repopulate authenticated
  navigation and document/corpus controls while backend user details load, and
  are cleared on logout, expiry, or genuine authentication failures. Ordinary
  `403 Forbidden` permission responses no longer discard an otherwise valid
  session.
