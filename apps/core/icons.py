"""Icon whitelist shared with the frontend sprite builder (frontend/icons.json)."""
import json
from functools import lru_cache

from django.conf import settings


@lru_cache(maxsize=1)
def _icons() -> dict:
    with open(settings.BASE_DIR / "frontend" / "icons.json", encoding="utf-8") as fh:
        return json.load(fh)


def picker_icons() -> list[str]:
    return list(_icons()["picker"])


def all_icons() -> set[str]:
    data = _icons()
    return set(data["ui"]) | set(data["picker"])
