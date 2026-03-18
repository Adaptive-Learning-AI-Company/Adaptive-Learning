# Adaptive Learning 3D

A re-envisioned adaptive learning system using a 3D Godot interface and a LangGraph-based Multi-Agent backend.

## Architecture

- **Frontend**: Godot 4.5+ (3D Library Interface)
- **Backend**: Python (FastAPI + LangGraph)

For the full rollout checklist for this upgrade, see [UPGRADE_INSTALLATION_GUIDE.md](/home/jglossner/Adaptive-Learning/UPGRADE_INSTALLATION_GUIDE.md).

## Prerequisites

- Godot 4.5+
- Python 3.13
- OpenAI API Key
- [uv](https://github.com/astral-sh/uv)

## Setup & Running

### 1. Backend

1. Navigate to the root directory.
2. Local development uses `uv sync`:
   ```bash
   uv sync
   ```
   If you want to activate it manually:
   ```bash
   source .venv/bin/activate
   ```
3. Configure environment variables:
   ```bash
   cp .env.secret.example .env.secret
   ```
   The project now supports split env files:
   - [`.env.public`](/home/jglossner/Adaptive-Learning/.env.public): safe to commit, contains non-secret defaults and recommended public config
   - `.env` or `.env.secret`: gitignored, keep real secrets there locally
   - [`.env.secret.example`](/home/jglossner/Adaptive-Learning/.env.secret.example): secret template
   - Render secret files at `/etc/secrets/.env` and `/etc/secrets/.env.secret` are also loaded automatically

   Set the private values in `.env` or `.env.secret`:
   ```bash
   OPENAI_API_KEY="sk-..."          # Platform fallback key
   EMAIL_PASSWORD="..."             # IONOS mailbox password for reset emails
   SECRET_KEY="..."                 # JWT/reset-token signing secret
   PROFILE_SECRET_KEY="..."         # Profile secret encryption key
   PROMO_CODE_HASH_SECRET="..."     # Promo/access-code hashing secret
   ```
   If you use Stripe, also keep these in `.env` or `.env.secret`:
   ```bash
   STRIPE_SECRET_KEY="..."
   STRIPE_WEBHOOK_SECRET="..."
   ```
   Public/runtime values like `PUBLIC_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `EMAIL_HOST`, `EMAIL_USER`, `ADMIN_USERNAMES`, and Stripe price IDs can live in [`.env.public`](/home/jglossner/Adaptive-Learning/.env.public).
   Tutoring access is locked down by default. Only users with an active subscription or access code can reach the agents unless you explicitly set `ALLOW_OPEN_TUTORING_ACCESS=true` for a temporary open-access environment.
   On Render, copy values from `.env.public` plus your private `.env` or `.env.secret`, or mount the secret values at `/etc/secrets/.env`, and also provide `DATABASE_URL` from your managed Postgres instance.
   Godot exports now derive their production backend URL from `PUBLIC_BASE_URL`; no manual `Secrets.gd` file is required.
4. Run the server:
   ```bash
   uv run uvicorn backend.main:app --reload
   ```
   Server will run at `http://127.0.0.1:8000`.

### Render Deploy

Render should keep using `pip`, not `uv`.

- Build Command:
  ```bash
  pip install -r backend/requirements.txt
  ```
- Start Command:
  ```bash
  uvicorn backend.main:app --host 0.0.0.0 --port $PORT
  ```
- Recommended environment variable:
  ```bash
  PYTHON_VERSION=3.13.5
  ```
- Copy values from [`.env.public`](/home/jglossner/Adaptive-Learning/.env.public) and your private `.env`/`.env.secret` into Render Environment Variables, or mount the secret file at `/etc/secrets/.env`.

Dependency ownership is split intentionally:

- Local: [pyproject.toml](/home/jglossner/Adaptive-Learning/pyproject.toml) + `uv sync`
- Render: [backend/requirements.txt](/home/jglossner/Adaptive-Learning/backend/requirements.txt) + `pip install -r ...`

### 2. Frontend (Godot)

1. Open Godot Engine.
2. Import the project located in `godot_project/`.
3. Open `scenes/Library.tscn` and press Play (F5).
4. Enter a topic in the UI (e.g., "History of Rome") and click "Start Learning".
5. Chat with the agents!

### 3. Automatic Platform Exports

If you want exports regenerated whenever a Godot project file changes:

1. Make sure the Godot CLI/headless binary is installed and available as `godot4` or `godot`.
   The export script also auto-detects `/home/jglossner/Apps/Godot_v4.5.1-stable_linux.x86_64` on this machine.
2. Export presets for `Android`, `Windows Desktop`, `Linux/X11`, and `Web` are already in the repo. If your local Godot version rewrites preset settings, regenerate them once in `Project > Export`.
3. Start the watcher from the repo root:
   ```bash
   bash scripts/watch_godot_exports.sh
   ```

Outputs are written to `platform_executables/` at the repo root:

- `platform_executables/android/Adaptive Learning 3D.apk`
- `platform_executables/linux/Adaptive Learning 3D.x86_64`
- `platform_executables/windows/Adaptive Learning 3D.exe`
- `platform_executables/web/Adaptive Learning 3D Web.zip`

The web target is a browser bundle, not a native Chrome executable. Exporting from Linux to additional first-party Godot targets beyond Android, Windows, Linux, and Web generally requires platform-specific SDKs or a non-Linux host.

### 4. Static Website For `adaptivetutor.ai`

The repo now includes a static browser site in [html/](/home/jglossner/Adaptive-Learning/html):

- [html/index.html](/home/jglossner/Adaptive-Learning/html/index.html): landing page
- `html/app/`: generated Godot browser bundle
- [html/.htaccess](/home/jglossner/Adaptive-Learning/html/.htaccess): MIME/cache hints for Apache-style hosting such as IONOS

To rebuild the browser app bundle:

```bash
bash scripts/build_browser_site.sh
```

Then upload the contents of `html/` to your IONOS web root. Important notes:

- `html/app/` is treated as generated output and should be uploaded to IONOS, but it is intentionally ignored by Git because the `wasm`/`pck` files are large.
- Your Render backend must allow the site origin in `CORS_ALLOWED_ORIGINS`.
- Set `PUBLIC_BASE_URL` and frontend backend URL settings to the real production HTTPS endpoints before going live.
- Verify that IONOS serves `.wasm` correctly; the included `.htaccess` adds the expected MIME type.

## Features

- **3D Library Environment**: Visual metaphor for selecting topics.
- **Profile Controls**: Recovery email, avatar selection, and optional user-provided OpenAI API keys.
- **Password Reset by Email**: Sends reset links through configurable SMTP, including IONOS.
- **Adaptive Agents**:
    - **Supervisor**: Routes requests.
    - **Teacher**: Explains concepts.
    - **ProblemGenerator**: Creates practice.
    - **Verifier**: Checks answers.
- **Persisted State**: Session memory via LangGraph.
