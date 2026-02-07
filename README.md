# Balloono (Flask)

Multiplayer Balloono-inspired game built for PythonAnywhere using Flask and long-polling.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000` and join a room.

## Auth and storage

User accounts are stored in SQLite by default (`balloono.db`). You can override
it with `DATABASE_URL`.

Recommended environment variables:

- `SECRET_KEY`: session signing secret
- `DATABASE_URL`: e.g. `sqlite:///balloono.db`

## PythonAnywhere deployment

Project path: `/home/greenmangroup/balloono`

### 1) Upload code

Clone or upload this repo into `/home/greenmangroup/balloono`.

### 2) Create virtualenv and install requirements

```bash
cd /home/greenmangroup/balloono
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Configure WSGI

In the Web tab, set the WSGI file to something like:

```python
import sys

path = "/home/greenmangroup/balloono"
if path not in sys.path:
    sys.path.append(path)

from app import app as application
```

### 4) Static files

Add a static files mapping:

- URL: `/static/`
- Directory: `/home/greenmangroup/balloono/static/`

### 5) Reload

Reload the web app. Share your room name to play together.

## Automatic deploy (GitHub Actions)

This repo includes a workflow that uploads files to PythonAnywhere and reloads
your webapp on every push to `main`.

Add these GitHub Actions secrets:

- `PA_USERNAME`: your PythonAnywhere username
- `PA_TOKEN`: API token from the PythonAnywhere Account page
- `PA_HOST`: `www.pythonanywhere.com` or `eu.pythonanywhere.com`
- `PA_TARGET`: `/home/greenmangroup/balloono`
- `PA_DOMAIN`: your webapp domain (for example, `greenmangroup.pythonanywhere.com`)

The workflow uses `scripts/deploy_pythonanywhere.py` to upload files using the
PythonAnywhere API and then call the webapp reload endpoint.

## Notes

- Multiplayer uses long-polling to avoid WebSocket requirements.
- Server state is in-memory; restarting the app resets active rooms.
