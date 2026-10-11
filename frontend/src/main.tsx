import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import i18n, { getStoredLanguage, isRtl } from "./i18n";
// Order matters: theme.css overrides bootstrap's variables/component
// styles, so it must load after bootstrap's own stylesheet. The LTR
// build is a plain static import (like theme.css/styles.css below) so
// Vite emits a real <link> for it straight into the built page's
// <head>, fetched in parallel with the JS bundle from the start --
// unlike the old fully-JS-managed version, where the browser couldn't
// even start that request until this module had already loaded and run,
// which is what Lighthouse flagged as the cause of a large layout shift
// (the page painted once, unstyled, then again once Bootstrap's CSS
// finally arrived). The RTL build stays behind Vite's `?url` suffix and
// is only ever added via JS (see applyDirection) for a returning
// Hebrew-preferring visitor -- not worth paying the same eager-load cost
// for the uncommon case.
import "bootstrap/dist/css/bootstrap.min.css";
import bootstrapRtlHref from "bootstrap/dist/css/bootstrap.rtl.min.css?url";
import "./theme.css";
import "./styles.css";

const BOOTSTRAP_RTL_LINK_ID = "bootstrap-rtl-css";

/**
 * Applies everything a language change needs outside React's own render
 * cycle: <html dir/lang> (drives every CSS logical-property/flex-
 * direction flip across styles.css, plus screen-reader language) and
 * Bootstrap's RTL override (a separately-built stylesheet, not
 * something a CSS class or attribute alone can flip -- see
 * bootstrapRtlHref above). The LTR build imported above is always
 * present and is never touched here; this only ever creates or removes
 * the RTL override, appended at the end of <head> so it wins the
 * cascade over the LTR build for shared selectors while active, and
 * removing it on an LTR switch leaves the LTR build as the only
 * Bootstrap stylesheet in effect again. Called once synchronously
 * before the first render (so there's no flash of the wrong direction)
 * and again on every subsequent language change (see i18n's
 * "languageChanged" event).
 */
function applyDirection(language: string) {
  document.documentElement.dir = isRtl(language) ? "rtl" : "ltr";
  document.documentElement.lang = language;

  const rtlLink = document.getElementById(BOOTSTRAP_RTL_LINK_ID) as HTMLLinkElement | null;

  if (isRtl(language)) {
    if (!rtlLink) {
      const link = document.createElement("link");
      link.id = BOOTSTRAP_RTL_LINK_ID;
      link.rel = "stylesheet";
      link.href = bootstrapRtlHref;
      document.head.appendChild(link);
    }
  } else {
    rtlLink?.remove();
  }
}

applyDirection(getStoredLanguage());
i18n.on("languageChanged", applyDirection);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
