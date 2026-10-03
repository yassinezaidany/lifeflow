# 07 — Moteur de progression

Code : `apps/analytics/services/progress/` — `engine.py` (algorithme), `goals.py` (périodes, mesure des entrées,
descriptions), `schedules.py` (classification des jours), `streaks.py`, `statistics.py`, `status.py`.

```python
engine = ProgressEngine(user)                       # « aujourd'hui » dans le fuseau de l'utilisateur
result = engine.evaluate(challenge, include_series=True)
results = engine.evaluate_many(challenges)          # 2–3 requêtes au total, quel que soit le nombre de défis
ProgressEngine(user, as_of=date(2026, 9, 30), day_closed=True).evaluate(c, window=(date(2026, 9, 1), date(2026, 9, 30)))
```

## 1. Classification des jours

Pour chaque jour de `[start_date, fin]` : `OUTSIDE` (hors période), `PAUSED` (dans une pause), `REST` (non planifié
par la version du planning en vigueur, ou jour de repos explicite), sinon `ACTIVE` (jour éligible).
Fin effective = min(`end_date`, `closed_on`).

## 2. Buckets (périodes d'évaluation)

Chaque jour appartient à un bucket défini par **la version d'objectif en vigueur ce jour-là** et sa période :
jour (`daily`), semaine civile (selon le début de semaine du profil), mois civil.

**Cible d'un bucket**
- sans jour éligible → 0 ;
- `daily` → `target` ;
- `weekly` / `monthly` → `target × jours_non_en_pause_dans_la_période / jours_civils_de_la_période`
  (proratisation des semaines/mois partiels : début/fin du défi, pauses, changement de version).
  Les jours de repos ne réduisent **pas** une cible hebdomadaire : ils indiquent seulement *quand* le travail est attendu.

**Part quotidienne** : la cible d'un bucket est répartie uniformément sur ses jours éligibles. Elle sert au rythme
attendu, aux objectifs sur une fenêtre (rapports mensuels) et aux graphiques.

## 3. Grandeurs

| Grandeur | Définition |
|---|---|
| **Actual** (réalisé) | somme des contributions des entrées de `[début, aujourd'hui]` (`sum` : valeur si ≥ minimum ; `count` : 1 si l'entrée est valide ; booléen : vrai = 1 ; sans métrique : 1 par entrée) |
| **Goal** | somme des cibles des buckets sur la période du défi (défi sans fin : jusqu'à la fin de la période courante) ; objectif `total` : la cible |
| **Expected** (attendu) | somme des parts quotidiennes des jours éligibles **entièrement écoulés** (jusqu'à hier) ; `total` avec date de fin : `cible × jours éligibles écoulés / jours éligibles` ; `total` sans fin : non défini |
| **Remaining** | `max(goal − actual, 0)` |
| **Progress %** | `actual / goal × 100` (peut dépasser 100 % ; non défini si goal = 0) |
| **Gap** | `actual − expected` |
| **Completion rate** | buckets réussis / buckets échus (+ le bucket en cours s'il est déjà réussi) |
| **Average** | réalisé / jours éligibles écoulés (+ aujourd'hui s'il y a déjà une entrée) |

> Exemple du cahier des charges : 2 pages/jour, 10 jours écoulés, 18 pages → Expected 20, Gap −2 ;
> sur un défi de 10 jours (Goal 20) → Progress 90 %. Avec 24 pages → 120 %, Gap +4.

Le travail du jour compte immédiatement dans Actual, mais le jour n'entre dans Expected qu'une fois terminé :
on n'est jamais « en retard » le matin.

## 4. Statut (ordre de priorité)

1. `NOT_STARTED` — avant la date de début ;
2. `COMPLETED` — marqué terminé, ou objectif final atteint (défi avec date de fin, ou objectif `total`) ;
3. `PAUSED` — défi en pause ;
4. `MISSED` — période terminée sans atteindre l'objectif (sinon `COMPLETED`) ;
5. sinon comparaison réalisé/attendu : `AHEAD` si ≥ 110 %, `ON_TRACK` si ≥ 90 %, `BEHIND` en dessous
   (attendu = 0 : `AHEAD` si réalisé > 0, sinon `ON_TRACK`).

`REST_DAY` est un statut **du jour** (`result.today.status` = `done | pending | partial | rest | paused | outside`).

## 5. Séries

Unités = buckets avec une cible > 0 (jours pour un objectif quotidien, semaines/mois sinon ; jours actifs pour un
objectif total). Les jours de repos et les pauses sont retirés : ils ne cassent ni n'allongent une série.
- **Série actuelle** : en remontant depuis le bucket le plus récent ; un bucket en cours non encore réussi est ignoré
  (aujourd'hui ne casse pas la série).
- **Meilleure série** (= « plus longue série ») : plus longue suite de buckets réussis.

## 6. Versionnement

Chaque jour est évalué avec **l'objectif et le planning en vigueur ce jour-là**. Exemple : 2 pages/jour du 1er au 15
puis 3 pages/jour ⇒ objectif d'octobre = 15×2 + 16×3 = 78.

## 7. Fenêtres (rapports, bilans)

Avec `window=(début, fin)` : Goal, Expected et Actual sont restreints aux jours de la fenêtre (via les parts
quotidiennes), le taux de réussite aux buckets se terminant dans la fenêtre ; « terminé » = fenêtre écoulée.
`day_closed=True` considère `as_of` comme entièrement écoulé (rapports de mois passés).

## 8. Performance

`evaluate_many` charge en une requête les entrées des défis, en une requête les valeurs des seules métriques
utilisées, en une requête les jours de repos ; goals/schedules/pauses/milestones via `prefetch` ; tout le reste est en mémoire.

## 9. Tests

`tests/test_progress_engine.py` couvre : actual/expected/gap/progress (exemples du cahier), dépassement, aujourd'hui
hors attendu, retard, aucune entrée, défi futur, défi sans fin, entrées hors période, planning par jours, jours de repos
(défi et global), série cassée/meilleure série, jour en cours, tous les N jours, cible partielle, pause, statut pause,
hebdo proratisé, semaine partielle, minimum par entrée, mensuel en durée, total avec/sans fin, booléen, année
bissextile, changement de mois, fenêtre mensuelle, versionnement d'objectif, paliers.
