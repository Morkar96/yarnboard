"""
WSGI entry point.

Local dev:   flask --app wsgi run --port 5001
Local dev:   python wsgi.py
Production:  gunicorn wsgi:app   (see Procfile / render.yaml)
One-off DB setup: flask --app wsgi init-db
"""

from dotenv import load_dotenv

# Load backend/.env for local development. In production, real environment
# variables are set by Render and this is a harmless no-op (no .env file
# exists there).
load_dotenv()

from app import create_app  # noqa: E402  (must run after load_dotenv)

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5001)
