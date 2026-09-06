const LOCAL_AUTH_SESSION_KEY = "oc_local_auth_session";
export const LOCAL_AUTH_SESSION_TTL_MS = 24 * 60 * 60 * 1000;

type StoredLocalAuthSession = {
  token: string;
  expiresAt: number;
  user?: unknown;
};

const getStorage = (): Storage | null => {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
};

export const saveLocalAuthSession = (token: string, user?: unknown): void => {
  const storage = getStorage();
  if (!storage || !token) return;

  const session: StoredLocalAuthSession = {
    token,
    expiresAt: Date.now() + LOCAL_AUTH_SESSION_TTL_MS,
    user,
  };
  try {
    storage.setItem(LOCAL_AUTH_SESSION_KEY, JSON.stringify(session));
  } catch {
    // Authentication still works for the current page when storage is blocked.
  }
};

export const loadLocalAuthSessionUser = (): unknown | null => {
  const storage = getStorage();
  if (!storage) return null;

  try {
    const raw = storage.getItem(LOCAL_AUTH_SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Partial<StoredLocalAuthSession>;
    if (
      typeof session.token !== "string" ||
      typeof session.expiresAt !== "number" ||
      session.expiresAt <= Date.now() ||
      !session.user ||
      typeof session.user !== "object"
    ) {
      return null;
    }
    return session.user;
  } catch {
    return null;
  }
};

export const loadLocalAuthSession = (): string | null => {
  const storage = getStorage();
  if (!storage) return null;

  try {
    const raw = storage.getItem(LOCAL_AUTH_SESSION_KEY);
    if (!raw) return null;

    const session = JSON.parse(raw) as Partial<StoredLocalAuthSession>;
    if (
      typeof session.token !== "string" ||
      !session.token ||
      typeof session.expiresAt !== "number" ||
      session.expiresAt <= Date.now()
    ) {
      storage.removeItem(LOCAL_AUTH_SESSION_KEY);
      return null;
    }

    return session.token;
  } catch {
    storage.removeItem(LOCAL_AUTH_SESSION_KEY);
    return null;
  }
};

export const clearLocalAuthSession = (): void => {
  try {
    getStorage()?.removeItem(LOCAL_AUTH_SESSION_KEY);
  } catch {
    // Storage may be disabled by browser policy.
  }
};
