# 17 — Assistant de création en langage naturel

Étape 1 de l'assistant de création : « Décrivez-le avec vos mots ».

> « Je veux apprendre Python 2 heures par jour pendant 30 jours »
> → nom *Apprendre Python*, catégorie Apprentissage, champ Durée (+ Sujet), objectif 120 min / jour, tous les jours, 30 jours.

**L'utilisateur confirme toujours** : la suggestion pré-remplit les 6 étapes ; rien n'est créé avant « Créer le défi »,
et la création repasse par la validation serveur habituelle.

## Fonctionnement — `apps/challenges/assistant.py`

```
texte ──► Claude (si ANTHROPIC_API_KEY)  ──┐
     └──► analyseur intégré FR/EN/AR  ─────┴──► sanitize() ──► payload de l'assistant (+ source: "ai" | "rules")
```

### Moteur Claude (optionnel)

- SDK officiel `anthropic`, modèle `claude-opus-5-5` (réglable via `ASSISTANT_MODEL`), effort `low` (tâche d'extraction simple).
- **Sortie structurée** : `output_config.format` avec un schéma JSON strict (champs, objectif, planning, catégories et couleurs
  en `enum`) — la réponse est un JSON valide par construction.
- Repli serveur en cas de refus : `fallbacks: "default"` (bêta `server-side-fallback-2026-07-01`).
- Toute erreur (réseau, quota, refus, sortie tronquée, JSON invalide) bascule silencieusement sur l'analyseur intégré.
- Seul le texte saisi est envoyé — aucune autre donnée personnelle.

### Analyseur intégré (toujours disponible)

Expressions régulières multilingues : quantités et unités (heures/minutes → durée en minutes, pages, pas, litres, km,
verres, « fois / séances » → comptage), périodes (par jour / semaine / mois / au total), durée du défi (« pendant 30 jours »,
« 3 mois », « un an »), minimum (« au moins 30 minutes »), jours de la semaine, thèmes → catégorie / icône / couleur,
nom déduit de la phrase. Sans quantité, un défi « fait / non fait » quotidien est proposé.

### `sanitize()`

Ne fait jamais confiance à la sortie d'un moteur : types de champs connus, clés en `snake_case` uniques, options de liste
non vides, métrique existante et mesurable, agrégation cohérente, cible bornée, jours 0–6, durée ≤ 5 ans, icône et couleur
dans les listes autorisées, longueurs tronquées.

## API

`POST /api/challenges/suggest/` `{text}` (3–500 caractères) → payload de l'assistant ; limité à **30 requêtes / heure** par utilisateur.
