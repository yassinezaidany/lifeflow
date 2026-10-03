# 09 — UI / UX & design system

Direction : *Modern Productivity / Premium SaaS* — beaucoup d'espace, hiérarchie claire, cartes sobres, couleur
utilisée avec parcimonie (une couleur de marque indigo + une teinte par défi/catégorie), animations discrètes.

## Tokens (frontend/input.css + tailwind.config.js)

- Couleurs sémantiques en variables CSS (`--c-canvas`, `--c-surface`, `--c-subtle`, `--c-line`, `--c-ink`, `--c-muted`,
  `--c-faint`, `--c-brand…`, `--c-success/warning/danger`) redéfinies sous `.dark` → un seul jeu de classes pour les deux thèmes.
- **Teintes** : `tone-<couleur>` définit `--tone` / `--tone-strong` ; les composants utilisent `bg-tone/10`,
  `text-tone-strong`, `border-tone`… (12 teintes : slate, indigo, blue, sky, teal, emerald, lime, amber, orange, rose, pink, violet).
- Typographie : Inter Variable auto-hébergée ; chiffres tabulaires (`.tabular`) pour les statistiques.
- Rayons 8–18 px, ombres `shadow-card` / `shadow-pop`.

## Composants

`.btn` (primary, secondary, ghost, soft, danger, sm/lg/icon) · `.card` · `.input/.select/.textarea/.checkbox/.radio`
(+ `.is-invalid`, `.field-error`, `.hint`) · `.seg` (contrôle segmenté) · `.tile` (choix de l'assistant) · `.badge-*`
· `.bar` (barre de progression) · `{% ring %}` (anneau SVG) · `{% status_badge %}` · `.menu` (dropdown) ·
`.modal-panel` (bottom sheet sur mobile, centrée sur desktop) · `.table` · `.alert-*` · `.skeleton` · `.empty`
(états vides) · `[data-tip]` (tooltip CSS) · `.toast` · `.tl-block` (planner) · `.hm-cell` (heatmap) · `{% icon %}`.

## Navigation

Desktop : barre latérale (Tableau de bord, Aujourd'hui, Planner, Défis, Calendrier, Statistiques · Rapports, Journal,
Bilan hebdo, Modèles · Paramètres) avec bouton « Ajout rapide ». Mobile : barre inférieure Accueil · Aujourd'hui ·
**+** · Planner · Défis, avatar → profil.

## États

- **Vides** : chaque liste a un écran dédié avec action principale (« Créer votre premier défi → »).
- **Chargement** : squelettes, spinners sur les boutons, overlay du planner.
- **Retour d'action** : toasts ; après une action, la zone principale est rafraîchie sans rechargement complet.
- **Erreurs** : messages lisibles par champ ; jamais de message technique (IntegrityError, trace…). Pages 403/404/500 dédiées.

## Accessibilité

Contraste AA sur les deux thèmes, focus visible (`:focus-visible` anneau de marque), lien « Aller au contenu », labels
sur tous les champs, `aria-label` sur les boutons-icônes, modales avec piège de focus (`x-trap`) et `Échap`,
`role="dialog"`, menus clavier, déplacement des activités au clavier (Alt + flèches), `prefers-color-scheme`.

## Graphiques (Chart.js)

Courbe réalisé cumulé vs rythme attendu, barres hebdo réalisé/objectif, donut de réussite, heatmap d'activité,
anneaux de progression, barres de réussite par défi, réalisation du planning par semaine, temps par catégorie,
jours les plus actifs. Les couleurs suivent les tokens et sont reconstruites au changement de thème.
