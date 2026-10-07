"""Database-backed file storage for hosts without a persistent disk.

Enable with `MEDIA_STORAGE=db`. Files are served by `apps.core.views.media_file`
under MEDIA_URL, exactly like files on disk, so templates and models don't change.
"""
from __future__ import annotations

import mimetypes

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.utils.encoding import filepath_to_uri

MAX_BYTES = 5 * 1024 * 1024


def _norm(name: str) -> str:
    """Storage names always use "/" (Django builds candidates with os.path, i.e. "\\" on Windows)."""
    return str(name).replace("\\", "/")


@deconstructible
class DatabaseStorage(Storage):
    def _model(self):
        from .models import StoredFile  # apps are loaded lazily

        return StoredFile

    def _open(self, name, mode="rb"):
        name = _norm(name)
        obj = self._model().objects.filter(name=name).only("content").first()
        if obj is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(obj.content), name=name)

    def get_available_name(self, name, max_length=None):
        return _norm(super().get_available_name(_norm(name), max_length))

    def _save(self, name, content):
        name = _norm(name)
        if hasattr(content, "seek"):
            content.seek(0)
        data = content.read()
        if len(data) > MAX_BYTES:
            raise ValueError("File too large for database storage")
        content_type = getattr(content, "content_type", None) or mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._model().objects.create(name=name, content=data, size=len(data), content_type=content_type)
        return name

    def exists(self, name):
        return self._model().objects.filter(name=_norm(name)).exists()

    def delete(self, name):
        self._model().objects.filter(name=_norm(name)).delete()

    def size(self, name):
        obj = self._model().objects.filter(name=_norm(name)).only("size").first()
        if obj is None:
            raise FileNotFoundError(name)
        return obj.size

    def url(self, name):
        from django.conf import settings

        return settings.MEDIA_URL + filepath_to_uri(_norm(name))

    def listdir(self, path):
        prefix = path.rstrip("/") + "/" if path else ""
        names = self._model().objects.filter(name__startswith=prefix).values_list("name", flat=True)
        dirs, files = set(), []
        for n in names:
            rest = n[len(prefix):]
            if "/" in rest:
                dirs.add(rest.split("/", 1)[0])
            else:
                files.append(rest)
        return sorted(dirs), sorted(files)
