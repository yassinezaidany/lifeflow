# 10 — Sécurité

| Sujet | Mise en œuvre |
|---|---|
| Mots de passe | hachage PBKDF2 (Django), validateurs (longueur ≥ 8, similarité, mots de passe courants, numériques) |
| Connexion | e-mail ou nom d'utilisateur ; **limitation** : 8 échecs / 10 min par IP+identifiant (`accounts/ratelimit.py`) ; temps constant si l'utilisateur n'existe pas ; anti open-redirect sur `next` |
| Réinitialisation | jetons Django signés (3 h), pas de fuite d'existence d'un compte |
| Sessions | cookies `HttpOnly`, `SameSite=Lax`, `Secure` + HSTS en production, rotation au changement de mot de passe |
| CSRF | middleware Django ; API en session exige `X-CSRFToken` (testé) |
| XSS | échappement automatique des templates, données JSON injectées via `json_script` / filtre `json_attr` échappé, CSP |
| En-têtes | `Content-Security-Policy` (ressources propres uniquement, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy` |
| Injection SQL | ORM exclusivement, aucune requête brute |
| Validation | **côté serveur** pour toute donnée (serializers DRF + services) ; le frontend n'est qu'un confort |
| Autorisation / isolation | chaque queryset est filtré par `user` (`OwnedQuerysetMixin`) + permission objet `IsOwner` ; les FK saisies (catégorie, défi, activité) sont restreintes aux objets de l'utilisateur (`UserScopedPK`) ; un objet d'un autre utilisateur renvoie **404** (pas 403, pour ne pas révéler son existence) |
| API | authentification obligatoire par défaut, throttling (`anon` 60/min, `user` 1200/min, `auth` 10/min) |
| Exports | neutralisation de l'injection de formules CSV/Excel (`=`, `+`, `-`, `@`) |
| Fichiers | avatar : extensions jpg/png/webp, ≤ 2 Mo |
| Secrets | `.env` (non versionné), `.env.example` fourni |
| Erreurs & logs | gestionnaire d'exceptions API (messages lisibles, détails journalisés), logs rotatifs `logs/lifeflow.log` |
| Traçabilité | `AuditLog` : création/modification/statut de défi, changements d'objectif/planning, entrées, activités, routines, modèles appliqués, rapports, événements de compte |
| Administration | l'admin ne gère que les utilisateurs et les modèles système ; **les contenus privés (entrées, journal, planning, rapports) ne sont pas enregistrés dans l'admin** |

Tests dédiés : `tests/test_isolation.py` (22 tentatives d'accès croisé API + pages web + exports),
`tests/test_auth.py` (CSRF, rate limiting, open redirect, reset), `tests/test_reports_and_misc.py` (en-têtes, XSS, CSV).

## Ajouts

| Sujet | Mise en œuvre |
|---|---|
| Cache hors ligne | le service worker ne met jamais en cache admin, comptes, PDF, exports, `.ics` ni écritures ; pages et réponses API personnelles effacées dès qu'une page « déconnecté » s'affiche |
| Saisie hors ligne | rejouée avec un jeton CSRF frais ; aucune écriture ne contourne la validation serveur |
| Web Push | endpoints HTTPS uniquement, clés VAPID dans `.env`, abonnement lié au compte connecté (réattribué si l'appareil change de compte), abonnements expirés supprimés |
| Flux iCal | jeton aléatoire de 256 bits, lecture seule, révocable ; un jeton inconnu renvoie 404 |
| Assistant IA | clé dans `.env`, limite 30 requêtes/heure, seul le texte saisi est transmis, sortie toujours assainie puis revalidée à la création |
