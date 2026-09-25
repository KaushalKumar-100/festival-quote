CREATE TABLE IF NOT EXISTS lead_payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_id INTEGER NOT NULL UNIQUE,
  provider_id INTEGER NOT NULL,
  amount INTEGER NOT NULL CHECK (amount >= 0),
  currency TEXT NOT NULL DEFAULT 'INR',
  status TEXT NOT NULL DEFAULT 'pending',
  gateway TEXT NOT NULL DEFAULT 'manual',
  gateway_payment_link_id TEXT,
  gateway_payment_id TEXT,
  payment_url TEXT,
  reference_id TEXT NOT NULL UNIQUE,
  failure_reason TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(quote_id) REFERENCES quotes(id),
  FOREIGN KEY(provider_id) REFERENCES providers(id)
);

CREATE INDEX IF NOT EXISTS idx_lead_payments_status ON lead_payments(status);
CREATE INDEX IF NOT EXISTS idx_lead_payments_provider ON lead_payments(provider_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_payments_gateway_link
  ON lead_payments(gateway_payment_link_id)
  WHERE gateway_payment_link_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_lead_payments_gateway_payment
  ON lead_payments(gateway_payment_id)
  WHERE gateway_payment_id IS NOT NULL;