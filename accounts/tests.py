import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from clients.models import Client
from core.models import FirmSettings
from matters.models import Matter
from trust.models import TrustTransaction

from . import totp
from .models import TwoFactorDevice

User = get_user_model()
PASSWORD = "correct-horse-battery"


def make_user(username, role, **extra):
    user = User.objects.create_user(username, f"{username}@firm.test", PASSWORD, first_name=username.title(),
                                    last_name="Test", **extra)
    user.profile.role = role
    user.profile.save()
    return user


class TotpTests(TestCase):
    def test_rfc6238_vector(self):
        # RFC 6238 appendix B, SHA-1 secret "12345678901234567890", T=59 -> 94287082 (last 6 digits).
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(totp.verify(secret, "287082", now=59, window=0), 1)
        self.assertIsNone(totp.verify(secret, "287082", last_used_step=1, now=59, window=0))  # no replay
        self.assertIsNone(totp.verify(secret, "000000", now=59))


class SetupWizardTests(TestCase):
    def test_first_run_creates_partner_and_firm(self):
        self.assertRedirects(self.client.get("/login/"), "/setup/")
        resp = self.client.post("/setup/", {
            "firm_name": "Moyo & Co", "currency_symbol": "US$", "vat_rate": "15", "first_name": "Ann",
            "last_name": "Moyo", "email": "ann@moyo.test", "username": "ann", "password": PASSWORD,
            "password_confirm": PASSWORD,
        })
        self.assertRedirects(resp, reverse("firm_settings"))
        user = User.objects.get()
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.profile.role, "partner")
        self.assertEqual(FirmSettings.load().name, "Moyo & Co")
        # Setup can never run again.
        self.client.logout()
        self.assertRedirects(self.client.get("/setup/"), "/login/")


@override_settings(LOGIN_MAX_FAILURES=3)
class LoginSecurityTests(TestCase):
    def setUp(self):
        self.user = make_user("ann", "partner")

    def login(self, password=PASSWORD):
        return self.client.post("/login/", {"username": "ann", "password": password})

    def test_lockout_after_repeated_failures(self):
        for _ in range(3):
            self.login("wrong")
        resp = self.login()  # correct password, but locked
        self.assertContains(resp, "Too many failed sign-in attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_clears_failures(self):
        self.login("wrong")
        self.assertRedirects(self.login(), "/", fetch_redirect_response=False)

    def test_two_factor_flow(self):
        device = TwoFactorDevice.objects.create(user=self.user, secret=totp.new_secret(), confirmed=True)
        self.assertRedirects(self.login(), reverse("login_2fa"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.post(reverse("login_2fa"), {"code": "000000"}), "not valid")
        code = totp._code(device.secret, totp.current_step())
        self.assertRedirects(self.client.post(reverse("login_2fa"), {"code": code}), "/",
                             fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_firm_can_require_two_factor(self):
        firm = FirmSettings.load()
        firm.require_two_factor = True
        firm.save()
        self.client.force_login(self.user)
        resp = self.client.get("/matters/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/account/2fa/"))
        self.assertEqual(self.client.get("/account/2fa/").status_code, 200)

    def test_two_factor_setup_confirms_device(self):
        self.client.force_login(self.user)
        self.client.get("/account/2fa/")
        device = TwoFactorDevice.objects.get(user=self.user)
        self.client.post("/account/2fa/", {"code": totp._code(device.secret, totp.current_step())})
        device.refresh_from_db()
        self.assertTrue(device.confirmed)

    def test_password_reset_email(self):
        self.client.post("/password-reset/", {"email": "ann@firm.test"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/reset/", mail.outbox[0].body)


class PermissionTests(TestCase):
    def setUp(self):
        self.partner = make_user("pat", "partner")
        self.secretary = make_user("sue", "secretary")
        self.bookkeeper = make_user("bob", "bookkeeper")
        client = Client.objects.create(name="Acme")
        self.matter = Matter.objects.create(client=client, description="M", responsible=self.partner,
                                            date_opened=date(2026, 10, 1))

    def post_receipt(self):
        return self.client.post(reverse("trust_receipt"), {
            "matter": self.matter.pk, "date": "2026-10-01", "amount": "100", "party": "X", "description": "Y",
        })

    def test_secretary_cannot_touch_trust_or_settings_or_users(self):
        self.client.force_login(self.secretary)
        self.assertEqual(self.post_receipt().status_code, 403)
        self.assertEqual(self.client.get(reverse("trust_cashbook")).status_code, 403)
        self.assertEqual(self.client.get(reverse("firm_settings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)
        self.assertFalse(TrustTransaction.objects.exists())
        # ...but can work on matters.
        self.assertEqual(self.client.get(self.matter.get_absolute_url()).status_code, 200)

    def test_bookkeeper_can_post_trust(self):
        self.client.force_login(self.bookkeeper)
        self.post_receipt()
        self.assertEqual(self.matter.trust_balance, Decimal("100"))

    def test_partner_manages_users(self):
        self.client.force_login(self.partner)
        resp = self.client.post(reverse("user_create"), {
            "username": "new", "first_name": "New", "last_name": "Person", "email": "new@firm.test",
            "role": "candidate", "password": PASSWORD,
        })
        self.assertRedirects(resp, reverse("user_list"))
        new = User.objects.get(username="new")
        self.assertEqual(new.profile.role, "candidate")
        self.assertTrue(new.check_password(PASSWORD))

    def test_partner_cannot_deactivate_self(self):
        self.client.force_login(self.partner)
        self.client.post(reverse("user_edit", args=[self.partner.pk]), {
            "username": "pat", "first_name": "Pat", "last_name": "Test", "email": "pat@firm.test",
            "role": "partner",
        })
        self.partner.refresh_from_db()
        self.assertTrue(self.partner.is_active)


TEST_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class DocumentSecurityTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = make_user("ann", "associate")
        client = Client.objects.create(name="Acme")
        self.matter = Matter.objects.create(client=client, description="M", responsible=self.user,
                                            date_opened=date(2026, 10, 1))
        self.client.force_login(self.user)

    def upload(self, name, content=b"%PDF-1.4 test"):
        return self.client.post(reverse("document_upload", args=[self.matter.pk]),
                                {"title": "Doc", "file": SimpleUploadedFile(name, content)})

    def test_upload_and_private_download(self):
        self.upload("contract.pdf")
        doc = self.matter.documents.get()
        resp = self.client.get(reverse("document_download", args=[doc.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"%PDF-1.4 test")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("document_download", args=[doc.pk])).status_code, 302)

    def test_dangerous_file_types_rejected(self):
        self.upload("evil.exe")
        self.upload("page.html")
        self.assertFalse(self.matter.documents.exists())


class HealthAndHeadersTests(TestCase):
    def test_health_is_public(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_security_headers(self):
        user = make_user("ann", "partner")
        self.client.force_login(user)
        resp = self.client.get("/")
        self.assertIn("default-src 'self'", resp["Content-Security-Policy"])
        self.assertEqual(resp["Cache-Control"], "no-store")
