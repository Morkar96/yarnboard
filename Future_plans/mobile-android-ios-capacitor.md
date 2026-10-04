# Wrap Yarnboard as installable Android + iOS apps (Capacitor)

## Context

Yarnboard is currently a web-only app: a Vite-built React SPA served by
the same Flask process that hosts the `/api/*` routes (see
`backend/app/__init__.py`'s `serve_frontend` and `render.yaml`), with
session-cookie auth that relies on frontend and API being same-origin in
production. The user wants real, installable Android and iOS apps out of
this — not a rewrite, reusing what already exists.

The frontend is already a plain responsive React app (react-bootstrap's
grid, a viewport meta tag in `index.html`, no browser-only APIs in use)
with zero native functionality — everything goes through
`frontend/src/api/client.ts`'s JSON/FormData `fetch` calls. That shape is
exactly what Capacitor (Ionic's native-wrapper toolkit) is built for: it
packages an existing web build into a real iOS/Android app shell with a
WebView, giving native distribution (App Store/Play Store, home-screen
icon, offline shell) and optional access to native device APIs later,
without rewriting the UI in React Native or Flutter. That's the
recommended path over a full native rewrite, which would mean
maintaining a second frontend indefinitely for no feature Yarnboard
currently needs (no camera/push/offline requirement today).

Two decisions were confirmed with the user before finalizing this plan:
- **iOS build machine**: a Mac with Xcode is available, so iOS
  App Store distribution is fully in scope, not just Android.
- **Auth strategy**: keep the existing session-cookie auth as-is and
  solve the native same-origin problem via Capacitor's `server.hostname`
  config (make the app's WebView believe it's being served from the
  production API's own domain), rather than rewriting auth to bearer
  tokens. Simpler and no backend auth code changes; the tradeoff (some
  edge cases with iOS's cross-site cookie tracking prevention if this
  ever stops being "same-site enough") is accepted for now and called
  out below so it can be revisited if login flakiness shows up on iOS
  specifically.

## What's needed, grouped

### 1. Accounts & tooling (one-time, outside the codebase)
- **Apple Developer Program** ($99/yr) — required for iOS builds beyond
  a personal device and for any App Store submission.
- **Xcode** (free, Mac only) — already covered, Mac is available.
- **Google Play Developer account** ($25 one-time) for Play Store
  submission.
- **Android Studio** (free) — for the Android SDK/emulator; Capacitor
  can build via CLI once the SDK is installed, Android Studio itself is
  optional but the SDK/emulator tooling it installs is not.
- **App icons + splash screens** at the required size sets for both
  platforms — `@capacitor/assets` generates all sizes from one source
  image/logo, so only one square Yarnboard mark needs to be designed.
- **A privacy policy URL** — both stores require one for any app that
  collects accounts/personal data (Yarnboard collects email/username/
  password and user-submitted content), hosted anywhere public.
- **A reviewer demo account** — both app review teams need working
  login credentials to test the app; the `demo@yarnboard.test` /
  `demopass123` account already seeded locally is the right shape for
  this, just needs to exist on whatever backend gets submitted for
  review (i.e., seed the same on the production database before
  submitting).

### 2. Frontend integration (`frontend/`)
- Add Capacitor: `npm install @capacitor/core @capacitor/cli`, then
  `npx cap init` (app name "Yarnboard", a bundle ID like
  `com.yarnboard.app`).
- Add the native platforms: `npm install @capacitor/ios @capacitor/android`
  then `npx cap add ios` / `npx cap add android` — this generates the
  `ios/` and `android/` native project folders that get committed
  alongside the existing frontend code.
- `capacitor.config.ts` — the key new file, configuring:
  ```ts
  const config: CapacitorConfig = {
    appId: "com.yarnboard.app",
    appName: "Yarnboard",
    webDir: "dist",
    server: {
      hostname: "yarnboard.onrender.com", // matches render.yaml's real prod host
      androidScheme: "https",
      iosScheme: "https",
    },
  };
  ```
  This is what makes the agreed-on auth approach work: the app's WebView
  requests look like they're coming from the production domain itself,
  so the existing session cookie flow needs no backend changes.
- **`VITE_API_BASE_URL` for native builds**: production today relies on
  it being *unset* (relative `/api/...` paths resolve against whatever
  origin is serving the page — see the comment in `client.ts` and
  `render.yaml`). With `server.hostname` set as above, that same relative
  path resolution keeps working inside the native app too, since the
  WebView believes its origin *is* `yarnboard.onrender.com` — so no new
  build-time env split between "web build" and "native build" should be
  needed. Confirmed during Verification below (this is the one part of
  the plan worth double-checking empirically rather than assuming).
- Every `npm run build` needs a `npx cap sync` afterward (copies the
  fresh `dist/` into the native `ios/`/`android/` projects) — worth a
  new `make` target (e.g. `sync-mobile`) once this is wired up, mirroring
  the existing `Makefile` conventions (`build`, `dev`, `down`, etc.).

### 3. Backend changes (`backend/app/config.py`)
- `CORS_ORIGINS` needs the native app's origins added alongside the
  existing web frontend origin, since Capacitor's dev/live-reload mode
  and any non-`server.hostname` fallback still originate requests from
  `capacitor://localhost` (iOS) / `http://localhost` (Android) — add
  both to the production `CORS_ORIGINS` env var on Render as a safety
  net even though the `server.hostname` trick should make same-origin
  the common case.
- No auth/session code changes needed given the decision above — this
  is intentionally the smallest-diff option.

### 4. Optional native features (cheap add-ons once Capacitor exists, not required for v1)
- `@capacitor/camera` — take a pattern photo directly instead of picking
  an existing one, on the existing upload flow in `EditPatternPage.tsx`.
- `@capacitor/filesystem` / a document-picker plugin — smoother PDF
  selection than a bare `<input type=file>` on mobile.
- `@capacitor/push-notifications` — a native alternative/complement to
  the existing "pattern updated" Resend emails (`backend/app/email.py`).
None of these are needed to ship v1; flagging them as easy follow-ups
once the native shell exists, not part of this plan's scope.

### 5. App store submission requirements (after the app builds and runs)
- App icons/screenshots at each store's required sizes (generated per
  above).
- Apple: App Store Connect listing, age rating questionnaire, the "App
  Privacy" nutrition-label questionnaire (accurately describing that
  Yarnboard collects email + account data), TestFlight for beta testing
  before public release.
- Google: Play Console listing, the Data Safety form (same substance as
  Apple's privacy label), an Internal Testing track before Production
  rollout.
- Both stores' review teams need the demo account from step 1.

## Critical files
- `frontend/capacitor.config.ts` — new, the central native-wrapper config.
- `frontend/ios/`, `frontend/android/` — new, generated native project
  folders (committed to the repo, edited occasionally for icons/
  permissions but not hand-written).
- `frontend/package.json` — new Capacitor dependencies + scripts.
- `backend/app/config.py` — `CORS_ORIGINS` additions.
- `Makefile` — optional new `sync-mobile` (or similar) target.
- `README.md` — new "Mobile builds" section documenting the `cap add`/
  `cap sync`/Xcode/Android Studio steps, mirroring how the existing
  README documents local web dev setup.

## Ordered implementation steps
1. `npm install @capacitor/core @capacitor/cli` in `frontend/`, `npx cap init`.
2. Write `capacitor.config.ts` with the `server.hostname` config above.
3. `npm install @capacitor/ios @capacitor/android`; `npx cap add ios`; `npx cap add android`.
4. `npm run build && npx cap sync` — confirm both native projects pick up the current `dist/`.
5. Add the native origins to `CORS_ORIGINS` in the Render dashboard (or `.env` for local testing against a tunneled backend).
6. Open `ios/App/App.xcworkspace` in Xcode, run on the Simulator; open `android/` in Android Studio, run on the Emulator.
7. Manual login smoke test on both (see Verification) — this is where the "no `VITE_API_BASE_URL` split needed" assumption from step 2 above gets confirmed or corrected.
8. Add app icons/splash via `@capacitor/assets` from one source image.
9. Document the new workflow in `README.md`.

## Verification
- **Automated**: none of the existing backend/frontend test suites are affected by this change (no application code changes, only new config/build tooling) — `make test` should still pass unchanged, worth a quick run to confirm nothing in the native tooling install disturbed `node_modules` in a way that breaks `npm run test`/`tsc`.
- **Manual, the real test of this plan**: on the iOS Simulator and Android Emulator, load the app, register or log in with the seeded `demo@yarnboard.test` account, confirm the session persists across an app relaunch (not just within one open session — this is the specific thing the cookie/same-origin approach needs to prove out), then exercise one write action (e.g. save a pattern) to confirm authenticated POST requests work end-to-end through the native WebView, not just the initial page load.
- If session persistence or cross-request cookie behavior turns out to be flaky specifically on iOS during that manual test, that's the signal to revisit the token-based auth alternative that was deliberately deferred in this plan rather than pre-built.
