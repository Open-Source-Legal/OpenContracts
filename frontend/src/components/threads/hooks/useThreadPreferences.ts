import { useState, useCallback } from "react";
import { ThreadSortOption } from "../../../atoms/threadAtoms";

const THREAD_PREFS_KEY = "opencontracts_thread_preferences";

export interface ThreadPreferences {
  defaultSort: ThreadSortOption;
  compactView: boolean;
  showAvatars: boolean;
}

const DEFAULT_PREFERENCES: ThreadPreferences = {
  defaultSort: "pinned",
  compactView: false,
  showAvatars: true,
};

/**
 * Hook for managing user thread preferences in localStorage
 */
export function useThreadPreferences() {
  const [prefs, setPrefs] = useState<ThreadPreferences>(() => {
    try {
      const stored = localStorage.getItem(THREAD_PREFS_KEY);
      if (stored) {
        return { ...DEFAULT_PREFERENCES, ...JSON.parse(stored) };
      }
    } catch (error) {
      console.error("Failed to load thread preferences:", error);
    }
    return DEFAULT_PREFERENCES;
  });

  const updatePrefs = useCallback(
    (updates: Partial<ThreadPreferences>) => {
      const newPrefs = { ...prefs, ...updates };
      setPrefs(newPrefs);
      try {
        localStorage.setItem(THREAD_PREFS_KEY, JSON.stringify(newPrefs));
      } catch (error) {
        console.error("Failed to save thread preferences:", error);
      }
    },
    [prefs]
  );

  const resetPrefs = useCallback(() => {
    setPrefs(DEFAULT_PREFERENCES);
    try {
      localStorage.removeItem(THREAD_PREFS_KEY);
    } catch (error) {
      console.error("Failed to reset thread preferences:", error);
    }
  }, []);

  return { prefs, updatePrefs, resetPrefs };
}
