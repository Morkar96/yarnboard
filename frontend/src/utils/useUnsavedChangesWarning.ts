/**
 * Shows the browser's native "leave site?" confirmation if the tab is
 * closed/refreshed/navigated away from (externally, e.g. typing a new
 * URL) while `hasUnsavedChanges` is true -- used on ReviewPatternPage and
 * EditPatternPage so an in-progress edit/submit isn't silently lost.
 *
 * Deliberately doesn't intercept in-app React Router navigation (clicking
 * another nav link): that needs a router-level navigation blocker, which
 * requires the data-router APIs this app doesn't use -- beforeunload
 * alone covers the common accidental-loss case (tab close, refresh,
 * typing a new address) without that added complexity.
 *
 * Modern browsers ignore any custom message and show their own generic
 * text -- setting returnValue is still required to trigger the prompt at
 * all, it just won't be what's displayed.
 */
import { useEffect } from "react";

export function useUnsavedChangesWarning(hasUnsavedChanges: boolean): void {
  useEffect(() => {
    if (!hasUnsavedChanges) return;

    function handleBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [hasUnsavedChanges]);
}
