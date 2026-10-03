# 02 — Architecture

## Vue générale

```
Navigateur ──► Django (monolithe modulaire)
                 ├── Pages HTML (templates + Tailwind + Alpine.js + Chart.js)
                 ├── API REST /api/ (DRF : session + CSRF pour le web, JWT pour un futur client mobile)
                 ├── Services métier (challenges, tracking, planner, analytics/progress, reports)
                 └── ORM ──► MySQL 8
```

### Pourquoi un monolithe Django plutôt que Django + Next.js ?

- une seule application, un seul serveur, un seul routage, une seule authentification ;
- rendu serveur rapide pour les pages de lecture (dashboard, défi, rapports) ;
- l'interactivité riche (planner glisser-déposer, assistant, modales) est apportée par **Alpine.js** qui consomme
  la même **API REST** que pourrait utiliser une future PWA ou application mobile ;
- aucune étape de build n'est nécessaire en production : le CSS Tailwind compilé et les librairies JS sont commités
  dans `static/` (Node ne sert qu'à recompiler le design).

## Organisation par domaines

| App | Responsabilité |
|---|---|
| `core` | `TimeStampedModel`, `OwnedModel`, `AuditLog`, utilitaires de dates/fuseaux, middleware (fuseau/langue, en-têtes de sécurité), gestion d'erreurs API, template tags du design system, commandes `seed_demo`, `i18n` |
| `accounts` | `User` (personnalisé), `Profile`, `UserSetting`, backend e-mail/nom d'utilisateur, rate limiting de connexion, onboarding |
| `challenges` | `Challenge`, `ChallengeCategory`, `TrackingField`, `Goal` et `Schedule` versionnés, `ChallengePause`, `RestDay`, `Milestone`, `ChallengeTemplate` + services |
| `tracking` | `ChallengeEntry`, `EntryFieldValue` + validation typée |
| `planner` | `PlannedActivity`, `RecurringRule`, `PlannerTemplate(Item)`, `ActivityCategory` + services (occurrences, déplacement, report, modèles, synthèses) |
| `analytics` | `services/progress/` (moteur de progression) et `services/overview.py` (statistiques multi-défis) |
| `dashboard` | read models : tableau de bord, aujourd'hui, calendrier, détail d'un jour, bilan hebdo |
| `journal` | `JournalEntry`, `WeeklyReview` |
| `reports` | `MonthlyReport`, `ReportChallengeSnapshot`, `services/monthly.py`, `generators/pdf.py`, `exports.py` |
| `notifications` | `Notification`, service `notify()`, commande `send_reminders` |

### Règles de dépendance

- Les **vues et l'API n'écrivent pas directement** les modèles métier complexes : elles appellent des services
  (`challenges.services`, `tracking.services`, `planner.services`, `reports.services`).
- **Toute logique de progression** vit dans `apps/analytics/services/progress/`. Tableaux de bord, rapports, calendrier,
  exports et API appellent `ProgressEngine` — rien n'est recalculé ailleurs.

## Frontend

- `templates/layouts/app.html` : barre latérale (desktop), barre supérieure, navigation mobile avec bouton + central,
  modales globales (enregistrer une progression, activité, note, confirmation, toasts).
- `static/js/app.js` : client API (CSRF, erreurs lisibles), toasts, confirmation, *soft refresh* (après une action,
  la zone `<main>` est rechargée sans recharger la page), thème, helpers Chart.js, composants Alpine globaux.
- `static/js/planner.js` : grille horaire jour/semaine, voies pour les chevauchements, glisser-déposer, redimensionnement.
- `static/js/challenges.js` : assistant de création et éditeur de paramètres.

## Choix techniques documentés

| Sujet | Choix | Raison |
|---|---|---|
| PDF | ReportLab | Python pur, rendu déterministe, pas de dépendance GTK (WeasyPrint) sous Windows |
| Récurrence | règle unique + occurrences matérialisées à la lecture | pas de duplication de règles ; chaque occurrence peut être modifiée/terminée individuellement |
| Versionnement | `effective_from / effective_to` sur `Goal` et `Schedule` | évaluer chaque jour avec la règle en vigueur ce jour-là |
| Isolation | FK `user` dénormalisée sur toutes les données privées + queryset filtré | contrôle d'appartenance en un filtre indexé, audit simple |
| i18n | gettext Django + commande `i18n` (polib) | fonctionne sans GNU gettext sous Windows |
| Icônes | sprite SVG Lucide généré au build | une requête mise en cache, aucun CDN (CSP stricte) |
| Cache | LocMem (rate limiting) | suffisant pour un processus ; Redis recommandé en multi-workers |
