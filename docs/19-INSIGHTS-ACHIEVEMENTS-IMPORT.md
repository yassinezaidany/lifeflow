# 19 — Objectifs-limites, constats, succès et import CSV

## Objectifs-limites (« au plus »)

Un objectif a une **direction** : `at_least` (atteindre, défaut) ou `at_most` (rester sous une limite).
Exemples : temps d'écran ≤ 2 h / jour, dépenses ≤ 50 € / semaine, cigarettes ≤ 3 / jour (modèle intégré
« Limite de temps d'écran »).

Règles du moteur (`Bucket.is_limit`, voir [07-PROGRESS-ENGINE.md](07-PROGRESS-ENGINE.md)) :

- une période est **réussie** si son total reste ≤ la cible ; un jour sans entrée compte pour 0 (donc réussi) ;
- une période n'est **acquise qu'une fois terminée** (on peut encore dépasser jusqu'au bout) ; un dépassement compte
  **immédiatement** comme échec ;
- `progress` = taux de périodes tenues ; `gap` = budget disponible − consommé (positif = sous la limite) ;
  le statut passe à « En avance » sous le budget, « En retard » en cas de dépassement ;
- la vue du jour affiche `within` / `over` au lieu de « fait » ; les séries comptent les périodes tenues d'affilée.

Validation : une limite exige une métrique numérique, une durée ou des séances comptées (pas un champ fait/non fait).
Tests : `tests/test_limit_goals.py`.

## Constats automatiques (`apps/analytics/services/insights.py`)

Règles simples et explicables, calculées à chaque affichage à partir des résultats du moteur — rien n'est stocké,
rien ne quitte le serveur. Les 3 plus prioritaires s'affichent sur le tableau de bord, jusqu'à 6 sur la page Statistiques.

| Constat | Déclencheur | Action proposée |
|---|---|---|
| Limite dépassée aujourd'hui | défi-limite au-dessus du budget du jour | ouvrir le défi |
| Série en danger | série quotidienne ≥ 3 et rien d'enregistré aujourd'hui | enregistrer |
| Bon retour | rien d'enregistré depuis ≥ 3 jours alors qu'un défi est actif | page Aujourd'hui |
| À surveiller | défi le plus en retard (écart relatif) | **planifier une séance** dans le planner |
| Suivi du planning en baisse / en hausse | taux de réalisation 7 derniers jours vs 7 précédents (±15 points, ≥ 3 activités) | planner |
| Étape en vue | palier atteint à ≥ 80 % | ouvrir le défi |
| En avance | défi « En avance » | — |
| Votre meilleur jour | ≥ 10 entrées sur 8 semaines et un jour de semaine ≥ 1,5 × la moyenne | — |

## Succès / badges (`apps/analytics/services/achievements.py`)

15 badges en 5 groupes (régularité, séries, défis, planner, réflexion), page `/analytics/achievements/`.
Ils sont **calculés à la volée** : un badge existe tant que les données qui le justifient existent (supprimer des entrées
peut le retirer), et **planifier ne rapporte rien** — seules les activités confirmées (faites / partielles) comptent.
Chaque badge non obtenu affiche sa progression (ex. 219 / 250).

## Import CSV (`apps/reports/imports.py`)

Rapports → « Importer des saisies (CSV) » (`/reports/import/`). Format = celui de l'export :

```
Challenge,Date,<libellé ou clé de champ>…,Note[,Source]
```

- le défi doit exister (reconnu par son nom, sans tenir compte de la casse) ; les colonnes sont associées aux champs
  par libellé ou clé, les colonnes inconnues sont ignorées ;
- séparateur `,` `;` ou tabulation détecté automatiquement ; UTF-8 (avec ou sans BOM), sinon cp1252 / latin-1 ;
- **chaque ligne passe par la validation normale** des entrées (types, bornes, champs obligatoires, dates dans la période
  du défi et pas dans le futur) ; les erreurs sont rapportées ligne par ligne, les lignes valides sont importées ;
- les lignes **identiques** à une entrée existante (défi, date, valeurs, note) sont ignorées : réimporter un export
  ne crée aucun doublon ; la protection anti-formule de l'export (`'=…`) est annulée à l'import ;
- limites : 2 Mo et 5 000 lignes par fichier ; un utilisateur ne peut importer que dans ses propres défis.

Tests : `tests/test_import.py` (aller-retour export → import, erreurs, séparateur `;`, isolation, page).
