import {
  Auth0Provider,
  Auth0ProviderOptions,
  useAuth0,
} from "@auth0/auth0-react";
import React, { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { safeReturnTo } from "./authRedirect";
import { ModernLoadingDisplay } from "../components/widgets/ModernLoadingDisplay";

interface Props extends Omit<Auth0ProviderOptions, "onRedirectCallback"> {
  children: React.ReactNode;
}

function Auth0InitializationBoundary({
  children,
}: {
  children: React.ReactNode;
}) {
  const { error, isLoading } = useAuth0();
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const hasCallbackParams = Boolean(
    params.get("state") && (params.get("code") || params.get("error"))
  );
  useEffect(() => {
    if (!isLoading && error && hasCallbackParams) {
      navigate(
        safeReturnTo(location.pathname + location.search + location.hash),
        { replace: true }
      );
    }
  }, [error, isLoading, hasCallbackParams, location, navigate]);
  // Child effects run before the provider's initialization effect. Keep the
  // entire app unmounted until the SDK has consumed code/state (or an OAuth
  // error); otherwise route and mobile-display effects can rewrite the URL
  // before the SDK recognizes the callback. AuthGate inside App runs too late
  // to protect routing effects outside that gate. Also wait for the router to
  // commit callback cleanup: its navigation can lag the SDK's state update,
  // leaving new children with a stale callback location and return path.
  if (isLoading || hasCallbackParams) {
    return (
      <ModernLoadingDisplay
        type="auth"
        message="Initializing OpenContracts"
        size="large"
      />
    );
  }
  return <>{children}</>;
}

export const Auth0ProviderWithHistory: React.FC<Props> = ({
  children,
  ...rest
}) => {
  const navigate = useNavigate();

  const onRedirectCallback = (appState?: { returnTo?: string }) => {
    navigate(safeReturnTo(appState?.returnTo ?? "/"), { replace: true });
  };

  return (
    <Auth0Provider
      {...(rest as Auth0ProviderOptions)}
      onRedirectCallback={onRedirectCallback}
      cacheLocation="memory"
    >
      <Auth0InitializationBoundary>{children}</Auth0InitializationBoundary>
    </Auth0Provider>
  );
};
