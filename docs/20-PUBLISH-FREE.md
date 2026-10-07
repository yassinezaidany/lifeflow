# 20 — Publier LifeFlow gratuitement sur Internet

Objectif : une adresse publique en HTTPS (`https://<nom>.onrender.com`) où n'importe qui peut créer un compte,
**sans payer et sans carte bancaire**. Durée : environ 30 minutes, une seule fois.

| Rôle | Service gratuit | Ce qu'il fournit |
|---|---|---|
| Code source | **GitHub** | dépôt (privé ou public) d'où Render construit l'application |
| Application | **Render** (plan *Free*) | conteneur Docker + HTTPS + déploiement automatique à chaque `git push` |
| Base de données | **Aiven** (MySQL *Free*) | MySQL 8 managé, 1 Go, chiffré (TLS) |
| Rappels | **cron-job.org** | appelle LifeFlow toutes les 10 min (rappels + empêche la mise en veille) |
| E-mails (facultatif) | **Brevo** (*Free*, 300/jour) | réinitialisation de mot de passe, rappels par e-mail |

> Les offres gratuites peuvent évoluer. Elles conviennent à un usage personnel ou à une petite communauté,
> pas à des milliers d'utilisateurs simultanés.

## Étape 1 — Mettre le code sur GitHub

1. Créer un compte sur <https://github.com> puis un dépôt **vide** nommé `lifeflow` (privé conseillé).
2. Dans PowerShell, à la racine du projet :

```powershell
git remote add origin https://github.com/<votre-compte>/lifeflow.git
git push -u origin master
```

(GitHub demande de se connecter dans le navigateur la première fois.) Le fichier `.env` n'est **jamais** envoyé :
il est exclu par `.gitignore`, aucun secret n'est dans le dépôt.

## Étape 2 — Créer la base MySQL gratuite (Aiven)

1. Compte sur <https://aiven.io> → **Create service** → **MySQL** → plan **Free** → région proche (Europe).
2. Quand le service est *Running*, ouvrir **Connection information** et noter : **Host**, **Port**,
   **User** (`avnadmin`), **Password**, **Database** (`defaultdb`).

## Étape 3 — Déployer sur Render

1. Compte sur <https://render.com> (bouton « Sign in with GitHub »).
2. **New → Blueprint** → choisir le dépôt `lifeflow`. Render lit `render.yaml` et demande les valeurs secrètes :

| Variable | Valeur |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_PASSWORD` | celles d'Aiven (étape 2) |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | votre compte **administrateur** (mot de passe fort) |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | facultatif — voir « Notifications push » ci-dessous |
| `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL` | facultatif — voir « E-mails » ci-dessous |
| `ANTHROPIC_API_KEY` | facultatif (sinon l'assistant utilise l'analyseur intégré) |

`SECRET_KEY` et `CRON_TOKEN` sont **générés automatiquement** par Render ; `DB_NAME`, `DB_USER`, le TLS MySQL,
le stockage des avatars en base et le HTTPS sont déjà réglés dans `render.yaml`.

3. **Apply**. Le premier déploiement prend 5 à 10 minutes (construction de l'image, migrations, création des modèles
   de défis et du compte administrateur). L'adresse apparaît en haut : `https://lifeflow-xxxx.onrender.com`.
4. Ouvrir l'adresse, se connecter avec le compte administrateur, vérifier `/admin/`.

## Étape 4 — Rappels et maintien en éveil (cron-job.org)

Le plan gratuit de Render n'a pas de tâches planifiées et met l'application en veille après 15 minutes sans visite
(réveil ≈ 1 minute). Un appel toutes les 10 minutes règle les deux problèmes.

1. Dans Render → service `lifeflow` → **Environment**, copier la valeur de `CRON_TOKEN`.
2. Compte sur <https://cron-job.org> → **Create cronjob** :
   - URL : `https://lifeflow-xxxx.onrender.com/internal/cron/reminders/`
   - Planification : toutes les **10 minutes**
   - **Advanced → Headers** : `X-Cron-Token` = la valeur copiée
3. Le test doit répondre `{"status": "ok", ...}`. Sans le bon jeton, l'adresse répond 404.

750 heures gratuites par mois couvrent un service allumé en permanence (744 h max).

## Notifications push (facultatif)

Sur votre PC : `.\.venv\Scripts\python manage.py generate_vapid_keys` affiche une paire de clés (sans `--write`, rien
n'est écrit). Copier les deux clés dans Render (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`) et mettre
`VAPID_SUBJECT=mailto:votre@adresse`. Ne plus les changer ensuite (cela invaliderait les abonnements).

## E-mails (facultatif mais recommandé)

Render gratuit bloque le SMTP ; LifeFlow envoie donc par l'API HTTPS de Brevo :

1. Compte sur <https://www.brevo.com> → **Senders** : ajouter et vérifier votre adresse d'expéditeur.
2. **SMTP & API → API Keys** : créer une clé.
3. Dans Render : `BREVO_API_KEY` = la clé, `DEFAULT_FROM_EMAIL` = `LifeFlow <adresse-vérifiée>`.

Sans e-mail configuré, tout fonctionne sauf la réinitialisation de mot de passe par e-mail (la page ne plante pas,
l'e-mail n'est simplement pas envoyé).

## Mettre à jour l'application

Chaque `git push` sur `master` redéploie automatiquement (migrations comprises). Aucune donnée n'est perdue :
tout est dans MySQL, avatars compris.

## Vérifier et dépanner

- Render → **Logs** : erreurs au démarrage (connexion MySQL, variable manquante).
- **Shell** n'est pas disponible en gratuit ; pour un diagnostic complet, lancer en local
  `python manage.py doctor` avec les mêmes variables.
- « Unable to create or change a table without a primary key » au premier déploiement : dans Aiven →
  **Advanced configuration**, désactiver `sql_require_primary_key`, puis redéployer.
- Après le premier démarrage, vous pouvez supprimer `DJANGO_SUPERUSER_PASSWORD` des variables Render
  (le compte existe déjà).

## Limites à connaître

| Limite | Effet | Parade |
|---|---|---|
| Veille Render après 15 min | premier chargement lent | cron-job.org toutes les 10 min |
| Aiven Free s'éteint après une longue inactivité | base indisponible | le cron la garde active ; e-mail d'avertissement d'Aiven |
| 1 Go MySQL, 512 Mo RAM | petite communauté | suffisant pour des centaines d'utilisateurs actifs |
| Pas de sauvegarde garantie | perte possible en cas d'incident | exporter régulièrement (Rapports → Export) ou `mysqldump` |
| Cache par processus | limitation de débit approximative avec 2 workers | acceptable ; Redis si l'audience grandit |
