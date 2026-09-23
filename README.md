# FestivalQuote

Remote-first festival quote matching service MVP for India.

## Goal
Customers submit a festival service request; the operator sources up to 3 relevant local providers and returns comparable options. The MVP is designed to be operated fully remotely and validated before paid automation.

## Current business model
- Customer: free during validation.
- Provider: pay-per-qualified-lead or pay-per-introduced-customer.
- Initial operator workflow: Google Maps/Instagram/web research + WhatsApp/email/phone.
- No inventory, no physical meetings, no local office required.

## MVP
The first release provides a responsive request form, service/category capture, admin lead queue, provider records, quote comparison, and notification-ready status fields. SQLite is used for zero-cost local development; PostgreSQL is supported for production.

## Run locally
```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# Linux/macOS
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Frontend can be opened from `frontend/index.html` during MVP validation. The API is under `/api`.

## Deployment
- Backend: Render
- Frontend: Vercel/static hosting
- Database: start with SQLite; switch to Render PostgreSQL when paid usage justifies it.

See `docs/OPERATIONS.md` and `.env.example`.
