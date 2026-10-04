"""Generate a VAPID key pair for Web Push.

    python manage.py generate_vapid_keys            # print the keys
    python manage.py generate_vapid_keys --write    # append them to .env (if not already set)
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.core.management.base import BaseCommand


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class Command(BaseCommand):
    help = "Generate VAPID keys for Web Push notifications."

    def add_arguments(self, parser):
        parser.add_argument("--write", action="store_true", help="Append to .env")

    def handle(self, *args, **opts):
        key = ec.generate_private_key(ec.SECP256R1())
        private = _b64(key.private_numbers().private_value.to_bytes(32, "big"))
        public = _b64(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        lines = f"VAPID_PUBLIC_KEY={public}\nVAPID_PRIVATE_KEY={private}\n"
        if opts["write"]:
            env_path = settings.BASE_DIR / ".env"
            existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
            if "VAPID_PRIVATE_KEY=" in existing and "VAPID_PRIVATE_KEY=\n" not in existing:
                self.stdout.write(self.style.WARNING(".env already contains VAPID keys — nothing changed."))
                return
            with env_path.open("a", encoding="utf-8") as fh:
                fh.write("\n# Web Push\n" + lines)
            self.stdout.write(self.style.SUCCESS("VAPID keys written to .env — restart the server."))
        else:
            self.stdout.write(lines)
