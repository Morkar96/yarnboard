# Yarnboard

A dashboard for all the knitting and crochet instructions scattered across
different websites. Paste a link to a pattern page, and Yarnboard pulls out
the materials, abbreviations, and step-by-step instructions into a
checklist you can follow while you craft -- then saves it to a shared
community library (deduplicated by source URL) so nobody has to scrape the
same pattern twice.

Every pattern always shows **who uploaded it to Yarnboard** and **who
originally designed it** (with a link back to the source page), and
uploading always publishes to the whole community -- users are told this
clearly before they publish.

## Architecture

```
[Browser] --fetch(credentials:include)--> [Flask, single Render service]
                                                |         |
                                                |         v
                                                |    [built React/Vite files,
                                                |     served directly by Flask --
                                                |     see FRONTEND_DIST in app/__init__.py]
                                                v
                                          [Neon Postgres, via psycopg2]
```

Frontend and backend deploy as **one combined Render service**: the build
step installs the backend's Python deps and builds the React app, and
Flask itself serves the built frontend files alongside its `/api/*`
routes (see `serve_frontend` in `backend/app/__init__.py`). Locally they
still run as two separate dev processes (Vite on 5173, Flask on 5001) for
hot-reload -- see Local setup below.

- **Backend** (`backend/`): Flask, split into a small app-factory package
  (`app/`) with two blueprints -- `auth` (accounts, session cookies) and
  `patterns` (scrape-preview, publish, the three pattern list views,
  per-user checklist progress). See `backend/app/*.py` module docstrings
  for what each file is responsible for.
- **Scraper** (`backend/app/scraper.py`): best-effort heuristic extraction
  (a headless browser via Playwright, parsed with BeautifulSoup) based on
  heading keywords (English and Hebrew) and list markup. There's no
  universal format for pattern pages across the web, so the scraper's
  output is always shown to the user as an **editable draft** before
  anything is saved -- never assume it's 100% correct. Outbound fetches
  are restricted to public `http(s)` hosts (no `file://`, no
  loopback/private/link-local addresses, checked both up front and
  per-request) so a submitted URL can't be used to read local files off
  the server or reach internal services (SSRF).
- **Translation & RTL**: a pattern can be machine-translated in either
  direction -- an English-primary pattern gets a Hebrew overlay, or a
  Hebrew-primary one gets an English overlay -- via the Gemini API
  (`backend/app/translation.py`, requires `GEMINI_API_KEY`). A
  translation is reviewable/correctable on the pattern's Edit page and
  marked reviewed once a person touches it. Content fields throughout the
  app use `dir="auto"` so right-to-left text displays correctly
  regardless of which language the UI chrome itself is in.
- **Per-user checklist progress**: a pattern's instructions are shared by
  everyone (one row in the `pattern` table), but checking off a step is
  personal -- tracked in a separate `user_pattern_progress` table so one
  person's progress never shows up as completed for anyone else viewing
  the same community pattern.
- **Editing & permissions**: a pattern's uploader, or a user with
  `is_admin` set (granted via `flask make-admin <email>`, see Local setup),
  can edit its title/author/materials/abbreviations/instructions after
  publishing. Editing `instructions` bumps `Pattern.instructions_version`,
  which invalidates other users' checklist progress on it -- lazily, per
  user, not as a bulk reset (see `UserPatternProgress.pattern_version`'s
  docstring in `backend/app/models.py` for the full mechanism). Affected
  users see an in-app banner (polled, `frontend/src/components/
  UpdateBanner.tsx`) and get an email (`backend/app/email.py`, via Resend)
  the next time a pattern they've engaged with changes.
- **Frontend** (`frontend/`): Vite + React + TypeScript, React Router,
  a typed API client (`src/api/client.ts`), and a single `AuthContext` for
  the logged-in user. No larger state library -- the app is small enough
  that page-local `useState` plus one context is sufficient.
- **Auth**: server-side session cookies (Flask's signed session) plus
  bcrypt password hashing. Since frontend and backend are one combined
  service in production, they're always same-origin -- an ordinary `Lax`
  session cookie (just `Secure`, since prod is HTTPS) is enough, no
  cross-site cookie workaround needed (see `backend/app/config.py`). CORS
  is still enabled for local dev, where Vite and Flask really are
  separate origins.
- **Security**: login, register, and resend-verification are rate
  limited per IP (Flask-Limiter); the app refuses to start in production
  if `SECRET_KEY` is left at its insecure default; passwords must be at
  least 8 characters; and user-controlled text (username, pattern title)
  is HTML-escaped before being interpolated into outbound emails. See
  `.github/workflows/security.yml` for the CI job that regression-tests
  all of this plus dependency vulnerability scanning (`pip-audit`,
  `npm audit`).

## Local setup

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # leave DATABASE_URL unset to use local SQLite,
                             # and the RESEND_* keys unset to log emails
                             # instead of sending them
flask --app wsgi init-db    # creates the tables
flask --app wsgi make-admin you@example.com  # optional: grant edit-any-pattern rights
flask --app wsgi run --port 5001
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local  # points at the local backend by default
npm run dev                 # http://localhost:5173
```

Register an account, then use "Submit a Pattern" to try it against a real
pattern page. The scraper is heuristic -- if a page doesn't extract
cleanly, the review screen lets you fill in materials/abbreviations/steps
by hand before publishing.

## Running the e2e tests

```bash
make e2e
```

One command runs the whole thing: wipes and reseeds a throwaway
`backend/instance/e2e.db` (see `flask --app wsgi seed-e2e` in
`backend/app/__init__.py` for exactly what it creates -- four fixture
users and eight patterns covering permissions, sharing, and translation
scenarios), starts real backend/frontend dev servers on the normal
5001/5173 ports, runs the Playwright suite (`frontend/e2e/`) against
them, then tears everything down. It never touches your real local
`backend/instance/yarnboard.db`, but it does use the same ports as
`make dev` -- don't run both at once. Real Resend/Gemini calls are
disabled for the run (see the Makefile), so email sends and translations
are asserted against the app's own log-fallback/seeded-data behavior,
not live third-party delivery -- that stays part of manual pre-merge QA.

This repo also has Playwright's AI test agents set up
(`npx playwright init-agents --loop=claude`, see `.claude/agents/
playwright-test-*.md` and `frontend/.mcp.json`) for drafting/maintaining
specs against a live running app from inside Claude Code -- the planner
explores the app and writes a plan, the generator turns it into real
spec files verified against the live DOM, and the healer can patch a
spec whose selector broke after a UI change. All three need the
`playwright-test` MCP server connected (Claude Code will prompt to
enable it once `frontend/.mcp.json` is picked up); every generated or
healed change should still be reviewed like any other diff before it's
trusted.

## Deploying to Render

Yarnboard deploys as a **single** Render web service (not separate
frontend/backend services) -- Flask serves the built React app itself.

1. Create a Postgres database at [neon.tech](https://neon.tech) and copy
   its connection string.
2. In the Render dashboard, create a new **Blueprint** from this repo --
   Render will read `render.yaml` and create one service (`yarnboard`)
   with the build/start commands already filled in:
   - Build: `cd backend && pip install -r requirements.txt && cd ../frontend && npm install && npm run build`
   - Start: `cd backend && gunicorn wsgi:app`

   (If you're configuring a Web Service manually instead of via Blueprint,
   enter those same two commands yourself -- there's no `rootDir` to set,
   since the build spans both `backend/` and `frontend/`.)
3. Set the env vars marked `sync: false` in `render.yaml`: `SECRET_KEY`
   (any long random string), `DATABASE_URL` (the Neon connection string
   from step 1), and `RESEND_ONBOARDING`/`RESEND_NOTIFICATIONS`/
   `RESEND_NEWSLETTER`/`RESEND_FROM_EMAIL` (from
   [resend.com](https://resend.com) -- one API key per email category,
   see `app/email.py`; a category's emails are just logged instead of
   sent if its key is left unset, and `RESEND_NEWSLETTER` isn't used by
   any sender yet). Update
   `PUBLIC_APP_URL` to match this service's actual Render URL (used to
   build links in emails). Don't set `VITE_API_BASE_URL` -- leaving it
   unset is what makes the built frontend call the API with relative,
   same-origin paths.
4. Run the schema against the Neon database once:
   `DATABASE_URL=<neon-connection-string> flask --app wsgi init-db`
   (run this locally, pointed at the production database, since there's no
   migration tool in v1 -- see Known limitations). If the database already
   existed before the pattern-editing feature (i.e. you're upgrading, not
   starting fresh), also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-versioning-columns`,
   since `init-db` only creates missing tables, never adds columns to
   ones that already exist. Same deal if the database predates the
   pattern-photo feature: also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-photo-columns`.
   Same deal again if it predates the Stitch Fiddle chart-import feature:
   also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-chart-grid-columns`.
   Same deal again if it predates email verification: also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-email-verification-columns`
   (this one backfills existing accounts as already-verified so nobody gets
   locked out retroactively -- see the command's docstring in
   `app/__init__.py`). Same deal again if it predates Hebrew translation:
   also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-hebrew-translation-columns`,
   and if it predates the reverse (Hebrew-primary -> English) translation
   direction, also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-english-translation-columns`.
   Same deal again if it predates private patterns/sharing: also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-pattern-visibility-columns`
   (this one also swaps a unique constraint, not just adding a column --
   see the command's docstring), and if it predates edit-level sharing and
   per-user notification settings, also run
   `DATABASE_URL=<neon-connection-string> flask --app wsgi add-sharing-and-notification-columns`.
5. Grant yourself edit-any-pattern rights once:
   `DATABASE_URL=<neon-connection-string> flask --app wsgi make-admin you@example.com`.

## Deploying the frontend to Cloudflare

An alternative to the combined Render deployment above: host the built
frontend as static assets on Cloudflare Workers (e.g. on your own
domain), while the API keeps running on Render as normal -- this makes
them **different origins**, which needs a bit more wiring than the
same-origin combined setup.

1. Deploy the backend to Render as above (or point at an existing
   deployment) -- note its URL, e.g. `https://yarnboard.onrender.com`.
2. On the Render service, set `CORS_ORIGINS` (see `render.yaml`) to the
   Cloudflare domain(s) the frontend will actually be served from
   (comma-separated if more than one, e.g. your custom domain plus the
   `*.workers.dev` preview URL). `SESSION_COOKIE_SAMESITE=None` is
   already handled for you in production (see `backend/app/config.py`),
   which is what lets the session cookie survive this cross-origin setup
   at all.
3. In the Cloudflare dashboard, create a Workers project connected to
   this repo. This repo's root `wrangler.jsonc` already points
   `assets.directory` at `frontend/dist` (Wrangler defaults to the raw,
   unbuilt `frontend` folder without it, which serves a blank page --
   `index.html` references `/src/main.tsx`, a `.tsx` file browsers can't
   execute). What's *not* in a repo file, and needs setting in the
   Cloudflare project's build settings:
   - **Build command**: `cd frontend && npm install && npm run build` --
     without this, `frontend/dist` doesn't exist at deploy time either
     (same blank-page symptom).
   - **Deploy command**: `npx wrangler deploy` (Cloudflare's default).
   - **Build variable** `VITE_API_BASE_URL`: the Render backend's URL from
     step 1. Vite bakes this in at build time (see
     `frontend/src/api/client.ts`) -- without it, the built frontend falls
     back to relative `/api/...` paths, which resolve against the
     Cloudflare domain itself (no API there) instead of Render.
4. Add your custom domain to the Workers project (Cloudflare dashboard --
   Workers project -- Custom Domains) if you're not just using the
   `*.workers.dev` URL.

## Known limitations

- The scraper is heuristic and best-effort; it's designed to feed a human
  review step, not to be a guaranteed-correct parser for every pattern site.
- Editing a pattern invalidates progress pattern-wide, not per-part -- a
  typo fix in one step resets everyone's checklist on the whole pattern,
  not just that step. A deliberate trade-off for a simple, lazy
  invalidation mechanism (see `UserPatternProgress.pattern_version`)
  rather than a smart per-part merge.
- No optimistic locking on pattern edits -- last-write-wins if two people
  somehow edit the same pattern at once (only its uploader and admins can,
  so this is inherently rare).
- No migration tool (Alembic, etc.) -- schema setup is a one-off
  `flask init-db` command for new databases, plus a purely-additive
  `flask add-*-columns` command per feature for upgrading an existing one
  (see the full list in Deploying to Render above); appropriate for the
  app's current size and rate of schema change.
- Manually-uploaded pattern photos are stored as bytes directly in
  Postgres (re-encoded as JPEG, capped at 1600px/2MB raw upload) rather
  than a dedicated object store -- simplest option given Render's web
  service has no persistent disk, at the cost of DB size growing with
  photo count and no CDN in front of them.
- Rate limiting (Flask-Limiter) uses in-memory storage, its default --
  fine at this app's current single-service scale, but limits reset on
  every restart and wouldn't be shared across multiple worker processes
  if the deployment ever grows beyond one.
