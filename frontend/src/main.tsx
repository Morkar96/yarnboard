import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
// Order matters: theme.css overrides bootstrap's variables/component
// styles, so it must load after bootstrap's own stylesheet. Both are kept
// here (rather than split across main.tsx/App.tsx) so there's only one
// place governing global CSS load order.
import "bootstrap/dist/css/bootstrap.min.css";
import "./theme.css";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
