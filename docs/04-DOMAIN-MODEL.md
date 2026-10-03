# 04 — Modèle de domaine

```
User ─┬─ Profile / UserSetting
      ├─ ChallengeCategory ─┐
      ├─ Challenge ─────────┴─┬─ TrackingField (n)
      │                       ├─ Goal (versions)  ── metric → TrackingField | ∅ (séances)
      │                       ├─ Schedule (versions)
      │                       ├─ ChallengePause (n)
      │                       ├─ Milestone (n)
      │                       └─ ChallengeEntry (n) ── EntryFieldValue (n) ── TrackingField
      ├─ RestDay (challenge ou global)
      ├─ ActivityCategory
      ├─ RecurringRule ──► PlannedActivity (occurrences)
      ├─ PlannedActivity ── challenge? ── entries (après confirmation)
      ├─ PlannerTemplate ── PlannerTemplateItem
      ├─ JournalEntry / WeeklyReview
      ├─ MonthlyReport ── ReportChallengeSnapshot
      ├─ Notification
      └─ AuditLog
```

## Concepts

- **Challenge** : ce que l'utilisateur veut faire régulièrement. Statuts : `active`, `paused`, `completed`, `archived`.
- **TrackingField** : une donnée saisie à chaque entrée (`boolean`, `integer`, `decimal`, `duration`, `time`, `text`, `select`).
- **Goal** : *quoi* et *combien* — `metric` (champ mesuré ou aucun = séances), `period` (`daily`, `weekly`, `monthly`, `total`),
  `aggregation` (`sum` ou `count`), `target`, `min_per_entry`. Versionné.
- **Schedule** : *quels jours* sont actifs — `daily`, `weekdays` (jours choisis), `interval` (tous les N jours). Versionné.
- **ChallengeEntry** : un résultat réel à une date, avec plusieurs valeurs typées.
- **RestDay** : jour de repos prévu (pour un défi ou pour tous).
- **ChallengePause** : période exclue de l'évaluation.
- **PlannedActivity** : un créneau planifié (date, début, fin, catégorie, priorité, statut, défi lié…).
- **RecurringRule** : règle de récurrence ; les occurrences sont des `PlannedActivity` créées à la demande.
- **MonthlyReport** : instantané figé d'un mois.

## Exemples (données, pas de code)

| Défi | Champs | Objectif | Planning |
|---|---|---|---|
| Sport | Type (liste), Durée | ∅ / `count` / 1 / `daily` | lun–sam |
| Coran | Pages (entier), Sourate (texte) | Pages / `sum` / 2 / `daily` | tous les jours |
| Apprentissage | Durée, Sujet | Durée / `sum` / 120 / `daily` | lun–ven |
| Fajr | Fait (booléen), Réveil (heure) | Fait / `count` / 1 / `daily` | tous les jours |
| Course | Durée, Distance | Durée / `count` / 3 / `weekly`, min 30 | tous les jours |
| Lecture | Pages | Pages / `sum` / 20 / `weekly` | tous les jours |
| Eau | Eau (décimal, L) | Eau / `sum` / 2 / `daily` | tous les jours |
