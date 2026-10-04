# 14 — Feuille de route

## Livré

MVP complet (cf. 01) + éléments V2 déjà présents : bilan hebdomadaire, journal, modèles de défis et de journée,
paliers, statistiques avancées, notifications in-app (architecture + commande de rappels), manifeste PWA.

## Livré dans la deuxième itération

Activités de nuit · PWA installable avec pages et saisie hors ligne · Web Push + e-mails HTML + résumé du matin + rappels par défi + planificateur · arabe complet avec mise en page RTL et PDF arabe · assistant de création en langage naturel (Claude optionnel + analyseur FR/EN/AR) · objectifs horaires (« avant 05:30 ») · export iCal et flux d'abonnement.

## V2 — prochaines étapes (reste à faire)

- **Notifications** : file de tâches (Celery/RQ) si le volume d'utilisateurs l'exige.
- **Planner** : vue mois, glisser depuis une liste de tâches, détection de conflits à l'application d'un modèle.
- **Défis** : plusieurs objectifs par défi, objectifs décroissants (réduire), tags.
- **Analytique** : corrélations (sommeil ↔ apprentissage), prévisions de fin, comparaison mois/mois.
- Import CSV, synchronisation bidirectionnelle avec Google Agenda.

## V3 — social

Groupes, amis, défis partagés, défis publics, modèles publics (le modèle `ChallengeTemplate` possède déjà `owner` et `is_public`).

## V4 — IA

- ✅ **Livré** : assistant de création en langage naturel, toujours soumis à confirmation (voir [17-AI-ASSISTANT.md](17-AI-ASSISTANT.md)).
- À venir : insights hebdomadaires générés à partir des résultats du moteur (« tes séances de sport tombent souvent le
  mercredi : planifie-les le mardi ? »), suggestions de planning, résumé automatique du bilan hebdomadaire.

## Gamification (optionnelle)

Points/badges calculables à partir des séries et paliers existants, sans transformer l'application en jeu.
