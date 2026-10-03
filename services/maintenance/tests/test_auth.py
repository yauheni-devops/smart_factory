"""The maintenance UI must work without a browser Basic-auth dialog."""

import base64
import os
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient


class MaintenanceAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{(Path(cls.temp_dir.name) / 'maintenance.db').as_posix()}"
        os.environ["PTO_ACCESS_USERNAME"] = "pto"
        os.environ["PTO_ACCESS_PASSWORD"] = "local-test-password"
        from app.main import app
        cls.app = app

    @classmethod
    def tearDownClass(cls):
        from app.db import engine
        engine.dispose()
        cls.temp_dir.cleanup()

    def test_login_cookie_and_logout(self):
        with TestClient(self.app) as browser:
            response = browser.get("/ui", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/login")
            self.assertNotIn("www-authenticate", response.headers)
            self.assertIn("Вход в систему", browser.get("/login?next=home").text)
            background = browser.get("/assets/login-background.webp")
            self.assertEqual(background.status_code, 200)
            self.assertEqual(background.headers["content-type"], "image/webp")

            response = browser.get("/api/equipment")
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("www-authenticate", response.headers)

            response = browser.post("/login", json={"username": "pto", "password": "wrong"})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("pto_session", browser.cookies)

            response = browser.post("/login", json={"username": "pto", "password": "local-test-password"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("httponly", response.headers["set-cookie"].lower())
            self.assertEqual(browser.get("/session").status_code, 204)
            response = browser.get("/login?next=home", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "http://localhost:8082/ui")
            self.assertEqual(browser.get("/ui").status_code, 200)
            self.assertEqual(browser.get("/api/equipment").status_code, 200)

            response = browser.post("/logout?next=home", follow_redirects=False)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/login?next=home")
            self.assertEqual(browser.get("/session").status_code, 401)
            self.assertEqual(browser.get("/api/equipment").status_code, 401)

    def test_explicit_basic_header_still_works_for_api_clients(self):
        value = base64.b64encode(b"pto:local-test-password").decode("ascii")
        with TestClient(self.app) as client:
            response = client.get("/api/equipment", headers={"Authorization": f"Basic {value}"})
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
