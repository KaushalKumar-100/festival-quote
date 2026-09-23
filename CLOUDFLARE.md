# Cloudflare production setup

FestivalQuote is now structured as one Cloudflare Worker with FastAPI + Workers Static Assets + D1. Cloudflare officially supports FastAPI on Python Workers and D1 bindings from Python Workers. See the Cloudflare docs for the current setup.

## One-time Cloudflare setup

1. Create a Cloudflare account and open Workers & Pages.
2. Create a D1 database named `festivalquote-prod`.
3. Copy the database ID.
4. Replace `REPLACE_WITH_YOUR_D1_DATABASE_ID` in `wrangler.jsonc`.
5. Run the schema against the remote database:
   `npx wrangler d1 execute festivalquote-prod --remote --file=schema.sql`
6. Deploy:
   `uv run pywrangler deploy`
7. Add the Worker secret:
   `npx wrangler secret put ADMIN_KEY`
8. The Worker URL will be a `workers.dev` URL unless a custom domain is configured.

## GitHub automatic deployments

Cloudflare Workers supports GitHub integration. Connect this repository to Workers Builds and deploy from `main`. Keep the D1 database binding configured in the Worker.

## Important

Do not commit the D1 database ID if your Cloudflare policy requires it to stay private; Cloudflare Wrangler configurations commonly contain it, but secrets such as ADMIN_KEY must never be committed. Do not store customer payment credentials in D1.

## Production architecture

Customer browser -> Cloudflare Worker -> FastAPI routes / Static Assets -> D1.

Provider contact and quote verification remain manual initially. This is intentional: prove demand before paying for external APIs or automated messaging.