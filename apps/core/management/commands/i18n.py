"""Pure-Python i18n workflow (no GNU gettext binaries required, works on Windows).

    python manage.py i18n extract        # update locale/<lang>/LC_MESSAGES/django.po
    python manage.py i18n compile        # build .mo files from .po files

Extraction understands {% trans %}, {% blocktrans %} (incl. count/plural),
_() / gettext() / gettext_lazy() / gettext_noop() / N() / ngettext() in Python,
and the JS string catalogue (apps.core.js_i18n). Existing translations are kept.
If GNU gettext is installed, `makemessages` / `compilemessages` work as usual too.
"""
import re
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

TEMPLATE_TRANS = re.compile(r"""{%\s*trans(?:late)?\s+(["'])(.+?)\1(?:\s+as\s+\w+)?\s*%}""")
BLOCKTRANS = re.compile(r"{%\s*blocktrans(?:late)?\b(?P<args>[^%]*)%}(?P<body>.*?){%\s*endblocktrans(?:late)?\s*%}", re.S)
PY_CALL = re.compile(r"""\b(?:_|gettext|gettext_lazy|gettext_noop|N|pgettext)\(\s*(?P<q>"|')(?P<s>(?:\\.|(?!(?P=q)).)*)(?P=q)\s*[,)]""")
PY_NGETTEXT = re.compile(r"""\bngettext\(\s*(?P<q>"|')(?P<s>(?:\\.|(?!(?P=q)).)*)(?P=q)\s*,\s*(?P<q2>"|')(?P<p>(?:\\.|(?!(?P=q2)).)*)(?P=q2)""")
VAR = re.compile(r"{{\s*(\w+)\s*}}")
PLURAL_FORMS = {
    "fr": "nplurals=2; plural=(n > 1);",
    "ar": "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);",
}


def _blocktrans_ids(args: str, body: str):
    def conv(text):
        return " ".join(VAR.sub(lambda m: f"%({m.group(1)})s", text).split()) if "trimmed" in args else VAR.sub(lambda m: f"%({m.group(1)})s", text)
    args = args + " trimmed"  # our templates never rely on leading/trailing whitespace
    if "{% plural %}" in body:
        singular, plural = body.split("{% plural %}", 1)
        return conv(singular), conv(plural)
    return conv(body), None


class Command(BaseCommand):
    help = "Extract / compile translations without GNU gettext."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["extract", "compile"])

    def handle(self, action, **opts):
        locale_dir = Path(settings.LOCALE_PATHS[0])
        languages = [code for code, _ in settings.LANGUAGES if code != settings.LANGUAGE_CODE]
        if action == "extract":
            messages = self.collect()
            for lang in languages:
                self.update_po(locale_dir / lang / "LC_MESSAGES" / "django.po", messages, lang)
        else:
            for po_path in locale_dir.glob("*/LC_MESSAGES/django.po"):
                po = polib.pofile(str(po_path))
                po.save_as_mofile(str(po_path.with_suffix(".mo")))
                self.stdout.write(f"compiled {po_path.parent.parent.name}: {po.percent_translated()}% translated")

    def collect(self) -> dict:
        base = Path(settings.BASE_DIR)
        found: dict[tuple, str] = {}
        for path in list((base / "templates").rglob("*.html")) + list((base / "templates").rglob("*.txt")):
            text = path.read_text(encoding="utf-8")
            for m in TEMPLATE_TRANS.finditer(text):
                found.setdefault((m.group(2), None), str(path.relative_to(base)))
            for m in re.finditer(r"""\b_\((["'])(.+?)\1\)""", text):  # e.g. default:_("Note"), title=_("…")
                found.setdefault((m.group(2), None), str(path.relative_to(base)))
            for m in BLOCKTRANS.finditer(text):
                found.setdefault(_blocktrans_ids(m.group("args"), m.group("body")), str(path.relative_to(base)))
        for path in (base / "apps").rglob("*.py"):
            if "migrations" in path.parts or "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for m in PY_NGETTEXT.finditer(text):
                found.setdefault((m.group("s").encode().decode("unicode_escape"), m.group("p").encode().decode("unicode_escape")), str(path.relative_to(base)))
            for m in PY_CALL.finditer(text):
                s = m.group("s")
                if s:
                    found.setdefault((bytes(s, "utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8"), None), str(path.relative_to(base)))
        return found

    def update_po(self, path: Path, messages: dict, lang: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        po = polib.pofile(str(path)) if path.exists() else polib.POFile()
        po.metadata = {
            "Project-Id-Version": "LifeFlow", "Language": lang, "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8", "Content-Transfer-Encoding": "8bit",
            "Plural-Forms": PLURAL_FORMS.get(lang, "nplurals=2; plural=(n != 1);"),
        }
        existing = {(e.msgid, e.msgid_plural or None): e for e in po}
        added = 0
        for (msgid, plural), occ in sorted(messages.items()):
            if (msgid, plural) in existing:
                continue
            entry = polib.POEntry(msgid=msgid, msgstr="", occurrences=[(occ, "")])
            if plural:
                entry.msgid_plural = plural
                entry.msgstr_plural = {i: "" for i in range(6 if lang == "ar" else 2)}
            po.append(entry)
            added += 1
        keys = set(messages)
        for e in list(po):
            e.obsolete = (e.msgid, e.msgid_plural or None) not in keys
        po.save(str(path))
        self.stdout.write(f"{path}: {len(po)} entries ({added} new), {po.percent_translated()}% translated")
        if not path.exists():
            raise CommandError("Failed to write catalogue")
