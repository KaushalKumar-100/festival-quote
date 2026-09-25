# FestivalQuote deployment

## Active production architecture

FestivalQuote currently runs as a single Cloudflare Worker:

`Browser → Cloudflare Worker → FastAPI → D1`

Static customer/admin/tracking pages are served from `public/` through Workers Static Assets. API routes live in `src/worker.py`.

Cloudflare documents FastAPI on Python Workers and the `uv run pywrangler dev/deploy` workflow: https://developers.cloudflare.com/workers/languages/python/packages/fastapi/

## Local development

From the repository root:

```powershell
uv --version
uv run pywrangler dev
```

Use `.dev.vars` for local secrets:

```env
ADMIN_KEY="replace-with-a-local-secret"
```

Never commit `.dev.vars`.

Local D1 is intentionally separate from the remote production D1. Initialize it from the schema when needed:

```powershell
npx wrangler d1 execute festivalquote-prod --local --file=./schema.sql
```

## Cloudflare Workers Builds

Because this is a Python Worker, do not leave Workers Builds on its default `npx wrangler deploy` command. Configure **Settings → Builds** for the Worker as follows:

- Build command: leave empty
- Production deploy command: `npm run deploy`
- Non-production/preview command: `npm run preview`
- Root directory: `/`
- Production branch: `main`

Cloudflare's Workers Builds defaults to `npx wrangler deploy`; the repository now provides explicit `npm run deploy` / `npm run preview` commands that invoke `pywrangler`, which bundles Python dependencies correctly. See the current Cloudflare Workers Builds configuration guidance.

## Cloudflare Workers Builds

For this Python Worker, configure **Settings → Builds** as follows:

- Build command: leave empty
- Production deploy command: `npm run deploy`
- Non-production/preview command: `npm run preview`
- Root directory: `/`
- Production branch: `main`

The repository provides explicit `pywrangler` scripts because the default Workers Builds deploy command is `npx wrangler deploy`.

## Production

Before deploying, make sure the D1 binding in `wrangler.jsonc` points at the intended database and the Worker secret exists:

```powershell
npx wrangler secret put ADMIN_KEY
uv run pywrangler deploy
```

The `ADMIN_KEY` must never be placed in frontend JavaScript, `.env` files committed to Git, or the repository.

## Database migrations

`schema.sql` is the baseline schema for a fresh local database. The production database may contain incremental migrations from earlier development. For production changes, prefer explicit, reviewed `ALTER TABLE`/index migrations rather than assuming `CREATE TABLE IF NOT EXISTS` will update an existing table.

## Legacy deployment files

`render.yaml`, `vercel.json`, `backend/requirements.txt`, and the old `backend/` implementation are retained for compatibility/rollback history. They are **not** the active production path.

Do not move the live application back to Render/Vercel without deliberately migrating the D1 data model, authentication, API base URL, and deployment secrets.

## Production checklist

- [ ] Workers Builds deploy command is `npm run deploy`
- [ ] Workers Builds preview command is `npm run preview`

- [ ] Workers Builds deploy command is `npm run deploy`
- [ ] Workers Builds preview command is `npm run preview`

- [ ] `ADMIN_KEY` stored as a Worker secret
- [ ] Remote D1 schema verified
- [ ] Customer request flow tested
- [ ] Private tracker tested
- [ ] Admin login tested
- [ ] Provider activation verified
- [ ] Quote creation tested
- [ ] Quote status/payment recording tested
- [ ] Mobile layout checked
- [ ] Cloudflare Logs/Observability checked after deployment

## Security

The Worker now adds baseline security headers and returns generic JSON for unexpected server errors. Public tracking links use a random token and should be treated as private links.

For production abuse protection, add a Cloudflare rate-limiting rule for `POST /api/requests` and the admin login surface once the public domain is configured. Cloudflare supports Worker rate limiting and WAF rate-limiting rules for this purpose.
