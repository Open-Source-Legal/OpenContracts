- Fix Auth0 login silently returning to the signed-out home page by delaying
  application mounting in `frontend/src/utils/Auth0ProviderWithHistory.tsx`
  until the SDK consumes OAuth callback parameters and the router commits the
  return path. This prevents routing effects from discarding both successful
  and failed callbacks; regression tests exercise the real SDK and router.
