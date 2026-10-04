# 15 — PWA, hors ligne et notifications

## Application installable (PWA)

| Élément | Implémentation |
|---|---|
| Manifest | `/manifest.webmanifest` (vue `apps/core/pwa.py`) : `standalone`, démarre sur `/today/`, icônes PNG 192/512 + *maskable*, raccourcis Aujourd'hui / Planner |
| Icônes | générées depuis le logo par `frontend/make_icons.py` (Pillow) dans `static/img/icons/` |
| Service worker | `/sw.js` servi à la racine (portée `/`, en-tête `Service-Worker-Allowed`), rendu depuis `templates/pwa/sw.js` ; sa version est le **hash du contenu des fichiers de l'app shell** → chaque déploiement invalide automatiquement l'ancien cache |
| Installation | bouton « Installer l'application » (barre latérale, Paramètres) via `beforeinstallprompt` ; consigne iOS (« Sur l'écran d'accueil ») |

Le service worker n'est actif qu'en **contexte sécurisé** (HTTPS, ou `localhost` / `127.0.0.1`).

### Stratégies de cache

| Requête | Stratégie |
|---|---|
| `/static/…` | *stale-while-revalidate* (cache `lf-shell-<version>`, pré-rempli à l'installation) |
| Navigations (pages) | *network-first*, copie des 30 dernières pages (`lf-pages`), sinon page `/offline/` |
| API en lecture utiles hors ligne (`/api/planner/today/`, `/api/planner/`, `/api/planner/week/`, `/api/challenges/?…`, catégories, dashboard, notifications) | *network-first* avec repli sur le cache (`lf-api`) ; sinon réponse JSON `503 {offline: true}` traduite en message clair |
| `/admin/`, `/accounts/`, PDF, exports, `.ics`, écritures | jamais mis en cache |

**Vie privée** : sur toute page « déconnecté » (connexion, inscription…), la page demande au service worker
d'effacer `lf-pages` et `lf-api` — les données personnelles ne restent pas sur un appareil partagé après déconnexion.

### Saisie hors ligne (outbox)

`static/js/app.js` : si un `POST /api/entries/` ou `POST /api/journal/` échoue faute de réseau, la requête est placée
dans une file locale (`localStorage`, clé `lf-outbox`) et l'utilisateur voit « Enregistré hors ligne ». La file est rejouée
(avec un jeton CSRF frais) au retour du réseau (`online`), au retour sur l'onglet et au chargement. Les erreurs de
validation (4xx) sont signalées et retirées de la file ; les erreurs serveur/403 sont retentées. Une pastille dans la barre
supérieure indique « Hors ligne » et le nombre d'éléments à synchroniser (clic = synchroniser).

## Notifications

Toutes les notifications passent par `apps.notifications.services.notify()` :

1. vérifie les préférences (`UserSetting`) ;
2. crée la notification in-app (dédoublonnage par `dedupe_key`) ;
3. l'envoie en **Web Push** à chaque appareil abonné (si `push_notifications`) ;
4. l'envoie par **e-mail HTML** (si `email_notifications`).

### Web Push

- Clés VAPID : `python manage.py generate_vapid_keys --write` (écrit `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` dans `.env`).
  Sans clés, le push est simplement désactivé (l'interface l'explique).
- Paramètres → Notifications → « Notifications sur cet appareil » : demande la permission, s'abonne via `PushManager`,
  enregistre l'abonnement (`POST /api/notifications/push/subscribe/`), bouton « Envoyer un test ».
- `PushSubscription` : unicité par hash SHA-256 de l'endpoint ; un appareil réutilisé par un autre compte est réattribué ;
  les abonnements expirés (404/410) sont supprimés automatiquement.
- Le service worker affiche la notification (`push`) et ouvre/focalise l'onglet sur l'URL cible (`notificationclick`).

### Règles de rappel (`apps/notifications/reminders.py`)

Évaluées dans le fuseau de chaque utilisateur, idempotentes (une exécution toutes les 5–10 min suffit) ; un rappel horaire
n'est envoyé que dans les 90 minutes qui suivent son heure (pas de rappel « en retard » après une panne).

| Rappel | Condition |
|---|---|
| Activité à venir | activité prévue qui commence dans les 15 minutes |
| Résumé du matin | à l'heure choisie (08:00 par défaut) : défis à faire + activités prévues |
| Rappel de défi | à l'heure de rappel du défi, uniquement un jour actif où rien n'est encore enregistré |
| Fin de journée | après l'heure choisie (21:00), s'il reste des défis ouverts |
| Bilan hebdomadaire | dernier jour de la semaine (selon le profil) après 18:00 |
| Rapport prêt | à la génération d'un rapport |

### Planification

- `python manage.py send_reminders` — une passe (cron / systemd / Planificateur de tâches Windows) ;
- `python manage.py run_scheduler [--interval 300]` — boucle intégrée, pratique en développement ou sur un petit serveur.

Windows (toutes les 10 minutes) :

```powershell
schtasks /Create /SC MINUTE /MO 10 /TN "LifeFlow reminders" /TR "C:\chemin\lifeFLow\.venv\Scripts\python.exe C:\chemin\lifeFLow\manage.py send_reminders"
```
