# 05 — Moteur de défis

## Création (assistant en 6 étapes)

1. **Infos** — nom, description, catégorie, icône, couleur.
2. **Mesure** — préréglages compréhensibles (« Fait / non fait », « Un nombre », « Temps passé », « Séances »,
   « Distance, poids, argent… », « Personnalisé ») + champs supplémentaires. Un champ mesurable peut être choisi
   « pour l'objectif » ; sinon l'objectif compte les entrées (séances).
3. **Objectif** — cible + période (par jour / semaine / mois / au total) ; pour un champ numérique : additionner les
   valeurs ou compter les séances, et minimum par entrée (« au moins 30 min »).
4. **Fréquence** — tous les jours, jours précis, tous les N jours.
5. **Période** — 7 / 30 / 90 jours / 1 an / personnalisée / sans fin.
6. **Récapitulatif** — + paliers optionnels → création.

Le payload est validé par `ChallengeCreateSerializer` puis persisté par `challenges.services.create_challenge`
(transaction). Normalisations : sans métrique ou métrique booléenne ⇒ `count` ; `min_per_entry` seulement pour un champ numérique.

## Modèles de défis

`apps/challenges/system_templates.py` (synchronisés par migration et `seed_templates`). Un modèle pré-remplit
l'assistant ; l'utilisateur peut tout modifier avant de créer.

## Entrées

`tracking.services.create_entry / update_entry` valident chaque valeur selon son type :

| Type | Règles |
|---|---|
| booléen | true/false (accepte `yes/no/1/0`) |
| entier / durée | entier ≥ 0, ≤ 99 999 999, bornes `min_value/max_value` |
| décimal | nombre ≥ 0 (virgule acceptée) |
| heure | `HH:MM` |
| liste | doit appartenir aux options |
| texte | ≤ 500 caractères |

Plus : champs obligatoires, au moins une valeur, date ni future (dans le fuseau de l'utilisateur), ni avant le début, ni après la fin.
Une entrée liée à une activité exige que l'activité soit **terminée** (`completed`/`partial`).

## Modification d'un défi

- Infos générales : `PATCH /api/challenges/{id}/` (début non déplaçable après des entrées existantes).
- **Objectif / planning** : `PUT …/goal/` et `…/schedule/` avec `effective_from` (par défaut aujourd'hui). La version
  courante est fermée la veille et une nouvelle version est ouverte ; si la version courante commence le même jour
  (ou plus tard), elle est modifiée sur place (rien à préserver).
- Champs : ajout libre ; suppression = désactivation si le champ a des valeurs ou sert à l'objectif.
- Statut : pause (ouvre une `ChallengePause`), reprise (la ferme la veille), terminé/archivé (renseigne `closed_on`
  si clôture anticipée), réactivation.
