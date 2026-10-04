# 06 — Planner

## Vues

- **Semaine** : grille horaire 7 colonnes (heures visibles réglables dans le profil), barre de réalisation par jour,
  ligne « maintenant ». Sur mobile : sélecteur de jour + une seule colonne.
- **Jour** : même grille sur une colonne ; la page **Aujourd'hui** propose en plus une liste chronologique avec
  actions rapides (fait / manqué).
- Chevauchements : affichés côte à côte (algorithme de voies) et signalés à la création/au déplacement.

## Interactions

| Action | Comment | Endpoint |
|---|---|---|
| Ajouter | clic sur un créneau vide, bouton +, ajout rapide | `POST /api/planner/activities/` |
| Modifier | clic sur le bloc | `PATCH /api/planner/activities/{id}/` |
| Déplacer (heure / jour) | glisser-déposer (pas de 15 min), Alt+flèches | `POST …/{id}/move/` |
| Redimensionner | tirer le bord inférieur | `POST …/{id}/move/` |
| Dupliquer | modale | `POST …/{id}/duplicate/` |
| Terminer / partiel / manqué / annuler | modale ou liste | `POST …/{id}/status/` |
| Reporter | nouvelle date/heure ; l'original devient `rescheduled` | `POST …/{id}/reschedule/` |
| Supprimer | ponctuelle : suppression ; occurrence récurrente : `cancelled` | `DELETE …/{id}/` |

Créneaux : 15 min, 30 min, 1 h ou durée libre (ex. 09:15 → 10:45). Fin `00:00` = minuit.

## Statuts

`planned`, `in_progress`, `completed`, `partial`, `missed`, `cancelled`, `rescheduled`.
Dans les synthèses, « manqué » = `missed` explicite **+** activités prévues dont l'heure est passée sans confirmation.

## Récurrence

Une `RecurringRule` (quotidienne, jours choisis, tous les N jours, date de fin optionnelle) est stockée **une seule fois**.
`planner.services.ensure_occurrences(user, start, end)` matérialise les occurrences des dates affichées/évaluées
(idempotent grâce à l'unicité `(rule, occurrence_date)`). Une occurrence modifiée devient `is_detached`.
Modifier une règle supprime les occurrences **futures, non modifiées et encore prévues** — elles sont régénérées avec
la nouvelle règle ; le passé et les occurrences modifiées sont conservés. Supprimer une règle garde l'historique.

## Modèles de journée

`PlannerTemplate` + items. Appliquer à 1–62 jours (option « remplacer » : supprime les activités ponctuelles prévues
et annule les occurrences prévues de ces jours). « Enregistrer la journée comme modèle » copie un jour existant.

## Lien Planner ↔ Défi

Une activité peut être liée à un défi. Quand l'utilisateur la **confirme** comme faite, l'API renvoie
`entry_suggestion` (valeurs pré-remplies : durée réelle pour un champ durée, `true` pour un booléen, option de liste
correspondant au titre/catégorie…). L'interface propose « Vérifier et enregistrer » ; rien n'est enregistré sans
validation explicite.

## Activités de nuit

Une heure de fin **antérieure ou égale** à l'heure de début signifie « le lendemain » : Sommeil 23:00 → 07:00 = 8 h
(`00:00 → 00:00` = journée entière ; une plage de durée nulle est refusée). La durée, la détection des chevauchements
(qui tient compte de la veille et du lendemain), le retard (« à confirmer ») et l'export iCal utilisent la vraie fin.
Dans la grille, la partie après minuit apparaît en tête du jour suivant (`carryover` dans les réponses jour/semaine),
sans être comptée dans la synthèse de ce jour ; on la modifie depuis son jour de départ.

## Export iCal et abonnement

- `GET /planner/export.ics` : fichier `.ics` (30 jours passés → 90 jours à venir, occurrences récurrentes incluses).
- **Flux d'abonnement** (Google Agenda, Apple Calendrier, Outlook) : lien secret dans Paramètres → « Synchronisation du
  calendrier » (`/planner/feed/<jeton>.ics`, lecture seule, sans connexion). « Générer un nouveau lien » révoque l'ancien.
- Événements en UTC, UID stables (`activity-<id>@hôte`), statut (`TENTATIVE` prévu, `CONFIRMED` fait, `CANCELLED`),
  catégorie, défi lié ; lignes repliées à 75 octets (RFC 5545).
