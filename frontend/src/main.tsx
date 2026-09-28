import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import i18n, { getStoredLanguage, isRtl } from "./i18n";
// Order matters: theme.css overrides bootstrap's variables/component
// styles, so it must load after bootstrap's own stylesheet. Both are kept
// here (rather than split across main.tsx/App.tsx) so there's only one
// place governing global CSS load order. Bootstrap itself is NOT a plain
// static import (unlike theme.css/styles.css below) -- it needs to switch
// between the LTR and RTL builds at runtime depending on language (see
// applyDirection), which a static import can't do, so its URL is
// resolved via Vite's `?url` suffix and applied through a managed <link>
// element instead.
import bootstrapLtrHref from "bootstrap/dist/css/bootstrap.min.css?url";
import bootstrapRtlHref from "bootstrap/dist/css/bootstrap.rtl.min.css?url";
import "./theme.css";
import "./styles.css";

const BOOTSTRAP_LINK_ID = "bootstrap-css";

/**
 * Applies everything a language change needs outside React's own render
 * cycle: <html dir/lang> (drives every CSS logical-property/flex-
 * direction flip across styles.css, plus screen-reader language) and
 * which Bootstrap build is loaded (its RTL build is a separately-built
 * stylesheet, not something a CSS class or attribute alone can flip --
 * see bootstrapRtlHref above). Called once synchronously before the
 * first render (so there's no flash of the wrong direction) and again on
 * every subsequent language change (see i18n's "languageChanged" event).
 */
function applyDirection(language: string) {
  document.documentElement.dir = isRtl(language) ? "rtl" : "ltr";
  document.documentElement.lang = language;

  let link = document.getElementById(BOOTSTRAP_LINK_ID) as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement("link");
    link.id = BOOTSTRAP_LINK_ID;
    link.rel = "stylesheet";
    // Inserted first, so the static imports below (already injected into
    // <head> by the time this module-scope code runs, since imports are
    // evaluated before the rest of this file) stay after it -- preserving
    // the "theme.css overrides bootstrap" order the comment above relies
    // on regardless of which Bootstrap build is currently loaded.
    document.head.prepend(link);
  }
  link.href = isRtl(language) ? bootstrapRtlHref : bootstrapLtrHref;
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
