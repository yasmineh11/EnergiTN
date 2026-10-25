from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase


class SmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def login(self, email):
        self.client.post("/login/", {"username": email, "password": "demo1234"})

    def test_anonymous_is_redirected(self):
        self.assertEqual(self.client.get("/foyer/").status_code, 302)
        self.assertEqual(self.client.get("/api/forecasts/").status_code, 403)

    def test_foyer_sees_only_own_data(self):
        self.login("foyer@demo.tn")
        self.assertEqual(self.client.get("/foyer/").status_code, 200)
        self.assertEqual(self.client.get("/operateur/").status_code, 302)
        ids = {f["household_id"] for f in self.client.get("/api/forecasts/").json()["results"]}
        self.assertEqual(ids, {"H001"})
        self.assertEqual(self.client.get("/api/operator/overview/").status_code, 403)

    def test_analyste_sees_operator(self):
        self.login("analyste@demo.tn")
        self.assertEqual(self.client.get("/operateur/").status_code, 200)
        data = self.client.get("/api/operator/overview/").json()
        self.assertEqual(len(data["regions"]), 6)
        self.assertEqual(len(data["dates"]), 7)

    def test_admin_dashboard(self):
        self.login("admin@demo.tn")
        self.assertEqual(self.client.get("/gestion/").status_code, 200)
        r = self.client.post("/gestion/user/", {"email": "n@x.tn", "password": "abcdef", "role": "analyste"}, content_type="application/json")
        self.assertTrue(r.json()["ok"])
        r = self.client.post("/gestion/user/", {"id": 3, "role": "foyer", "active": True}, content_type="application/json")
        self.assertIn(r.status_code, (200, 400))

    def test_non_admin_blocked(self):
        self.login("analyste@demo.tn")
        self.assertEqual(self.client.get("/gestion/").status_code, 302)
        self.assertEqual(self.client.post("/gestion/action/", {"action": "seed"}, content_type="application/json").status_code, 403)
