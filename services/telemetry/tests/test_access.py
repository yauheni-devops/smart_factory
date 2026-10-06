"""The shared login guards visitor pages without blocking sensor ingestion."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, EQUIPMENT_DOCUMENT_FILES


class AcceptedSessionClient:
    def __init__(self, *, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, *, headers):
        return SimpleNamespace(status_code=204 if headers.get("Cookie") == "pto_session=valid" else 401)


class VisitorAccessTests(unittest.TestCase):
    def test_pages_redirect_and_api_denies_without_login(self):
        with TestClient(app) as browser:
            for path in ("/ui", "/monitoring", "/production", "/alerts", "/documents", "/reports"):
                with self.subTest(path=path):
                    response = browser.get(path, follow_redirects=False)
                    self.assertEqual(response.status_code, 303)
                    self.assertEqual(response.headers["location"], "http://localhost:8086/login?next=home")
            for path in ("/ui/data", "/readings/latest", "/assets/factory-hero.png", "/assets/specprofstroy-logo.png", "/assets/cemezit-horse.webp", "/assets/sections.css", "/equipment-documents/kinco-fv100-user-manual-en.pdf"):
                with self.subTest(path=path):
                    self.assertEqual(browser.get(path).status_code, 401)

    def test_one_session_opens_all_pages(self):
        with patch("app.main.httpx.AsyncClient", AcceptedSessionClient):
            with TestClient(app, cookies={"pto_session": "valid"}) as browser:
                for path in ("/ui", "/monitoring", "/production", "/alerts", "/documents", "/reports"):
                    with self.subTest(path=path):
                        self.assertEqual(browser.get(path).status_code, 200)
                for path, media_type in (
                    ("/assets/factory-hero.png", "image/png"),
                    ("/assets/specprofstroy-logo.png", "image/png"),
                    ("/assets/cemezit-horse.webp", "image/webp"),
                ):
                    with self.subTest(path=path):
                        image = browser.get(path)
                        self.assertEqual(image.status_code, 200)
                        self.assertEqual(image.headers["content-type"], media_type)

    def test_document_library_requires_login_for_get_and_head(self):
        with TestClient(app) as browser:
            for filename in EQUIPMENT_DOCUMENT_FILES:
                with self.subTest(filename=filename):
                    path = f"/equipment-documents/{filename}"
                    self.assertEqual(browser.get(path).status_code, 401)
                    self.assertEqual(browser.head(path).status_code, 401)

    def test_document_view_download_and_range_after_login(self):
        with patch("app.main.httpx.AsyncClient", AcceptedSessionClient):
            with TestClient(app, cookies={"pto_session": "valid"}) as browser:
                page = browser.get("/documents")
                for filename in EQUIPMENT_DOCUMENT_FILES:
                    with self.subTest(filename=filename):
                        path = f"/equipment-documents/{filename}"
                        self.assertIn(path, page.text)
                        document = browser.get(path)
                        self.assertEqual(document.status_code, 200)
                        self.assertEqual(document.headers["content-type"], "application/pdf")
                        self.assertTrue(document.content.startswith(b"%PDF-"))
                        self.assertTrue(document.headers["content-disposition"].startswith("inline;"))
                        self.assertIn("no-store", document.headers["cache-control"])
                        download = browser.get(path, params={"download": "1"})
                        self.assertTrue(download.headers["content-disposition"].startswith("attachment;"))
                        self.assertEqual(download.content, document.content)
                        head = browser.head(path)
                        self.assertEqual(head.status_code, 200)
                        self.assertEqual(head.content, b"")
                        self.assertEqual(head.headers["content-length"], str(len(document.content)))
                        part = browser.get(path, headers={"Range": "bytes=0-7"})
                        self.assertEqual(part.status_code, 206)
                        self.assertEqual(part.content, document.content[:8])
                self.assertEqual(browser.get("/equipment-documents/not-published.pdf").status_code, 404)

    def test_sensor_ingestion_remains_available_to_simulator(self):
        with patch("app.main.get_site", return_value={"status": "active"}):
            with TestClient(app) as browser:
                response = browser.post(
                    "/readings",
                    json={"site_id": "workshop-dry-mix-1", "metric": "temp_c", "value": 22.0},
                )
                self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
