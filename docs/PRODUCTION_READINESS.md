# FestivalQuote — Production Readiness Audit

This document is the engineering gate for the current Cloudflare Worker implementation.

## Current architecture

Customer browser → Cloudflare Worker → FastAPI on Python Workers → D1

Static customer, tracker, request-center and admin pages are served from Workers Static Assets.

## Audit findings and actions

### Critical

- **Customer request editing:** the private tracker now receives the customer-editable request fields needed to populate the edit form. Access still requires the random request token.
- **Credential hygiene:** the hardcoded local admin fallback was removed. Local development now requires `.dev.vars`; production requires the Cloudflare `ADMIN_KEY` secret.
- **Private surfaces:** admin, tracker and request-center pages are marked `noindex`; the private paths are also excluded in `robots.txt`.
- **Admin authentication:** admin APIs remain protected server-side by `ADMIN_KEY`. The browser only keeps the key in memory for the current dashboard session.
- **Unexpected errors:** production API exceptions return a generic message rather than a stack trace.
- **Security headers:** baseline anti-framing, MIME-sniffing, referrer and permissions headers are applied.

### High priority

- **Public abuse protection:** configure Cloudflare rate limiting/WAF for `POST /api/requests` and the admin surface before public launch. This cannot be safely replaced by an in-memory Worker limiter because Worker instances are distributed and ephemeral.
- **Observability:** enable Cloudflare Logs/Workers Observability and monitor request errors, latency and deployment health.
- **Production secret:** verify `ADMIN_KEY` exists in the production Worker environment before merging to production.
- **Database migration discipline:** use explicit reviewed D1 migrations for changes to an existing production database. `schema.sql` is the baseline for fresh/local databases.
- **End-to-end browser validation:** test customer submission → tracker → edit → request center → provider quote → customer quote display on a deployed environment before public launch.

### Medium priority

- Add a formal API request-id/correlation mechanism for operational debugging without logging request tokens or unnecessary personal data.
- Add automated browser E2E coverage for the highest-value customer and admin journeys.
- Add pagination/archival strategy for admin request/provider lists as volume grows beyond the current bounded API responses.
- Consider phone/WhatsApp OTP lookup for cross-device request recovery; localStorage is intentionally limited to the same browser/device.

## Regression contract

CI now verifies:

1. The D1 schema creates the required tables, columns and indexes.
2. The public request, private tracker, request center and admin pages contain their required structural hooks.
3. Private pages are marked `noindex`.
4. The source contains no hardcoded local admin credential.
5. The tracker/edit flow and request-token header remain present.

## Deployment gate

Do not call the product production-ready until all of these are verified:

- [ ] Production `ADMIN_KEY` secret exists.
- [ ] Production D1 schema/migrations are verified.
- [ ] Rate limiting/WAF is configured.
- [ ] HTTPS/custom domain is active.
- [ ] Health endpoint responds successfully.
- [ ] Customer request flow passes end-to-end.
- [ ] Customer tracker and edit flow pass end-to-end.
- [ ] Admin request/provider/quote flows pass end-to-end.
- [ ] Mobile checks pass at 320/375/390/414px plus tablet/desktop.
- [ ] Cloudflare logs/observability show no unexplained errors.
- [ ] Rollback path is documented and tested.

The engineering rule remains: **Inspect → Plan → Implement → Test → Review → Improve → Verify.**
