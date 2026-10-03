# 12 — Rapports

## Génération

`apps/reports/services/monthly.generate_monthly_report(user, year, month)` :

1. sélectionne les défis ayant chevauché le mois ;
2. évalue chacun avec le moteur sur la **fenêtre du mois** (`as_of` = fin du mois si écoulé, sinon aujourd'hui → rapport *partiel*) ;
3. copie dans `ReportChallengeSnapshot` : nom, catégorie, couleur, description de l'objectif, unité, objectif du mois,
   réalisé, attendu, progression, écart, statut, taux de réussite, séries, moyenne, jours actifs, série journalière ;
4. calcule le résumé (nombre de défis, actifs, terminés, réussite moyenne, entrées, meilleure série) et la synthèse
   du planner (prévu, fait, partiel, manqué, taux, temps prévu/réalisé) ;
5. journalise (`REPORT_GENERATED`) et notifie (si activé).

## Immuabilité & versions

Un rapport est un **snapshot** : modifier/supprimer des entrées, renommer ou supprimer un défi ne le change pas
(la FK vers le défi passe à `NULL`, les valeurs restent). Régénérer un mois crée une **nouvelle version**
(`version` 2, 3…) ; les précédentes sont conservées dans l'historique.

## Formats

- **HTML** : `/reports/{id}/` (KPIs, carte par défi avec anneau et mini-série, planner).
- **PDF** : `/reports/{id}/pdf/` (`?inline=1` pour l'afficher) — `generators/pdf.py` (ReportLab) : en-tête, KPIs,
  bloc par défi (puce de statut, barre de progression, tableau Goal/Actual/Expected/Gap/Progress/Completion/Séries/Moyenne),
  section planner, pied de page paginé. Rendu à partir du snapshot ⇒ identique à chaque téléchargement.
- **Exports** : Excel (feuilles Statistiques + Entrées), CSV des entrées (global ou par défi), CSV des statistiques.
