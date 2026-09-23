# Deployment

## Render API
Create a web service from this repository.
Build command: pip install -r backend/requirements.txt
Start command: uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT

Set ADMIN_KEY to a long random secret.
Set CORS_ORIGINS to your Vercel URL.
Use PostgreSQL for durable production storage once the MVP validates demand.

## Vercel
Import this repository into Vercel and deploy the root project.
The public customer page is frontend/index.html.
The admin page is admin/index.html.

The customer page can point at the Render API by setting localStorage key fq_api in the browser. Do not put the admin key in frontend code.

## Scope
The MVP intentionally keeps provider contact and payment manual. Customers pay providers directly. FestivalQuote does not hold customer funds or guarantee bookings.