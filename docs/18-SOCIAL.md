# 18 — Communauté (V3 sociale)

Page **Communauté** (`/community/`) : amis, défis de groupe et modèles communautaires.
Principe directeur : **privé par conception**. Rien de ce qu'un utilisateur enregistre (entrées, notes, journal, planner)
n'est jamais visible par quelqu'un d'autre ; seuls des **chiffres agrégés**, et seulement dans un groupe rejoint
volontairement, peuvent l'être.

## Amis

- Demande par **nom d'utilisateur ou e-mail exact** (pas d'annuaire ni de recherche par préfixe : impossible
  d'énumérer les comptes). Limite : 30 demandes par heure et par utilisateur.
- Si l'autre personne avait déjà envoyé une demande, elle est acceptée automatiquement.
- Accepter / refuser / annuler / retirer un ami. Une notification est envoyée à la demande et à l'acceptation.
- Être ami ne donne accès à **rien** en soi : cela permet seulement d'inviter quelqu'un dans un défi de groupe.

## Défis de groupe

1. Depuis les paramètres d'un défi : **Partager avec des amis** → crée un `SharedChallenge` contenant la *définition*
   du défi (champs, objectif, planning, dates) — jamais les entrées.
2. Le créateur invite des amis, ou partage le **lien d'invitation** (`/community/join/<code>/`, code aléatoire).
3. Rejoindre crée **une copie personnelle** du défi chez le membre (via le même service de création, donc les mêmes
   validations). Chacun suit sa copie ; le moteur de progression la calcule comme n'importe quel défi.
4. **Classement** : progression, taux de réussite, séries, statut et « fait aujourd'hui » — rien d'autre. Chaque membre peut masquer sa
   progression (`share_progress = False`) : il apparaît alors « Progression masquée » pour les autres.
5. Quitter le groupe conserve le défi et les entrées. Le créateur ne quitte pas : il **clôt** le groupe ; chacun garde
   alors son défi.

Les pages d'un groupe renvoient **404** à toute personne qui n'en est pas membre ou invitée.

## Modèles communautaires

« Publier comme modèle » (paramètres du défi) crée un `ChallengeTemplate` avec `owner` = auteur et `is_public = True`.
Seule la **structure** est publiée (champs, objectif, planning, durée). Les autres utilisateurs le voient dans
Communauté → « Partagés par la communauté » et peuvent démarrer un défi pré-rempli (`/challenges/new/?template_id=<id>`).
L'auteur peut le dépublier à tout moment ; les modèles des comptes désactivés ne sont plus listés.

## Modèle de données (`apps/social`)

| Modèle | Rôle |
|---|---|
| `Friendship` | `from_user`, `to_user`, `status` (pending / accepted / declined) ; contraintes : une demande par sens, pas d'amitié avec soi-même |
| `SharedChallenge` | `owner`, `name`, `description`, `icon`, `color`, `definition` (JSON), `start_date`, `end_date`, `invite_code` (unique, aléatoire), `is_active` |
| `SharedChallengeMember` | `shared`, `user`, `challenge` (copie personnelle, `SET_NULL`), `status` (invited / active), `share_progress`, `invited_by`, `joined_at` |

Clore un groupe supprime le `SharedChallenge` et ses adhésions ; les défis personnels (et leurs entrées) restent intacts.

## API (session ou JWT)

| Méthode | URL | Contenu |
|---|---|---|
| GET | `/api/v1/social/friends/` | amis et demandes en attente |
| GET | `/api/v1/social/shared/` | groupes dont l'utilisateur est membre ou invité |
| GET | `/api/v1/social/shared/<id>/leaderboard/` | classement agrégé (404 si non membre) |

## Tests

`tests/test_social.py` (20 tests) : demandes et acceptation automatique, limitation, impossibilité d'inviter un non-ami,
404 pour les non-membres, copie personnelle à l'adhésion, classement sans aucune donnée brute, masquage, départ / clôture,
publication et dépublication de modèles, isolation API.
