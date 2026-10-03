# 14 — Feuille de route

## Livré

MVP complet (cf. 01) + éléments V2 déjà présents : bilan hebdomadaire, journal, modèles de défis et de journée,
paliers, statistiques avancées, notifications in-app (architecture + commande de rappels), manifeste PWA.

## V2 — prochaines étapes

- **PWA** : service worker (cache hors ligne de la vue Aujourd'hui, file d'attente des entrées hors ligne), icônes PNG, installation.
- **Notifications** : push web / e-mail planifiés par Celery ou cron, rappel de défi à heure fixe, objectif du jour.
- **Planner** : vue mois, glisser depuis une liste de tâches, activités sur deux jours (nuit), détection de conflits à l'application d'un modèle.
- **Défis** : objectifs sur un champ « heure » (ex. réveil avant 05:30), plusieurs objectifs par défi, objectifs décroissants (réduire), tags.
- **Analytique** : corrélations (sommeil ↔ apprentissage), prévisions de fin, comparaison mois/mois.
- **Arabe + RTL** : ajouter `("ar", "العربية")` à `LANGUAGES`, `dir="rtl"` piloté par la langue (Tailwind : variantes `rtl:`), traduire `locale/ar`.
- Import CSV, export iCal du planner.

## V3 — social

Groupes, amis, défis partagés, défis publics, modèles publics (le modèle `ChallengeTemplate` possède déjà `owner` et `is_public`).

## V4 — IA

Assistant de création en langage naturel (« Je veux apprendre Python 2 heures par jour pendant 30 jours » →
payload de l'assistant **soumis à confirmation**) : la sortie de l'IA alimenterait exactement le payload de
`POST /api/challenges/`, déjà validé côté serveur. Insights hebdomadaires générés à partir des résultats du moteur.

## Gamification (optionnelle)

Points/badges calculables à partir des séries et paliers existants, sans transformer l'application en jeu.
