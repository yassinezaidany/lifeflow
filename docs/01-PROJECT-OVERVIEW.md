# 01 — Vue d'ensemble

## Vision

LifeFlow aide chaque utilisateur à organiser sa vie autour de trois questions :

| | Question | Module |
|---|---|---|
| **PLAN** | Qu'est-ce que je prévois de faire ? | Planner (jour, semaine, routines, modèles) |
| **TRACK** | Qu'est-ce que j'ai réellement fait ? | Défis + entrées |
| **ANALYZE** | Comment est-ce que je progresse ? | Moteur de progression, statistiques, rapports |

Le cycle central est **Plan → Execute → Track → Analyze**. Les deux piliers (Planner et Challenge System)
communiquent : une activité peut être liée à un défi, et une fois *confirmée comme faite*, l'application propose
d'enregistrer le résultat dans le défi avec des valeurs pré-remplies — l'utilisateur vérifie et valide.

## Principes

1. **Générique** — aucun défi n'est codé en dur. « Sport », « Coran », « Fajr », « Apprentissage » ne sont que des
   données (modèles intégrés, données de démo). Tout passe par le moteur générique (champs + objectif + planning).
2. **Planifier ≠ réussir** — seule une entrée confirmée fait progresser un défi.
3. **L'historique n'est jamais réécrit** — objectifs et plannings sont versionnés ; les rapports sont des snapshots.
4. **Un jour de repos n'est pas un jour manqué** — et une pause n'est ni un succès ni un échec.
5. **Fiabilité et simplicité avant la richesse fonctionnelle.**

## Périmètre livré (MVP + une partie de la V2)

Authentification complète, profil, création/édition/archivage de défis, objectifs, plannings, champs,
entrées, ajout rapide, planner jour/semaine, routines, modèles de journée, calendrier, moteur de progression,
tableau de bord, page défi avec statistiques et graphiques, statistiques globales, rapports mensuels + historique + PDF,
exports CSV/Excel, journal, bilan hebdomadaire, paliers, modèles de défis, notifications in-app, responsive,
mode sombre, FR/EN, sécurité, tests, documentation.

Voir [14-ROADMAP.md](14-ROADMAP.md) pour la suite.
