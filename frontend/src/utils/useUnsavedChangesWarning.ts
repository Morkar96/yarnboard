/**
 * Warns before losing unsaved work in two situations, while
 * `hasUnsavedChanges` is true -- used on ReviewPatternPage and
 * EditPatternPage so an in-progress edit/submit isn't silently lost:
 *
 *  1. Leaving the tab/site entirely (close, refresh, typing a new
 *     address) -- the browser's native "leave site?" prompt, via
 *     beforeunload. Modern browsers ignore any custom message and show
 *     their own generic text; returnValue still has to be set to
 *     trigger the prompt at all, it just won't be what's displayed.
 *
 *  2. Clicking to another page *within* the app (a nav link, a Link
 *     elsewhere on the page) -- intercepted at the document level in
 *     the capture phase, before React Router's own <Link> click handler
 *     runs, so it can ask window.confirm() and only navigate if
 *     confirmed. This app uses plain <BrowserRouter> rather than a data
 *     router, so React Router's built-in useBlocker isn't available;
 *     this is the equivalent for a non-data router setup.
 *
 * Deliberately doesn't cover the browser back/forward buttons
 * (popstate) -- by the time that event fires the URL has already
 * changed, and reliably un-doing it without janky double-back-press
 * artifacts is a meaningfully bigger problem than what's asked for here.
 */
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

export function useUnsavedChangesWarning(hasUnsavedChanges: boolean): void {
  const navigate = useNavigate();
  const { t } = useTranslation();

  useEffect(() => {
    if (!hasUnsavedChanges) return;

    function handleBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }

    function handleClick(e: MouseEvent) {
      // Let the browser handle its own new-tab/download/modified-click
      // behavior untouched -- only intercept a plain left-click that
      // would otherwise navigate in this same tab.
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }

      const link = (e.target as HTMLElement).closest("a");
      if (!link || !link.href || link.target === "_blank") return;

      const destination = new URL(link.href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      const samePage =
        destination.pathname === window.location.pathname && destination.search === window.location.search;
      if (samePage) return;

      e.preventDefault();
      e.stopPropagation();
      if (window.confirm(t("unsavedChanges.confirmLeave"))) {
        navigate(destination.pathname + destination.search + destination.hash);
      }
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    document.addEventListener("click", handleClick, true);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("click", handleClick, true);
    };
  }, [hasUnsavedChanges, navigate, t]);
}
