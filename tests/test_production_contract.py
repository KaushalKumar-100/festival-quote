import pathlib
import sqlite3
import unittest
from html.parser import HTMLParser


ROOT = pathlib.Path(__file__).resolve().parents[1]


class HTMLContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.forms = set()
        self.meta_robots = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "form" and "id" in attrs:
            self.forms.add(attrs["id"])
        if tag == "meta" and attrs.get("name") == "robots":
            self.meta_robots.append(attrs.get("content", ""))
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])


class ProductionContractTests(unittest.TestCase):
    def test_schema_has_required_tables_columns_and_indexes(self):
        schema = (ROOT / "schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(":memory:") as conn:
            conn.executescript(schema)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue({"requests", "providers", "quotes"} <= tables)

            request_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(requests)")
            }
            provider_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(providers)")
            }
            quote_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(quotes)")
            }

            self.assertTrue(
                {
                    "name", "phone", "email", "city", "festival", "service",
                    "event_date", "budget", "details", "status",
                    "tracking_token", "created_at",
                } <= request_columns
            )
            self.assertTrue(
                {
                    "name", "city", "service", "phone", "whatsapp",
                    "source_url", "lead_fee", "active", "created_at",
                } <= provider_columns
            )
            self.assertTrue(
                {
                    "request_id", "provider_id", "price", "package",
                    "availability", "response_note", "lead_fee",
                    "lead_status", "customer_selected", "provider_paid",
                    "created_at",
                } <= quote_columns
            )

            indexes = {
                row[1]
                for row in conn.execute(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
                )
            }
            self.assertTrue(
                {
                    "idx_requests_status",
                    "idx_requests_city_service",
                    "idx_quotes_request",
                    "idx_quotes_lead_status",
                } <= indexes
            )

    def test_public_pages_have_expected_private_and_customer_flows(self):
        expected = {
            "public/index.html": {"requestForm", "serviceInput"},
            "public/track.html": {"editModal", "editForm"},
            "public/my-requests.html": {"list"},
            "public/admin/index.html": {"loginForm", "dash"},
        }
        for relative, required_ids in expected.items():
            parser = HTMLContractParser()
            parser.feed((ROOT / relative).read_text(encoding="utf-8"))
            self.assertTrue(
                required_ids <= parser.ids,
                f"{relative} missing IDs: {required_ids - parser.ids}",
            )

        for relative in ("public/track.html", "public/my-requests.html", "public/admin/index.html"):
            parser = HTMLContractParser()
            parser.feed((ROOT / relative).read_text(encoding="utf-8"))
            self.assertTrue(
                any("noindex" in value.lower() for value in parser.meta_robots),
                f"{relative} must be noindex",
            )

    def test_worker_does_not_contain_hardcoded_local_admin_secret(self):
        worker = (ROOT / "src/worker.py").read_text(encoding="utf-8")
        self.assertNotIn("festivalquote-local-admin-2026", worker)
        self.assertIn('getattr(request.scope["env"], "ADMIN_KEY", "")', worker)

    def test_private_tracker_returns_editable_fields(self):
        worker = (ROOT / "src/worker.py").read_text(encoding="utf-8")
        self.assertIn(
            "SELECT id,name,phone,email,city,festival,service,event_date,budget,details,status,created_at",
            worker,
        )
        self.assertIn('"X-Request-Token"', (ROOT / "public/track.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
