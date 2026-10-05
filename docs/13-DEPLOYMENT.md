# 13 — Déploiement

Trois façons de faire tourner LifeFlow, de la plus simple à la plus « serveur ».

## 1. Poste local en une commande (Windows / Linux / macOS)

| Étape | Windows | Linux / macOS |
|---|---|---|
| Installation (une fois) | `.\setup.ps1 [-Demo] [-Dev] [-NoDocker]` | `./setup.sh [--demo] [--dev]` |
| Lancement (développement) | `.\start.ps1` | `./start.sh` |
| Lancement (production locale) | `.\start.ps1 -Prod [-Port 8000] [-Listen 0.0.0.0]` | `./start.sh --prod` |

`setup` crée le venv, installe les dépendances, génère `.env` avec une `SECRET_KEY` aléatoire (jamais commitée),
démarre MySQL (Docker, port 3307), applique les migrations, synchronise les modèles intégrés, compile les traductions,
génère les clés Web Push, crée éventuellement les comptes de démo, puis lance `doctor`.

`start` démarre MySQL si besoin, vérifie que le port est libre, lance le **planificateur de rappels** en arrière-plan
(arrêté proprement à la fermeture) puis le serveur :
- dev : `runserver` (DEBUG) ;
- `-Prod` : `config.settings.prod`, `DEBUG=False`, `migrate` + `collectstatic`, **Waitress** (Windows) / **Gunicorn**
  (Linux), `USE_HTTPS=False` pour un usage en HTTP sur le réseau local.

## 2. Pile Docker complète

```bash
cp .env.example .env                       # SECRET_KEY obligatoire ; ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS si domaine
docker compose --profile app up -d --build # db + web (Gunicorn, port ${APP_PORT:-8080}) + scheduler
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py doctor
```

- L'image (`Dockerfile`, `python:3.11-slim`) collecte les fichiers statiques à la construction et tourne sous un
  utilisateur non-root ; `docker/entrypoint.sh` attend MySQL, applique les migrations puis lance Gunicorn (`web`)
  ou la boucle de rappels (`scheduler`).
- Volumes persistants : `lifeflow_mysql` (données), `lifeflow_media` (avatars), `lifeflow_logs` (journaux + battement
  de cœur du planificateur).
- `GET /healthz` sert de sonde de santé (exemptée de la redirection HTTPS).
- Sans profil (`docker compose up -d`), seul MySQL démarre : c'est le mode développement.

## 3. Serveur avec reverse proxy (Nginx / Caddy / Traefik)

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput   # WhiteNoise sert les statiques compressés + manifestés
python manage.py check --deploy
python manage.py doctor
gunicorn config.wsgi:application --workers 3 --bind 127.0.0.1:8000
python manage.py run_scheduler             # processus supervisé (systemd) — ou cron sur send_reminders
```

Le proxy termine TLS et transmet `X-Forwarded-Proto` ; il peut servir `/media/` lui-même (`SERVE_MEDIA=False`).

### `.env` de production

| Variable | Valeur |
|---|---|
| `DEBUG` | `False` |
| `SECRET_KEY` | longue, unique, jamais commitée |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | domaine(s) ; origines en `https://…` |
| `USE_HTTPS` | `True` derrière TLS (redirection, cookies `Secure`, HSTS 30 jours) ; `False` seulement en réseau local HTTP |
| `DB_*` | utilisateur MySQL dédié, mot de passe fort |
| `EMAIL_BACKEND` + `EMAIL_*` | SMTP réel (`django.core.mail.backends.smtp.EmailBackend`) |
| `SITE_URL` | URL publique (liens des e-mails) |
| `VAPID_*` | `generate_vapid_keys --write` une fois ; les garder (en changer invalide les abonnements) |
| `ANTHROPIC_API_KEY` | facultatif (assistant IA) |

## Diagnostic : `python manage.py doctor`

Vérifie base de données, migrations en attente, clé secrète, mode, fichiers statiques (manifeste en prod), polices PDF,
traductions compilées, e-mail, Web Push, assistant IA, battement de cœur du planificateur (`logs/scheduler.last`),
modèles intégrés et comptes. Les avertissements (ex. e-mails en console) n'empêchent pas le démarrage ; une erreur renvoie
le code de sortie 1 (utilisable en CI ou en sonde).

## Points d'attention

- Plusieurs workers ou serveurs : remplacer le cache LocMem par Redis (`CACHES`) pour partager la limitation de débit.
- Sauvegardes MySQL régulières (`mysqldump --single-transaction`, ou sauvegarde du volume `lifeflow_mysql`).
- `seed_demo` ne doit pas être lancé en production (les comptes démo sont marqués `is_demo` et supprimables via
  `seed_demo --reset`, jamais mélangés aux vrais comptes).
- **HTTPS obligatoire** sur Internet : le service worker et le Web Push ne fonctionnent qu'en HTTPS (ou sur `localhost`).
- Voir aussi [15-PWA-AND-NOTIFICATIONS.md](15-PWA-AND-NOTIFICATIONS.md) pour les rappels et le push.
