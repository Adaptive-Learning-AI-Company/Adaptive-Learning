# Upgrade Installation Guide

This guide covers the full rollout of the current upgrade set:

- user profile expansion
- personal OpenAI keys
- password reset by email
- Stripe subscriptions and hosted-usage caps
- promo codes and manual access grants
- node link catalogs and admin review
- browser deployment for `adaptivetutor.ai`
- updated Godot export workflow

## 1. Before You Deploy

1. Back up your Render Postgres database.
2. Rotate any secret that has ever been shared in chat or copied into notes.
3. Confirm your Render backend URL. You will need it for:
   - `PUBLIC_BASE_URL`
   - Stripe success/cancel/portal return URLs
   - generated Godot export config
4. Decide whether you want any temporary open access at all.
   - Recommended production setting: `ALLOW_OPEN_TUTORING_ACCESS=false`
   - Only set `ALLOW_OPEN_TUTORING_ACCESS=true` for a temporary dev/demo environment where users should be able to reach the agents without a subscription or access code.

## 2. Local Secret Files

Create or update your private secret file:

```bash
cp .env.secret.example .env.secret
```

Set real values in `.env.secret` or `.env`:

```dotenv
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
EMAIL_PASSWORD=...
SECRET_KEY=...
PROFILE_SECRET_KEY=...
PROMO_CODE_HASH_SECRET=...
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
```

Keep these files out of Git:

- `.env`
- `.env.secret`

On Render, you can also mount the same content as a secret file at:

- `/etc/secrets/.env`
- `/etc/secrets/.env.secret`

The backend now reads those Render secret-file paths explicitly.

Files that are safe to commit:

- `.env.public`
- `.env.secret.example`
- `billing_config.json`
- `knowledge_graph_links.json`

## 3. Update Public Runtime Config

Edit `.env.public` for production values before copying them into Render:

```dotenv
EMAIL_HOST=smtp.ionos.com
EMAIL_PORT=587
EMAIL_USER=admin@adaptivetutor.ai
PUBLIC_BASE_URL=https://your-render-backend.onrender.com
CORS_ALLOWED_ORIGINS=https://adaptivetutor.ai,https://www.adaptivetutor.ai

BILLING_ALLOW_PAST_DUE_ACCESS=false
ALLOW_OPEN_TUTORING_ACCESS=false
ADMIN_USERNAMES=your_admin_username

STRIPE_PRICE_ID_BYOK_MONTHLY=price_...
STRIPE_PRICE_ID_HOSTED_MONTHLY=price_...
STRIPE_SUCCESS_URL=https://your-render-backend.onrender.com/billing/success
STRIPE_CANCEL_URL=https://your-render-backend.onrender.com/billing/cancel
STRIPE_PORTAL_RETURN_URL=https://your-render-backend.onrender.com/billing/manage-return
```

Notes:

- `billing_config.json` provides default plans and caps even if env vars are missing.
- Env vars can still override those defaults if you want to tune plans later without editing JSON.
- Hosted tutor models can now be changed from the in-app admin screen with separate `teacher`, `verifier`, and `fast` selections. Gemini selections require `GOOGLE_API_KEY` on the backend.
- Hosted tutoring currently defaults to `gpt-5-mini`.
- With `ALLOW_OPEN_TUTORING_ACCESS=false`, users must have either an active subscription or an active access code/grant before the tutoring agents can be used.

## 4. Stripe Dashboard Setup

Create these recurring monthly prices in Stripe:

1. `byok_monthly`
   - Price: `$0.99/month`
   - User supplies their own OpenAI key
2. `hosted_monthly`
   - Price: `$4.99/month`
   - Uses your platform OpenAI key

Then copy the Stripe price IDs into:

- `STRIPE_PRICE_ID_BYOK_MONTHLY`
- `STRIPE_PRICE_ID_HOSTED_MONTHLY`

Also add to Render:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`

Webhook:

1. Point Stripe webhooks at:
   - `https://your-render-backend.onrender.com/stripe/webhook`
2. Subscribe to at least:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`
   - `invoice.paid`

## 5. Render Backend Deploy

Render settings:

- Build Command: `pip install -r backend/requirements.txt`
- Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Environment Variable: `PYTHON_VERSION=3.13.5`

Copy these into Render Environment Variables or a Render secret file:

- all non-secret values from `.env.public`
- all secret values from `.env.secret` or `.env`
- `DATABASE_URL` from Render Postgres

If you use a Render secret file, `/etc/secrets/.env` is supported directly now.

Important behavior on startup:

- the backend creates new tables automatically
- missing columns are added automatically
- indexes and default backfills are applied automatically

You do not need to delete or reinitialize the database.

## 6. Godot Production URL

You no longer need to create `godot_project/scripts/Secrets.gd` manually.

Godot exports now generate a temporary runtime config file automatically from:

- `PUBLIC_BASE_URL` in your shell
- or `PUBLIC_BASE_URL` from `/etc/secrets/.env`
- or `PUBLIC_BASE_URL` from `.env.public`, `.env`, or `.env.secret`

The generated file is:

- `godot_project/scripts/GeneratedSecrets.gd`

It is gitignored and rebuilt automatically by the export scripts.

## 7. Rebuild Local Python Environment

For local development:

```bash
uv sync
```

Recommended sanity checks:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest backend/tests -q
UV_CACHE_DIR=/tmp/uv-cache uv run python -c "import backend.main"
```

## 8. Build The Browser Site

Rebuild the static browser bundle:

```bash
bash scripts/build_browser_site.sh
```

Important:

- the script now fails if `PUBLIC_BASE_URL` is missing
- the script generates `godot_project/scripts/GeneratedSecrets.gd` automatically
- generated browser output lives in `html/app/` and is intentionally not committed

## 9. Upload To IONOS

Upload the contents of `html/` to your IONOS web root.

That includes:

- `html/index.html`
- `html/styles.css`
- `html/site.webmanifest`
- `html/.htaccess`
- the generated `html/app/` folder

The `.htaccess` file is important for correct web asset handling, especially `.wasm`.

## 10. Optional Native/Desktop Exports

If you want refreshed Android, Linux, Windows, and Web exports:

```bash
bash scripts/export_godot_platforms.sh
```

Or keep them auto-regenerated while editing:

```bash
bash scripts/watch_godot_exports.sh
```

Outputs go to `platform_executables/`.

## 11. First-Run Validation Checklist

After deployment, test these in order:

1. Open `https://adaptivetutor.ai`.
2. Confirm login and registration work from the browser.
3. Confirm the app talks to the Render backend, not the placeholder URL.
4. Register a new user and open the profile screen.
5. Save a personal OpenAI API key and verify it persists.
6. Trigger password reset and confirm the email arrives.
7. Create a Stripe checkout session and complete a test subscription.
8. Open the billing portal from the app.
9. Redeem an access code.
10. As admin, create and revoke:
    - a promo code
    - a direct access grant
11. Submit a user link for a node and approve it from the admin panel.
12. Test the site on a real iPad in Safari.

## 12. Known Non-Blocking Notes

- `datetime.utcnow()` deprecation warnings still appear in parts of the backend and tests. They are warnings, not current blockers.
- The web bundle is large. Expect slower first load on iPad or slower connections.
- Godot web export prints some local socket/Android build-tool warnings during export on Linux; the web export still completes successfully here.

## 13. Recommended Push Sequence

1. Update `.env.secret` locally.
2. Update `.env.public` for production URLs and Stripe IDs.
3. Make sure `PUBLIC_BASE_URL` is set correctly in your `.env`.
4. Run:
   - `uv sync`
   - `UV_CACHE_DIR=/tmp/uv-cache uv run pytest backend/tests -q`
   - `bash scripts/build_browser_site.sh`
5. Commit and push to GitHub.
6. Let Render deploy.
7. Copy the same env values into Render.
8. Upload `html/` to IONOS.
9. Run the validation checklist above.
