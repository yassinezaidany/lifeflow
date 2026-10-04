# LifeFlow

**Plateforme personnelle de défis, de planning et de progression** — *Plan → Execute → Track → Analyze.*

LifeFlow réunit un **planner** (journée / semaine, routines, modèles de journée), un **moteur de défis générique**
(n'importe quel objectif mesurable : pages, pas, minutes, séances, litres, fait/non fait…), un **moteur de progression**
centralisé (réalisé, attendu, écart, statut, séries, taux de réussite), des **statistiques**, un **calendrier**,
un **journal** et des **rapports mensuels** figés (HTML + PDF).

> Règle fondamentale : *planifier ≠ réussir*. Une activité planifiée ne fait jamais progresser un défi tant que
> l'utilisateur n'a pas confirmé ce qu'il a réellement fait.

---

## Fonctionnalités

| Domaine | Contenu |
|---|---|
| Comptes | Inscription, connexion (e-mail ou nom d'utilisateur), déconnexion, mot de passe oublié / réinitialisation, changement de mot de passe, suppression du compte, profil (avatar, fuseau, langue, formats, début de semaine, thème), préférences de notification, onboarding facultatif |
| Défis | Assistant en 6 étapes **+ description en langage naturel** (« Je veux apprendre Python 2 h par jour pendant 30 jours » → assistant pré-rempli, IA Claude optionnelle ou analyseur intégré FR/EN/AR), champs personnalisés (fait/non fait, entier, décimal, durée, heure, texte, liste), objectifs quotidiens / hebdo / mensuels / totaux, minimum par entrée, **objectifs horaires** (« réveil avant 05:30 »), rappel quotidien par défi, fréquences (tous les jours, jours choisis, tous les N jours), période, paliers, pause, archivage, duplication, **historisation des objectifs et plannings**, jours de repos, 11 modèles intégrés |
| Suivi | Entrées multi-valeurs validées côté serveur, ajout rapide global (+), enregistrement depuis une activité terminée (pré-rempli, confirmé par l'utilisateur) |
| Planner | Vue jour & semaine en grille horaire, **activités de nuit** (23:00 → 07:00), glisser-déposer (y compris vers un autre jour), redimensionnement, clic pour créer, détection des chevauchements, statuts (prévu, en cours, fait, partiel, manqué, annulé, reporté), report, duplication, routines récurrentes (sans duplication des règles), modèles de journée (appliquer à plusieurs jours, enregistrer une journée comme modèle), **export iCal + flux d'abonnement** (Google/Apple/Outlook) |
| Analyse | Tableau de bord, vue « Aujourd'hui », calendrier mensuel avec détail du jour, page par défi (anneau, KPIs, courbe réalisé/attendu, barres hebdo, donut de réussite, heatmap, statistiques, paliers, historique), page Statistiques multi-défis |
| Réflexion | Journal (humeur, lien à un défi), bilan hebdomadaire (questions guidées) |
| Rapports | Rapport mensuel figé (snapshot), versions, historique, PDF professionnel, exports CSV / Excel |
| Notifications | In-app, **Web Push** (VAPID, multi-appareils), e-mail HTML ; résumé du matin, rappels d'activités, rappel par défi, bilan de fin de journée, bilan hebdomadaire, rapport prêt ; planificateur intégré (`run_scheduler`) |
| PWA | Installable (manifest + icônes), **service worker** : pages et données récentes disponibles hors ligne, **entrées et notes enregistrées hors ligne puis synchronisées automatiquement** |
| Transverse | Mode clair/sombre/système, responsive mobile-first (barre de navigation mobile + bouton + central), **FR / EN / AR avec mise en page RTL** (PDF arabe inclus), journal d'audit, API REST complète (session + JWT) |

## Stack

- **Backend** : Python 3.11+, Django 5.2, Django REST Framework, MySQL 8 (Django ORM)
- **Frontend** : templates Django + Tailwind CSS 3 (compilé, CSS commité) + Alpine.js + Chart.js, icônes Lucide (sprite SVG) — tout est servi localement, aucun CDN
- **PDF** : ReportLab + police DejaVu embarquée (latin + arabe, mise en forme arabe via arabic-reshaper / python-bidi) — Python pur, fonctionne sous Windows
- **Notifications** : pywebpush (Web Push / VAPID) ; **Assistant IA** (optionnel) : SDK Anthropic, modèle Claude Opus 5.5 en sortie JSON structurée
- **Tests** : pytest + pytest-django (sur MySQL), scripts Playwright optionnels pour la QA navigateur

Choix d'architecture : un **monolithe Django modulaire** (pas de SPA séparée) — une seule application à déployer,
un seul routage, et une API REST propre qui prépare une future PWA / application mobile. Détails dans
[docs/02-ARCHITECTURE.md](docs/02-ARCHITECTURE.md).

## Installation

Prérequis : Python 3.11+, Docker (pour MySQL) **ou** un MySQL 8 local, Node.js 18+ (uniquement pour recompiler le CSS).

```powershell
# 1. Environnement Python
python -m venv .venv
.\.venv\Scripts\activate            # Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt     # + requirements-dev.txt pour les tests

# 2. Configuration
copy .env.example .env              # puis renseigner SECRET_KEY (longue chaîne aléatoire)

# 3. Base MySQL (Docker, port 3307 pour éviter un conflit avec XAMPP/WAMP)
docker compose up -d

# 4. Schéma + modèles de défis intégrés
python manage.py migrate

# 5. (optionnel) données de démonstration
python manage.py seed_demo

# 6. Lancer
python manage.py runserver
```

Ouvrir http://127.0.0.1:8000 — **démo** : `demo` / `LifeFlow-demo1` (et `demo2` / même mot de passe, pour tester l'isolation).

### MySQL sans Docker

Créer une base `utf8mb4` et un utilisateur, puis ajuster `DB_*` dans `.env` :

```sql
CREATE DATABASE lifeflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'lifeflow'@'localhost' IDENTIFIED BY 'lifeflow';
GRANT ALL PRIVILEGES ON lifeflow.* TO 'lifeflow'@'localhost';
GRANT ALL PRIVILEGES ON `test\_%`.* TO 'lifeflow'@'localhost';  -- pour les tests
```

`mysqlclient` nécessite sous Linux les en-têtes MySQL (`default-libmysqlclient-dev`, `pkg-config`).

### Frontend (facultatif)

Le CSS compilé est commité : aucune étape Node n'est nécessaire pour lancer l'application.
Pour modifier le design :

```bash
npm install
npm run build        # copie Alpine/Chart.js/polices + génère le sprite d'icônes + compile Tailwind
npm run watch:css    # recompilation à la volée pendant le développement
```

## Variables d'environnement

| Variable | Rôle | Défaut |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` / `prod` | `config.settings.dev` |
| `SECRET_KEY` | clé secrète Django (**obligatoire**) | — |
| `DEBUG` | mode debug | `True` en dev |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | hôtes autorisés (séparés par des virgules) | localhost |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | connexion MySQL | `lifeflow` … `3307` |
| `DB_ROOT_PASSWORD` | mot de passe root du conteneur MySQL | `root` |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | envoi d'e-mails (reset mot de passe) — en dev, les e-mails s'affichent dans la console | console |
| `DEFAULT_TIMEZONE` | fuseau horaire par défaut des nouveaux comptes | `UTC` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | clés Web Push (`generate_vapid_keys --write`) ; vides = push désactivé | — |
| `SITE_URL` | URL publique (liens des e-mails) | `http://127.0.0.1:8000` |
| `ANTHROPIC_API_KEY`, `ASSISTANT_MODEL` | assistant IA optionnel (sans clé : analyseur intégré) | —, `claude-opus-5-5` |

## Commandes utiles

| Commande | Effet |
|---|---|
| `python manage.py seed_demo [--reset]` | crée/recrée les comptes de démo (`is_demo=True`, jamais mélangés aux vrais comptes) |
| `python manage.py seed_templates` | (re)synchronise les modèles de défis intégrés |
| `python manage.py send_reminders` | génère les rappels dus (in-app, push, e-mail) — à planifier toutes les 5–10 min |
| `python manage.py run_scheduler` | planificateur intégré : lance les rappels en boucle (alternative à cron) |
| `python manage.py generate_vapid_keys --write` | crée les clés Web Push dans `.env` |
| `python manage.py i18n extract` / `compile` | met à jour / compile les traductions sans GNU gettext |
| `python manage.py createsuperuser` | compte administrateur (`/admin/`) |

## Tests

```bash
pip install -r requirements-dev.txt
pytest                      # 231 tests : moteur de progression, API, planner, sécurité/isolation, rapports, pages
pytest tests/test_progress_engine.py -q
```

Les tests tournent sur MySQL (base `test_lifeflow` créée automatiquement). QA navigateur facultative :

```bash
python -m playwright install chromium
python scripts/e2e_scenario.py         # scénario complet : inscription → défi → planner → suivi → rapport → PDF → isolation
python scripts/ui_screenshots.py "/dashboard/,/planner/" mobile dark
```

## Structure

```
config/              settings (base/dev/test/prod), urls, api_urls
apps/
  core/              modèles de base, audit, dates/fuseaux, middleware, template tags (design system), commandes
  accounts/          utilisateur, profil, préférences, auth, onboarding
  challenges/        défis, champs, objectifs & plannings versionnés, pauses, repos, paliers, modèles
  tracking/          entrées et valeurs typées
  planner/           activités, routines récurrentes, modèles de journée, catégories
  analytics/         services/progress (moteur de progression) + statistiques multi-défis
  dashboard/         tableau de bord, aujourd'hui, calendrier, bilan hebdo (read models)
  journal/           journal et bilans hebdomadaires
  reports/           rapports mensuels (services/, generators/pdf.py), exports
  notifications/     notifications in-app, rappels
templates/           pages et composants
static/              CSS compilé, JS (app, planner, challenges), vendor, polices, sprite d'icônes
frontend/            sources Tailwind + script de build des assets
locale/fr/           traductions françaises
docs/                documentation (14 chapitres)
tests/               suite de tests
scripts/             QA navigateur (Playwright)
```

## Documentation

1. [Vue d'ensemble](docs/01-PROJECT-OVERVIEW.md) · 2. [Architecture](docs/02-ARCHITECTURE.md) · 3. [Base de données](docs/03-DATABASE.md) ·
4. [Modèle de domaine](docs/04-DOMAIN-MODEL.md) · 5. [Moteur de défis](docs/05-CHALLENGE-ENGINE.md) · 6. [Planner](docs/06-PLANNER.md) ·
7. [Moteur de progression](docs/07-PROGRESS-ENGINE.md) · 8. [API](docs/08-API.md) · 9. [UI/UX](docs/09-UI-UX.md) ·
10. [Sécurité](docs/10-SECURITY.md) · 11. [Tests](docs/11-TESTING.md) · 12. [Rapports](docs/12-REPORTS.md) ·
13. [Déploiement](docs/13-DEPLOYMENT.md) · 14. [Feuille de route](docs/14-ROADMAP.md) ·
15. [PWA & notifications](docs/15-PWA-AND-NOTIFICATIONS.md) · 16. [Langues & RTL](docs/16-I18N-RTL.md) · 17. [Assistant IA](docs/17-AI-ASSISTANT.md)
