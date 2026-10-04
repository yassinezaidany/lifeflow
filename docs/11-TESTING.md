# 11 — Tests

```bash
pip install -r requirements-dev.txt
pytest            # MySQL requis (docker compose up -d) — base de test créée automatiquement
```

Configuration : `pytest.ini` (settings `config.settings.test` : hachage rapide, e-mails en mémoire, throttling désactivé).

| Fichier | Couverture |
|---|---|
| `test_progress_engine.py` (31) | moteur : actual, expected, goal, progress, gap, statuts, séries, taux de réussite, repos, pauses, hebdo/mensuel/total, minimum par entrée, booléen, versionnement, paliers, année bissextile, fin/début de mois, fenêtres |
| `test_challenges_api.py` | création via assistant, normalisations, 10 cas de validation, catégorie d'un autre utilisateur, modèles, mise à jour, versionnement objectif/planning, champs, statuts, filtres, suppression, duplication, progression/statistiques, jours de repos, entrées de tous types, 7 cas de validation d'entrée, dates (futur, avant début), mise à jour/suppression |
| `test_planner.py` | création, durées personnalisées, minuit, plage invalide, chevauchements, modification/déplacement/duplication, **terminer ne crée jamais d'entrée**, entrée liée seulement après confirmation, tous les statuts, report, suppression, récurrence hebdo sans doublon, quotidienne/intervalle/date de fin, occurrence annulée non recréée, occurrence détachée conservée après modification de la règle, suppression de règle conservant l'historique, modèles (CRUD, appliquer, remplacer, depuis un jour), début de semaine, planning vide, retard compté comme manqué |
| `test_isolation.py` | listes vides pour l'autre utilisateur, 22 accès croisés → 404, rattachement à des objets étrangers refusé, données intactes, pages web, calendrier, exports |
| `test_auth.py` | inscription (+ catégories par défaut), mot de passe faible, doublons, connexion e-mail/nom, mauvais mot de passe, limitation, open redirect, logout POST, reset complet, e-mail inconnu, changement de mot de passe, paramètres, suppression du compte, API register/login/logout/me, JWT, validation du profil, CSRF |
| `test_reports_and_misc.py` | snapshot immuable (après suppression d'entrées, renommage, suppression du défi), versions, mois futur refusé, mois partiel, PDF, génération web + notification, rapport vide, **fuseaux horaires** (Tokyo/Los Angeles), audit, notifications (préférences, dédoublonnage), commande de rappels, API dashboard/calendrier, journal & bilan, en-têtes de sécurité, erreurs lisibles, injection CSV, XSS |
| `test_pages.py` | rendu (200) des 19 pages principales avec données de démo et en état vide, pages de détail, PDF, exports, interface française, redirection des anonymes |

Résultat au moment de la livraison : **191 tests réussis**.

## QA navigateur (Playwright, facultatif)

- `scripts/e2e_scenario.py` : scénario §109 complet (inscription → onboarding → assistant → activité liée →
  confirmation → enregistrement pré-rempli → ajout rapide → page défi → calendrier → rapport → PDF → historique →
  déconnexion → isolation avec un autre compte), en collectant les erreurs JavaScript.
- `scripts/ui_screenshots.py` : captures desktop/mobile, clair/sombre + erreurs console.

## Ajouts (version actuelle : 231 tests)

| Fichier | Couverture |
|---|---|
| `test_planner.py` (ajouts) | activités de nuit : durée, `carryover`, chevauchement avec le lendemain, retard, routine de nuit, plage nulle refusée |
| `test_pwa_notifications.py` (18) | service worker (portée, en-têtes, contenu), manifest, page hors ligne, purge du cache à la déconnexion ; push (désactivé sans clés, abonnement idempotent, envoi simulé, abonnement expiré supprimé, préférence, validation, réattribution d'appareil) ; e-mail HTML ; rappels (résumé du matin + dédoublonnage, fenêtre horaire, rappel de défi seulement si non fait, rappel d'activité, désactivation globale), planificateur, page notifications, `reminder_time` |
| `test_assistant_time_ical_rtl.py` (19) | analyseur FR/EN/AR (heures, séances + minimum, pages + jours, habitude oui/non, arabe, décimales), assainissement d'une sortie hostile, endpoint (moteur intégré, Claude simulé avec vérification du modèle / schéma / fallbacks, repli après refus, suggestion → création valide) ; objectifs horaires (moteur, validation API, modèle Lève-tôt) ; iCal (export, échappement, repli des lignes, isolation, flux par jeton, révocation, fin réelle des activités de nuit) ; arabe (`dir="rtl"`, sélecteur de langue, PDF arabe avec police embarquée) |
