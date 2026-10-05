# 14 — Feuille de route

## Livré

MVP complet (cf. 01) + éléments V2 déjà présents : bilan hebdomadaire, journal, modèles de défis et de journée,
paliers, statistiques avancées, notifications in-app (architecture + commande de rappels), manifeste PWA.

## Livré dans la deuxième itération

Activités de nuit · PWA installable avec pages et saisie hors ligne · Web Push + e-mails HTML + résumé du matin + rappels par défi + planificateur · arabe complet avec mise en page RTL et PDF arabe · assistant de création en langage naturel (Claude optionnel + analyseur FR/EN/AR) · objectifs horaires (« avant 05:30 ») · export iCal et flux d'abonnement.

## Livré dans la troisième itération (« prêt à l'emploi »)

- **Installation en une commande** : `setup.ps1` / `setup.sh`, lancement `start.ps1` / `start.sh` (dev ou prod),
  pile Docker complète (`docker compose --profile app`), commande de diagnostic `doctor` — voir [13-DEPLOYMENT.md](13-DEPLOYMENT.md).
- **Objectifs-limites** (« au plus ») : temps d'écran, dépenses, cigarettes… — voir [19](19-INSIGHTS-ACHIEVEMENTS-IMPORT.md).
- **V3 social** : amis, défis de groupe avec classement privé par conception, modèles communautaires — voir [18-SOCIAL.md](18-SOCIAL.md).
- **Constats automatiques** (règles explicables) sur le tableau de bord et les statistiques.
- **Succès / badges** calculés à la volée à partir des données réelles (aucune gamification artificielle).
- **Import CSV** de l'historique, compatible aller-retour avec l'export.
- Lien vers la vue mois depuis le planner, menu mobile pour toutes les pages secondaires,
  modèles intégrés traduits (FR / AR).

## Pistes pour la suite

- **Notifications** : file de tâches (Celery/RQ) et cache Redis si le volume d'utilisateurs l'exige.
- **Planner** : glisser depuis une liste de tâches, détection de conflits à l'application d'un modèle.
- **Défis** : plusieurs objectifs par défi, tags.
- **Analytique** : corrélations (sommeil ↔ apprentissage), prévision de date de fin, comparaison mois/mois.
- **Synchronisation** bidirectionnelle avec Google Agenda (l'export iCal / abonnement couvre déjà le sens LifeFlow → agenda).
- **IA** : résumé automatique du bilan hebdomadaire et suggestions de planning à partir des constats
  (toujours soumis à confirmation, comme l'assistant de création).
- **Application mobile** native : l'API REST (JWT) et la PWA en posent déjà les bases.
