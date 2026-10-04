# 16 — Langues et mise en page RTL

## Langues

Anglais (source), **français** et **arabe** — catalogues complets dans `locale/fr` et `locale/ar`.

- Choix : profil (`Profile.language`), activé à chaque requête par `UserPreferencesMiddleware` ; pour les visiteurs
  non connectés : en-tête `Accept-Language` ou sélecteur sur les pages de connexion (`/i18n/setlang/`).
- À l'inscription, la langue détectée devient celle du profil, et les catégories par défaut sont renommées dans cette langue
  (elles deviennent des données modifiables). Pour les comptes plus anciens, les noms par défaut sont traduits à l'affichage
  (filtre `trans_default`, sérialiseurs de catégories) ; un nom personnalisé n'est jamais modifié.
- Chaînes JavaScript : `apps/core/js_i18n.py`, injectées dans `lf-config`.
- Pluriels arabes : 6 formes (zéro, un, deux, 3–10, 11–99, autres).

### Mettre à jour les traductions (sans GNU gettext)

```bash
python manage.py i18n extract    # ajoute les nouvelles chaînes à locale/*/LC_MESSAGES/django.po
# … traduire les msgstr vides …
python manage.py i18n compile    # génère les .mo
```

## RTL

- `<html dir="rtl">` automatique pour l'arabe (`get_current_language_bidi`).
- Toutes les classes de direction physique ont été converties en **propriétés logiques** Tailwind (`ms-/me-`, `ps-/pe-`,
  `start-/end-`, `text-start/end`, `border-s/e`) : barre latérale à droite, menus, champs avec unité, toasts… se
  retournent sans duplication de styles. Les blocs du planner sont positionnés avec `inset-inline-start`.
- Les icônes directionnelles (chevrons, flèches, déconnexion) reçoivent la classe `rtl-flip` (miroir horizontal).
- Le planner et le calendrier se lisent de droite à gauche (lundi à droite, axe des heures à droite) ; les plages horaires
  suivent l'ordre de lecture RTL (début à droite).
- Typographie : Noto Sans Arabic (variable, auto-hébergée, chargée uniquement pour les glyphes arabes via `unicode-range`) ;
  pas d'espacement de lettres en arabe.
- Dates/heures : formats Django `ar` ; côté JS, locale `ar-u-nu-latn` (chiffres latins, cohérents avec le serveur).
- Graphiques : légendes et infobulles Chart.js en RTL.

## PDF

ReportLab n'a pas de moteur de mise en forme des écritures complexes : le générateur embarque **DejaVu Sans** (latin,
accents, arabe), met en forme les chaînes arabes (`arabic-reshaper` + `python-bidi`) et, si la langue est RTL, inverse
l'ordre des colonnes, des KPIs et aligne le texte à droite. Les noms de défis en arabe sont ainsi lisibles même dans un
rapport en français.
