# 08 — API REST

Base : `/api/`. JSON uniquement. Authentification : **session** (navigateur, en-tête `X-CSRFToken` obligatoire
pour les écritures) ou **JWT** (`Authorization: Bearer <access>`). Toutes les routes exigent un utilisateur connecté,
sauf `auth/register`, `auth/login`, `auth/token*`.

Erreurs uniformes : `{"detail": "message lisible", "errors": {"champ": ["…"]}}` — 400 validation, 404 introuvable
(**y compris pour les objets d'un autre utilisateur**), 409 conflit, 429 limite de débit, 500 message générique.
Listes paginées : `{"count", "next", "previous", "results"}` (`?page=`, `?page_size=` ≤ 500).

## Authentification — `/api/auth/`

| Méthode | Route | Description |
|---|---|---|
| POST | `register/` | `{username, email, password, first_name?, timezone?}` |
| POST | `login/` | `{username (ou e-mail), password}` — limité |
| POST | `logout/` | |
| GET / PATCH | `me/` | profil complet (`profile`, `settings` imbriqués) |
| POST | `password/` | `{current_password, new_password}` |
| POST | `token/`, `token/refresh/` | JWT |

## Défis

| Méthode | Route | Description |
|---|---|---|
| GET / POST | `challenges/` | liste (`?status=active,paused`, `?q=`) avec `progress` ; création = payload de l'assistant |
| GET / PATCH / DELETE | `challenges/{id}/` | |
| POST | `challenges/{id}/status/` | `{status}` |
| PUT | `challenges/{id}/goal/` | `{metric, period, aggregation, target, min_per_entry, effective_from?}` (versionné) |
| PUT | `challenges/{id}/schedule/` | `{frequency, weekdays, interval_days, effective_from?}` |
| GET | `challenges/{id}/progress/` | résultat complet du moteur (séries jour/bucket, statistiques, paliers) |
| GET | `challenges/{id}/statistics/` | `?start=&end=` fenêtre optionnelle |
| POST | `challenges/{id}/fields/` · PATCH/DELETE `fields/{fid}/` | champs |
| POST / DELETE | `challenges/{id}/milestones/` | paliers |
| POST | `challenges/{id}/rest-day/` | bascule un jour de repos `{date}` |
| POST | `challenges/{id}/duplicate/` | |
| GET / POST | `challenges/{id}/entries/` | entrées du défi |
| CRUD | `challenge-categories/` | |
| GET | `challenge-templates/` | modèles |
| GET / POST | `rest-days/` | jours de repos globaux (POST = bascule) |

Exemple de création :

```json
{
  "name": "Lire 20 pages", "start_date": "2026-10-01", "end_date": "2026-10-30",
  "fields": [{"ref": "p", "label": "Pages", "field_type": "integer", "unit": "pages"}],
  "goal": {"metric": "p", "period": "daily", "aggregation": "sum", "target": 20},
  "schedule": {"frequency": "daily"}
}
```

## Entrées — `entries/`

CRUD ; `?challenge=&start=&end=`. Création : `{challenge, date, values: {key|id: valeur}, note?, planned_activity?}`.

## Planner

| Méthode | Route | Description |
|---|---|---|
| GET | `planner/?date=` · `planner/today/` · `planner/week/?start=` | jour / aujourd'hui (+ `next`) / semaine (occurrences matérialisées) |
| CRUD | `planner/activities/` | `?start=&end=&status=&challenge=` ; les réponses incluent `overlaps` |
| POST | `planner/activities/{id}/move/` · `duplicate/` · `status/` · `reschedule/` | `status/` renvoie `entry_suggestion` si l'activité est liée à un défi |
| CRUD | `planner/rules/` | routines récurrentes |
| CRUD | `planner/templates/` · POST `{id}/apply/` · POST `from-day/` | modèles de journée |
| CRUD | `planner/categories/` | |

## Analyse, journal, rapports, notifications

| Méthode | Route |
|---|---|
| GET | `dashboard/` · `calendar/?month=YYYY-MM` · `calendar/day/?date=` |
| CRUD | `journal/` (`?start=&end=&challenge=&q=`) · `journal/weekly-reviews/` (upsert par semaine) |
| GET / DELETE | `reports/` · `reports/{id}/` · GET `reports/{id}/pdf/` · POST `reports/monthly/` `{year, month}` |
| GET / PATCH / DELETE | `notifications/` · POST `notifications/read-all/` |

Exports (pages web) : `/reports/export/?format=xlsx` · `?format=csv&kind=entries|statistics[&challenge=]`.
