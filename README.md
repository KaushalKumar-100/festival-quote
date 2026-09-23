# FestivalQuote

Remote-first festival quote matching service for India's festival season.

## Production architecture

- Cloudflare Workers + Python FastAPI
- Cloudflare Workers Static Assets
- Cloudflare D1
- GitHub as source control
- Real Guwahati provider seed for initial validation

Cloudflare officially supports FastAPI on Python Workers and D1 bindings from Python Workers. See CLOUDFLARE.md.

## Business model

Customer submits a festival service requirement. FestivalQuote remotely sources relevant providers, verifies availability/price, and returns up to three comparable options.

Initial monetization test: qualified provider leads, starting around ₹100–₹300 per qualified lead. This is a test range, not a guaranteed market price.

Customers pay providers directly in the MVP. FestivalQuote does not hold customer funds.

## Run/deploy

Cloudflare setup is documented in CLOUDFLARE.md.

The public app lives under public/. API routes live under src/worker.py.

## Current validation scope

Start with Guwahati and a small number of services:
- Diwali decoration
- Photography
- Puja materials/services
- Catering
- Festival/corporate gifting

The provider seed is in schema.sql and data/guwahati_providers.md.

Provider listings are leads, not confirmed partners. Festival availability, pricing and inclusions must be verified before a provider is presented as an actual quote.

## Budget rule

Do not spend the ₹1,000 launch budget on paid infrastructure or ads until the product has genuine customer requests and responsive providers.