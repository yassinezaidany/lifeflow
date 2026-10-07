# 20 — Publier LifeFlow gratuitement sur Internet

Deux méthodes, toutes deux gratuites :

| | **A. PythonAnywhere** (recommandé) | **B. Render + Aiven** |
|---|---|---|
| Carte bancaire | **jamais demandée** | demandée par Render « pour vérifier l'identité » (1 $ autorisé puis annulé) |
| Adresse | `https://<compte>.pythonanywhere.com` | `https://<nom>.onrender.com` |
| Base de données | SQLite (fichier sur le disque du compte) | MySQL managé (Aiven) |
| Mise en veille | non | après 15 min sans visite (évitée par le cron) |
| Entretien | un clic par mois (« Run until 1 month from today ») | aucun |
| Limites | 512 Mo de disque, 1 processus web | 512 Mo de RAM, 1 Go MySQL |

Les deux conviennent à un usage personnel ou à une petite communauté. Les offres gratuites peuvent évoluer.

---

## A. PythonAnywhere (sans carte bancaire)

### 1. Rendre le code accessible

Le dépôt GitHub doit pouvoir être cloné par PythonAnywhere. Le plus simple : le rendre **public**
(GitHub → dépôt → *Settings* → *Danger Zone* → *Change visibility*). Il ne contient **aucun secret**
(`.env` est exclu) ; les mots de passe et clés sont générés sur le serveur.

### 2. Créer le compte et l'application web

1. Compte gratuit (« Beginner ») sur <https://www.pythonanywhere.com>. Le nom choisi donnera l'adresse
   `https://<nom>.pythonanywhere.com`.
2. Onglet **Web** → **Add a new web app** → **Next** → **Manual configuration** → **Python 3.13** (ou la plus récente
   proposée, au moins 3.11) → **Next**.

### 3. Installer LifeFlow (une commande)

Onglet **Consoles** → **Bash**, puis :

```bash
git clone https://github.com/<compte-github>/lifeflow.git ~/lifeflow
bash ~/lifeflow/deploy/pythonanywhere.sh
```

Le script (5 à 10 minutes) crée l'environnement Python, génère `.env` (clé secrète, jeton du cron, clés Web Push),
crée la base SQLite dans `~/lifeflow-data/`, prépare les fichiers statiques, écrit le fichier WSGI de l'application,
demande **l'identifiant, l'e-mail et le mot de passe de l'administrateur**, puis lance `doctor`. Il affiche à la fin
les dernières étapes et le **jeton du cron** (à garder pour l'étape 5).

> Compte créé sur le site européen (`eu.pythonanywhere.com`) : lancer
> `PA_DOMAIN=$USER.eu.pythonanywhere.com bash ~/lifeflow/deploy/pythonanywhere.sh`.

### 4. Terminer dans l'onglet Web

- **Virtualenv** : `/home/<nom>/.virtualenvs/lifeflow`
- **Security → Force HTTPS** : activé
- Bouton vert **Reload** → ouvrir `https://<nom>.pythonanywhere.com` et se connecter avec le compte administrateur.

### 5. Rappels (cron-job.org)

Compte gratuit sur <https://cron-job.org> → **Create cronjob** :
- URL : `https://<nom>.pythonanywhere.com/internal/cron/reminders/`
- toutes les **10 minutes**
- **Advanced → Headers** : `X-Cron-Token` = le jeton affiché par le script (aussi dans `~/lifeflow/.env`, ligne `CRON_TOKEN`)

La réponse doit être `{"status": "ok", ...}` (404 avec un mauvais jeton).

### 6. Entretien

- **Chaque mois** : PythonAnywhere envoie un e-mail ; onglet **Web** → **Run until 1 month from today**.
  Sans ce clic, le site est mis en pause (les données sont conservées).
- **Mettre à jour** après un `git push` : console Bash → `bash ~/lifeflow/deploy/pythonanywhere.sh update`
  (récupère le code, migre la base, recharge le site).
- **Sauvegarde** : fichier `~/lifeflow-data/lifeflow.sqlite3` à télécharger depuis l'onglet **Files**, ou exports
  Rapports → Export.

### Limites propres à l'offre gratuite

- L'accès Internet sortant est limité à une liste de sites autorisés : les notifications push, l'envoi d'e-mails
  par Brevo et l'assistant Claude ne fonctionnent que si leurs services y figurent. Tout le reste de l'application
  (comptes, défis, planner, suivi, statistiques, rapports PDF, communauté…) n'en dépend pas.
- 512 Mo de disque au total (code + environnement Python + base) : largement suffisant pour des centaines d'utilisateurs.

---

## B. Render + Aiven MySQL (carte de vérification demandée par Render)

Fichier `render.yaml` fourni (Blueprint). Résumé :

1. **Aiven** (<https://aiven.io>) : *Create service* → **MySQL** → plan **Free** ; noter Host, Port, Password.
2. **Render** (<https://render.com>) : *New → Blueprint* → dépôt `lifeflow` → renseigner `DB_HOST`, `DB_PORT`,
   `DB_PASSWORD` et `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` (les autres champs sont facultatifs)
   → *Apply*. `SECRET_KEY` et `CRON_TOKEN` sont générés automatiquement ; TLS MySQL, stockage des avatars en base
   (`MEDIA_STORAGE=db`, pas de disque permanent) et HTTPS sont préréglés.
3. **cron-job.org** : même réglage qu'en A.5 avec l'adresse `onrender.com` et le `CRON_TOKEN` de Render
   (*Environment*) — il garde aussi le service éveillé.
4. **E-mails** (facultatif) : Render bloque le SMTP ; utiliser Brevo (`BREVO_API_KEY`, `DEFAULT_FROM_EMAIL` =
   expéditeur vérifié). **Push** (facultatif) : `python manage.py generate_vapid_keys` en local, copier les deux clés.

Chaque `git push` redéploie automatiquement. En cas d'erreur « table without a primary key » : Aiven →
*Advanced configuration* → désactiver `sql_require_primary_key`.

---

## Réglages utilisés (référence)

| Variable | Rôle |
|---|---|
| `DB_ENGINE=sqlite`, `SQLITE_PATH` | base SQLite (méthode A) |
| `DB_HOST`… `DB_SSL_MODE=REQUIRED` | MySQL managé en TLS (méthode B) |
| `MEDIA_STORAGE=db` | avatars stockés en base (hébergeurs sans disque permanent) |
| `CRON_TOKEN` | active `/internal/cron/reminders/` |
| `SECURE_SSL_REDIRECT=False` | redirection HTTPS laissée à l'hébergeur (PythonAnywhere « Force HTTPS ») |
| `EMAIL_BACKEND=apps.core.mail.BrevoEmailBackend`, `BREVO_API_KEY` | e-mails par API HTTPS |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | administrateur créé sans console |
