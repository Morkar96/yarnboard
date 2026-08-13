# Yarnboard is one deployable unit (a single combined Render service --
# see render.yaml) but two separate toolchains during development (Python
# backend, Node frontend), so targets here are organized by toolchain
# rather than by "service": `test-backend`/`test-frontend` can be run and
# reasoned about independently, `test`/`install` just call both.
#
# Assumes the backend venv already exists at backend/.venv (see README's
# Local setup) -- run `make install` first on a fresh checkout.

.PHONY: install install-backend install-frontend \
        dev dev-backend dev-frontend down \
        test test-backend test-frontend \
        build build-check

install: install-backend install-frontend

install-backend:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt

install-frontend:
	cd frontend && npm install

# Runs both dev servers concurrently (they're foreground processes, so
# `dev-backend && dev-frontend` would just block forever on the first one
# and never start the second). The trap ensures Ctrl+C kills both instead
# of leaving the backend running orphaned in the background.
dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-frontend & \
	wait

dev-backend:
	cd backend && .venv/bin/flask --app wsgi run --port 5001

dev-frontend:
	cd frontend && npm run dev

# `dev`'s Ctrl+C trap only fires for the shell that ran it in the
# foreground -- a `make dev` backgrounded/detached (or a terminal closed
# out from under it) leaves the Flask and Vite processes running with
# nothing left to catch the signal. Kill by port rather than by process
# name (`flask`/`node`) so this can't take out an unrelated process that
# happens to share those names; 5001/5173 are hardcoded to this app's dev
# servers (see dev-backend above and frontend/vite.config.ts).
down:
	@echo "Stopping Yarnboard dev servers (ports 5001, 5173)..."
	@-lsof -ti :5001 -ti :5173 | xargs kill 2>/dev/null
	@echo "Done."

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/pytest

test-frontend:
	cd frontend && npm run test

# Mirrors render.yaml's buildCommand exactly, so a broken production build
# can be caught locally before pushing -- see that file if the two ever
# drift, they should always match.
build: build-check

build-check:
	cd backend && pip install -r requirements.txt && cd ../frontend && npm install && npm run build
