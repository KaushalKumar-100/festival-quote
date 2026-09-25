# Cloudflare production setup

FestivalQuote runs as one Cloudflare Worker using FastAPI on Python Workers, Workers Static Assets and D1.

Cloudflare's current Python Workers workflow uses `uv run pywrangler dev` locally and `uv run pywrangler deploy` for deployment:
https://developers.cloudflare.com/workers/languages/python/

## One-time setup

1. Create the D1 database named `festivalquote-prod`.
2. Put its database ID in `wrangler.jsonc`.
3. Initialize the production schema. For an existing database, use reviewed incremental migrations rather than assuming `schema.sql` will modify old tables.
4. Set the admin secret:

```powershell
npx wrangler secret put ADMIN_KEY
```

5. Deploy:

```powershell
uv run pywrangler deploy
```

## Local development

Install/update `uv`, then run:

```powershell
uv --version
uv run pywrangler dev
```

For local-only secrets create `.dev.vars`:

```env
ADMIN_KEY="local-development-secret"
```

`.dev.vars` is ignored by Git and must never be committed.

Local D1 is separate from remote D1. If the local database is empty:

```powershell
npx wrangler d1 execute festivalquote-prod --local --file=./schema.sql
```

## Production bindings

The Worker expects:

- `DB` — D1 binding
- `ASSETS` — Workers Static Assets binding
- `APP_ENV` — production environment variable
- `ADMIN_KEY` — Worker secret

The current database ID is intentionally stored in `wrangler.jsonc` because it is configuration, not an authentication secret. Do not put API tokens or admin credentials there.

## GitHub automatic deployments

Cloudflare Workers Builds can deploy the `main` branch automatically. Keep the D1 binding configured in the Worker.

Review changes before merging production-impacting code. The project includes GitHub Actions checks that compile both the legacy backend and the active Python Worker.

## Architecture

```text
Customer browser
      ↓
Cloudflare Worker
   ┌──┴───────────────┐
   ↓                  ↓
FastAPI API      Static Assets
   ↓
D1
```

The customer request flow, private token tracker, provider management and quote management are all handled by the same Worker.

## Security

- Admin authentication uses the `ADMIN_KEY` Worker secret.
- Customer tracking uses a random private token.
- API responses are marked `no-store`.
- Baseline security headers are added by the Worker.
- `/admin` and `/track.html` are excluded from search indexing.
- Never commit `.env`, `.dev.vars`, API tokens or other credentials.
- Add Cloudflare rate limiting/WAF rules for public request creation and administrative surfaces once the production domain is configured.


## Lead payment setup

FestivalQuote uses a provider-paid lead-fee workflow. A lead fee becomes payable only after the customer selects a quote. The payment ledger is stored in D1 in `lead_payments`.

For live Razorpay Payment Links, configure these Worker secrets:

```bash
npx wrangler secret put RAZORPAY_KEY_ID
npx wrangler secret put RAZORPAY_KEY_SECRET
npx wrangler secret put RAZORPAY_WEBHOOK_SECRET
```

Configure the Razorpay webhook URL as:

```
https://<your-production-host>/api/webhooks/razorpay
```

Subscribe to the `payment_link.paid` event. The webhook signature is verified before a payment is marked paid. Do not put the Razorpay secret in frontend code.

Apply the migration before using payment endpoints:

```bash
npx wrangler d1 execute festivalquote-prod --remote --file=./migrations/0003_payments.sql
```

Local development can use the manual payment flow without Razorpay credentials. The admin can attach a verified external payment URL and reconcile the payment with a gateway/reference ID.

Razorpay Payment Links support sharing through messaging/email/social channels, and the API expects INR amounts in paise.
