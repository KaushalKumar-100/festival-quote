import pathlib
import sqlite3
import re
import shutil
import sys
import sqlite3
import subprocess
import tempfile
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
                    "source_url", "lead_fee", "active", "portal_token_hash",
                    "portal_token_created_at", "created_at",
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
                    "idx_providers_portal_token_hash",
                } <= indexes
            )

    def test_public_pages_have_expected_private_and_customer_flows(self):
        expected = {
            "public/index.html": {"requestForm", "serviceInput"},
            "public/track.html": {"editModal", "editForm"},
            "public/my-requests.html": {"list"},
            "public/admin/index.html": {"loginForm", "dash"},
            "public/provider.html": set(),
        }
        for relative, required_ids in expected.items():
            parser = HTMLContractParser()
            parser.feed((ROOT / relative).read_text(encoding="utf-8"))
            self.assertTrue(
                required_ids <= parser.ids,
                f"{relative} missing IDs: {required_ids - parser.ids}",
            )

        for relative in (
            "public/track.html",
            "public/my-requests.html",
            "public/admin/index.html",
            "public/provider.html",
        ):
            parser = HTMLContractParser()
            parser.feed((ROOT / relative).read_text(encoding="utf-8"))
            self.assertTrue(
                any("noindex" in value.lower() for value in parser.meta_robots),
                f"{relative} must be noindex",
            )

    def test_public_javascript_parses(self):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to validate public JavaScript")
        for relative in (
            "public/index.html",
            "public/festivals.html",
            "public/quotes.html",
            "public/guide.html",
            "public/create.html",
        ):
            html = (ROOT / relative).read_text(encoding="utf-8")
            scripts = re.findall(
                r"<script[^>]*>(.*?)</script>",
                html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            for index, script in enumerate(scripts):
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".js", encoding="utf-8", delete=False
                ) as handle:
                    handle.write(script)
                    path = handle.name
                try:
                    result = subprocess.run(
                        [node, "--check", path],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        f"{relative} script #{index + 1} has invalid JavaScript:\n{result.stderr}",
                    )
                finally:
                    pathlib.Path(path).unlink(missing_ok=True)

    def test_worker_python_syntax_parses(self):
        worker = ROOT / "src" / "worker.py"
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(worker)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"src/worker.py has invalid Python syntax:\n{result.stderr}",
        )

    def test_admin_layout_has_no_duplicate_section_close(self):
        html = (ROOT / "public" / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("</section>\n</section>\n</main>", html)
        self.assertIn('class="searchbox"', html)
        self.assertIn('id="search"', html)

    def test_private_page_javascript_parses(self):
        node = shutil.which("node")
        self.assertIsNotNone(
            node, "Node.js is required to validate private-page JavaScript"
        )
        for relative in (
            "public/admin/index.html",
            "public/provider.html",
            "public/track.html",
            "public/my-requests.html",
        ):
            html = (ROOT / relative).read_text(encoding="utf-8")
            scripts = re.findall(
                r"<script[^>]*>(.*?)</script>",
                html,
                flags=re.IGNORECASE | re.DOTALL,
            )
            self.assertTrue(scripts, f"{relative} must contain JavaScript")
            for index, script in enumerate(scripts):
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".js", encoding="utf-8", delete=False
                ) as handle:
                    handle.write(script)
                    path = handle.name
                try:
                    result = subprocess.run(
                        [node, "--check", path],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(
                        result.returncode,
                        0,
                        f"{relative} script #{index + 1} has invalid JavaScript:\n{result.stderr}",
                    )
                finally:
                    pathlib.Path(path).unlink(missing_ok=True)

    def test_provider_portal_uses_bearer_token_without_exposing_token_storage(self):
        worker = (ROOT / "src/worker.py").read_text(encoding="utf-8")
        portal = (ROOT / "public/provider.html").read_text(encoding="utf-8")
        admin = (ROOT / "public/admin/index.html").read_text(encoding="utf-8")
        self.assertIn("hashlib.sha256", worker)
        self.assertIn(
            "x_provider_token: str | None = Header(default=None)",
            worker,
        )
        self.assertIn("provider_token_hash(x_provider_token)", worker)
        self.assertIn("/api/provider/portal", portal)
        self.assertIn("/api/provider/quotes/", portal)
        self.assertNotIn("localStorage", portal)
        self.assertNotIn("portal_token_hash", admin)
        self.assertIn('"/api/providers/"+id+"/portal-link"', admin)

    def test_festival_content_hubs_are_present(self):
        data = (ROOT / "public" / "festival-data.js").read_text(encoding="utf-8")
        festivals = (ROOT / "public" / "festivals.html").read_text(encoding="utf-8")
        quotes = (ROOT / "public" / "quotes.html").read_text(encoding="utf-8")
        guide = (ROOT / "public" / "guide.html").read_text(encoding="utf-8")
        home = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        for name in ["Diwali", "Durga Puja", "Chhath", "Navratri", "Dussehra"]:
            self.assertIn(name, data)
        for feature in ["wishes", "shayari", "status", "captions", "messages"]:
            self.assertIn(feature, data)
        for feature in ["WhatsApp", "Instagram", "Download PNG", "Copy text"]:
            self.assertIn(feature, quotes)
        for feature in ["Puja Vidhi", "Muhurat", "Mantra", "Traditions", "Samagri"]:
            self.assertIn(feature, guide)
        self.assertIn('class="ritual"', guide)
        self.assertIn('id="festivalSelect"', guide)
        self.assertIn('id="style"', quotes)
        self.assertIn('id="next"', quotes)
        for feature in ["wishes", "shayari", "status", "captions", "messages"]:
            self.assertIn(feature+':[', data)
        self.assertGreaterEqual(data.count('May '), 10)
        self.assertIn('setInterval(next,9000)', quotes)
        self.assertIn('DRAFT_KEY', home)
        self.assertIn('restoreDraft()', home)
        self.assertIn('updateRequestUX()', home)
        self.assertIn('No obligation to book', home)
        self.assertIn('requestSummary', home)
        self.assertIn('whySend', home)
        for path in ["/festivals.html", "/quotes.html", "/guide.html"]:
            self.assertIn(path, home)

    def test_payment_collection_is_removed_from_validation_flow(self):
        worker = (ROOT / "src" / "worker.py").read_text(encoding="utf-8")
        admin = (ROOT / "public" / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("/api/quotes/{quote_id}/payment", worker)
        self.assertNotIn("/api/payments/{payment_id}/status", worker)
        self.assertNotIn("/api/webhooks/razorpay", worker)
        self.assertNotIn("Razorpay", worker)
        self.assertNotIn("paymentsTab", admin)
        self.assertNotIn("Collect ₹", admin)
        self.assertNotIn("createPayment(", admin)
        self.assertNotIn("loadPayments(", admin)

    def test_provider_migration_is_explicit(self):
        migration = (
            ROOT / "migrations/0002_provider_portal.sql"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "ALTER TABLE providers ADD COLUMN portal_token_hash TEXT;",
            migration,
        )
        self.assertIn(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_providers_portal_token_hash",
            migration,
        )

    def test_worker_does_not_contain_hardcoded_local_admin_secret(self):
        worker = (ROOT / "src/worker.py").read_text(encoding="utf-8")
        self.assertNotIn("festivalquote-local-admin-2026", worker)
        self.assertIn(
            'getattr(request.scope["env"], "ADMIN_KEY", "")',
            worker,
        )

    def test_private_tracker_returns_editable_fields(self):
        worker = (ROOT / "src/worker.py").read_text(encoding="utf-8")
        self.assertIn(
            "SELECT id,name,phone,email,city,festival,service,event_date,budget,details,status,created_at",
            worker,
        )
        self.assertIn(
            '"X-Request-Token"',
            (ROOT / "public/track.html").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
