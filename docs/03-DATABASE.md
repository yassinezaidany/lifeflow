# 03 — Base de données

MySQL 8 (`utf8mb4`, mode `STRICT_TRANS_TABLES`), Django ORM, `ATOMIC_REQUESTS=True` (chaque requête HTTP est une transaction).

## Tables principales

| Modèle | Clés / relations | Contraintes & index |
|---|---|---|
| `accounts.User` | — | e-mail unique (normalisé en minuscules) |
| `Profile` | 1–1 User | `planner_day_start < planner_day_end ≤ 24` |
| `UserSetting` | 1–1 User | — |
| `ChallengeCategory` | FK User | unique (user, name) |
| `Challenge` | FK User, FK Category (SET NULL), FK Template (SET NULL) | `end_date ≥ start_date` ; index (user, status), (user, start_date) |
| `TrackingField` | FK Challenge | unique (challenge, key) |
| `Goal` | FK Challenge, FK TrackingField `metric` (**RESTRICT**) | `target > 0`, `min_per_entry ≥ 0`, `effective_to ≥ effective_from` ; index (challenge, effective_from) |
| `Schedule` | FK Challenge | `interval_days ≥ 1`, plage effective ; index |
| `ChallengePause` | FK Challenge | `end_date ≥ start_date` |
| `RestDay` | FK User, FK Challenge nullable (= tous) | unique (user, challenge, date) ; index (user, date) |
| `Milestone` | FK Challenge | `target_value > 0` |
| `ChallengeTemplate` | FK User nullable (= système) | unique (owner, slug) |
| `ChallengeEntry` | FK User, FK Challenge, FK PlannedActivity (SET NULL) | index (challenge, date), (user, date) |
| `EntryFieldValue` | FK Entry, FK Field | unique (entry, field) ; colonnes typées `value_number/bool/time/text` |
| `ActivityCategory` | FK User | unique (user, name) |
| `RecurringRule` | FK User, Category, Challenge | fin > début (ou fin = 00:00 = minuit), `interval_days ≥ 1`, dates |
| `PlannedActivity` | FK User, Category, Challenge, RecurringRule (SET NULL), self `rescheduled_from` | fin > début / minuit ; **unique (recurring_rule, occurrence_date)** ; index (user, date), (user, status), (challenge, date) |
| `PlannerTemplate` / `Item` | FK User / FK Template | unique (user, name) ; plage horaire |
| `JournalEntry` | FK User, Challenge | humeur 1–5 ; index (user, date) |
| `WeeklyReview` | FK User | unique (user, week_start) ; note 1–5 |
| `MonthlyReport` | FK User | unique (user, year, month, version) ; mois 1–12 |
| `ReportChallengeSnapshot` | FK Report, FK Challenge (SET NULL) | valeurs copiées (snapshot) |
| `Notification` | FK User | unique (user, dedupe_key) — `NULL` autorisé plusieurs fois |
| `core.AuditLog` | FK User | index (user, -created_at) |

## Conventions

- Toutes les données privées portent une **FK `user`** directe (même quand elle est déductible d'un parent).
- Dates « métier » (`date`, `start_date`…) = dates **locales de l'utilisateur** ; horodatages (`created_at`…) en UTC.
- **Archivage logique** : les défis sont archivés plutôt que supprimés ; un champ utilisé est désactivé (`is_active=False`).
- Les durées sont stockées en **minutes** (`value_number`).
- Heure de fin `00:00` = « jusqu'à minuit » (les activités ne débordent pas sur le jour suivant ; une nuit se découpe en deux blocs).

## Migrations

`apps/*/migrations/`. La migration `challenges.0002_system_templates` crée les modèles de défis intégrés
(données, pas de code métier). Vérification : `python manage.py makemigrations --check`.
