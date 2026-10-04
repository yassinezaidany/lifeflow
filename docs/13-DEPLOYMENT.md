# 13 — Déploiement

## Production (exemple Linux + Gunicorn + Nginx)

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
pip install -r requirements.txt gunicorn
python manage.py migrate
python manage.py collectstatic --noinput        # WhiteNoise sert les fichiers statiques compressés
python manage.py check --deploy
gunicorn config.wsgi:application --workers 3 --bind 127.0.0.1:8000
```

`.env` de production : `DEBUG=False`, `SECRET_KEY` longue et unique, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
(https://…), identifiants MySQL dédiés, SMTP réel (`EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`).

`config/settings/prod.py` active : redirection HTTPS, cookies `Secure`, HSTS 30 jours, `SECURE_PROXY_SSL_HEADER`,
stockage statique compressé avec manifeste.

Nginx : terminer TLS, transmettre `X-Forwarded-Proto`, servir `/media/` (avatars) depuis `MEDIA_ROOT`.

## Tâches planifiées

```cron
*/10 * * * *  cd /srv/lifeflow && .venv/bin/python manage.py send_reminders
```

## Points d'attention

- Plusieurs workers : remplacer le cache LocMem par Redis (`CACHES`) pour que la limitation de connexion soit partagée.
- Sauvegardes MySQL régulières (`mysqldump --single-transaction`).
- Ne jamais lancer `seed_demo` en production (ou le faire en connaissance de cause : les comptes démo sont marqués `is_demo`
  et supprimables via `seed_demo --reset`).

## Docker

`docker-compose.yml` fournit uniquement MySQL (développement). Django tourne nativement pour garder une architecture simple.

## PWA, push et rappels

- **HTTPS obligatoire** en production pour le service worker et le Web Push (déjà le cas avec `config.settings.prod`).
- `python manage.py generate_vapid_keys --write` une fois par environnement (garder les mêmes clés : en changer
  invalide les abonnements existants), et `SITE_URL` = URL publique (liens des e-mails).
- Rappels : `send_reminders` toutes les 5–10 minutes (cron, timer systemd, Planificateur de tâches Windows) ou un processus
  `run_scheduler` supervisé. Voir [15-PWA-AND-NOTIFICATIONS.md](15-PWA-AND-NOTIFICATIONS.md).
- Assistant IA : `ANTHROPIC_API_KEY` facultatif.
