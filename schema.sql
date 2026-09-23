CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT,
  city TEXT NOT NULL,
  festival TEXT NOT NULL DEFAULT 'Other Festival',
  service TEXT NOT NULL,
  event_date TEXT NOT NULL,
  budget TEXT NOT NULL,
  details TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new',
  tracking_token TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  service TEXT NOT NULL,
  phone TEXT DEFAULT '',
  whatsapp TEXT,
  source_url TEXT,
  notes TEXT DEFAULT '',
  lead_fee INTEGER DEFAULT 150,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER NOT NULL,
  provider_id INTEGER NOT NULL,
  price INTEGER,
  package TEXT DEFAULT '',
  availability TEXT DEFAULT 'unknown',
  response_note TEXT DEFAULT '',
  lead_fee INTEGER DEFAULT 0,
  lead_status TEXT NOT NULL DEFAULT 'pending',
  customer_selected INTEGER NOT NULL DEFAULT 0,
  provider_paid INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(request_id) REFERENCES requests(id),
  FOREIGN KEY(provider_id) REFERENCES providers(id)
);

CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_city_service ON requests(city, service);
CREATE INDEX IF NOT EXISTS idx_quotes_request ON quotes(request_id);
CREATE INDEX IF NOT EXISTS idx_quotes_lead_status ON quotes(lead_status);

INSERT OR IGNORE INTO providers (id,name,city,service,phone,source_url,notes,lead_fee) VALUES
(1,'Magic Moments Party Planners - Guwahati','Guwahati','Decoration / Event Planning','+91 76380 62984','https://www.google.com/maps/search/?api=1&query=Magic+Moments+Party+Planners+Guwahati','Real local-business listing; verify festival availability and pricing.',150),
(2,'Brahmaputra Tent House & Decorators','Guwahati','Decoration / Tent / Event','+91 88766 72350','https://www.google.com/maps/search/?api=1&query=Brahmaputra+Tent+House+Decorators+Guwahati','Real local-business listing; verify festival availability and pricing.',150),
(3,'ChitraGeek Studios Pvt. Ltd.','Guwahati','Photography','+91 97425 93010','https://www.google.com/maps/search/?api=1&query=ChitraGeek+Studios+Guwahati','Real local-business listing; verify event date and package.',150),
(4,'Samagri Store','Guwahati','Puja Materials','+91 88225 94244','https://www.google.com/maps/search/?api=1&query=Samagri+Store+Guwahati','Real local-business listing; verify stock and delivery.',100),
(5,'Shaanze Luxury Gifting Studio','Guwahati','Corporate / Festival Gifting','+91 88110 76134','https://www.google.com/maps/search/?api=1&query=Shaanze+Luxury+Gifting+Studio+Guwahati','Real local-business listing; verify festive stock, MOQ and delivery.',150),
(6,'Kamrup Metro Catering & Hospitality Service','Guwahati','Catering','+91 98640 26328','https://www.google.com/maps/search/?api=1&query=Kamrup+Metro+Catering+Hospitality+Service+Guwahati','Real local-business listing; verify date, menu and guest count.',150),
(7,'Mayabini event and wedding planners','Guwahati','Event Planning / Decoration','','https://www.google.com/maps/search/?api=1&query=Mayabini+event+wedding+planners+Guwahati','Real local-business listing; verify contact and festival availability.',150),
(8,'Aysha decorators','Guwahati','Decoration / Floral','+91 76358 49985','https://www.google.com/maps/search/?api=1&query=Aysha+decorators+Guwahati','Real local-business listing; verify festival availability and pricing.',150),
(9,'Balloons Unlimited Guwahati','Guwahati','Balloons / Event Decoration','+91 70028 70793','https://www.google.com/maps/search/?api=1&query=Balloons+Unlimited+Guwahati','Real local-business listing; verify festival availability and pricing.',100),
(10,'Planora Events','Guwahati','Event Planning / Decoration / Catering','+91 93658 14266','https://www.google.com/maps/search/?api=1&query=Planora+Events+Guwahati','Public business page; verify current packages and availability.',150),
(11,'Photography World Guwahati','Guwahati','Photography','+91 70022 49506','https://www.google.com/maps/search/?api=1&query=Photography+World+Guwahati','Real local-business listing; verify event date and package.',150),
(12,'SP Photography Guwahati','Guwahati','Photography','+91 97069 67139','https://www.google.com/maps/search/?api=1&query=SP+Photography+Guwahati','Real local-business listing; verify event date and package.',150),
(13,'Manab Deka Photography','Guwahati','Photography','+91 70991 09463','https://www.google.com/maps/search/?api=1&query=Manab+Deka+Photography+Guwahati','Real local-business listing; verify event date and package.',150),
(14,'POOJA CENTRE - PUJA SAMAGRI WHOLESALE','Guwahati','Puja Materials','+91 95310 00999','https://www.google.com/maps/search/?api=1&query=POOJA+CENTRE+PUJA+SAMAGRI+WHOLESALE+Guwahati','Real local-business listing; verify stock and delivery.',100),
(15,'Prodopia','Guwahati','Corporate Gifting','+91 81330 29442','https://www.google.com/maps/search/?api=1&query=Prodopia+Guwahati','Real local-business listing; verify festive catalog, MOQ and delivery.',150),
(16,'PriNiks','Guwahati','Corporate Gifting','+91 98540 20531','https://www.google.com/maps/search/?api=1&query=PriNiks+Guwahati','Real local-business listing; verify festive catalog, MOQ and delivery.',150);