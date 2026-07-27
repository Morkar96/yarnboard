# Yarnboard is one deployable unit (a single combined Render service --
# see render.yaml) but two separate toolchains during development (Python
# backend, Node frontend), so targets here are organized by toolchain
# rather than by "service": `test-backend`/`test-frontend` can be run and
# reasoned about independently, `test`/`install` just call both.
#
# Assumes the backend venv already exists at backend/.venv (see README's
# Local setup) -- run `make install` first on a fresh checkout.

.PHONY: install install-backend install-frontend \
        dev-backend dev-frontend \
        test test-backend test-frontend \
        build build-check

install: install-backend install-frontend

install-backend:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt

install-frontend:
	cd frontend && npm install

dev-backend:
	cd backend && .venv/bin/flask --app wsgi run --port 5001

dev-frontend:
	cd frontend && npm run dev

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
