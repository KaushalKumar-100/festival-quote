-- FestivalQuote migration 0002: secure provider response portal
ALTER TABLE providers ADD COLUMN portal_token_hash TEXT;
ALTER TABLE providers ADD COLUMN portal_token_created_at TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_providers_portal_token_hash ON providers(portal_token_hash) WHERE portal_token_hash IS NOT NULL;
