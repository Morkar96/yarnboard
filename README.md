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
  (requests + BeautifulSoup) based on heading keywords and list markup.
  There's no universal format for pattern pages across the web, so the
  scraper's output is always shown to the user as an **editable draft**
  before anything is saved -- never assume it's 100% correct.
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

## Local setup

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # leave DATABASE_URL unset to use local SQLite,
                             # and RESEND_API_KEY unset to log emails instead
                             # of sending them
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
   from step 1), and `RESEND_API_KEY`/`RESEND_FROM_EMAIL` (from
   [resend.com](https://resend.com) -- pattern-updated emails are just
   logged instead of sent if these are left unset). Update
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
   ones that already exist.
5. Grant yourself edit-any-pattern rights once:
   `DATABASE_URL=<neon-connection-string> flask --app wsgi make-admin you@example.com`.

## Known limitations

- The scraper is heuristic and best-effort; it's designed to feed a human
  review step, not to be a guaranteed-correct parser for every pattern site.
- No email verification on signup.
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
  `flask add-versioning-columns` command for upgrading an existing one;
  appropriate for the app's current size and rate of schema change.
