# FestivalQuote Provider Response Portal — Security Design

## Threat model

The provider portal is a bearer-link interface. A provider does not receive an account password; instead, an operations administrator generates a high-entropy access link.

The link is a credential. Anyone who possesses it can act as that provider, so the implementation follows these controls:

- The raw token is generated with a cryptographically secure random source.
- Only a SHA-256 hash of the token is persisted in D1.
- The raw token is returned only to the authenticated admin action that creates or rotates it.
- The portal uses a URL fragment (#token=...), so the bearer token is not sent to the Worker as part of the HTTP request or normal referrer data.
- API calls move the token into the X-Provider-Token request header.
- The provider page never stores the token in localStorage.
- Generating a new portal link rotates the credential and invalidates the previous link.
- Deactivated providers cannot authenticate to the portal.
- Provider APIs scope every quote read/write by the authenticated provider ID, preventing horizontal access to another provider's leads.
- Provider APIs cannot change lead fees, customer-selection state, payment state, or provider identity.
- Quotes become read-only to the provider after customer selection or provider payment.
- Provider responses expose request requirements but deliberately omit customer name, phone and email.

## Data minimization

The provider portal receives only the data needed to respond:

- request ID
- festival
- service
- city
- event date
- budget
- requirement details
- current quote response fields

Customer contact information remains in the admin/customer workflows.

## Rotation and revocation

There is no persistent provider password. Rotation is the revocation mechanism:

1. Admin generates a new link.
2. The old token hash is replaced.
3. The old link immediately fails authentication.
4. The provider receives the new link through the operator's chosen private channel.

## Database migration

Production databases must receive migrations/0002_provider_portal.sql through the reviewed D1 migration process. schema.sql remains the fresh/local baseline.

## Remaining production controls

Before public provider rollout:

- Cloudflare rate limiting/WAF must cover provider API endpoints.
- Cloudflare Workers Observability should be enabled.
- Provider links should be distributed only through private channels.
- Do not log raw provider tokens.
- Run deployed browser E2E tests for link generation, authentication, quote response, rotation and deactivation.
