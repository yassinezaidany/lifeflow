/* LifeFlow — core client: API, UI services and global Alpine components. */
(function () {
  "use strict";

  const cfg = JSON.parse(document.getElementById("lf-config")?.textContent || "{}");
  const t = (key) => (cfg.i18n && cfg.i18n[key]) || key;

  // ---------------------------------------------------------------- API
  function csrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  class ApiError extends Error {
    constructor(message, status, errors) {
      super(message);
      this.status = status;
      this.errors = errors || {};
    }
  }

  async function api(url, { method = "GET", body, params } = {}) {
    if (params) {
      const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
      url += (url.includes("?") ? "&" : "?") + qs.toString();
    }
    const opts = { method, credentials: "same-origin", headers: { Accept: "application/json" } };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    if (method !== "GET") opts.headers["X-CSRFToken"] = csrfToken();
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      if (method === "POST" && isQueueable(url)) return enqueue(url, body);
      throw new ApiError(t("Network error. Check your connection."), 0);
    }
    if (res.status === 204) return null;
    let data = null;
    try { data = await res.json(); } catch (e) { /* non JSON */ }
    if (res.status === 503 && data && data.offline) {
      throw new ApiError(t("You're offline. This data isn't available on this device yet."), 0);
    }
    if (!res.ok) {
      if (res.status === 403 && !data) throw new ApiError(t("Your session expired. Please sign in again."), 403);
      const message = (data && data.detail) || t("Something went wrong. Please try again.");
      throw new ApiError(message, res.status, (data && data.errors) || {});
    }
    return data;
  }

  // ---------------------------------------------------------------- offline outbox
  // Creating entries / notes works offline: requests are queued locally and replayed
  // (with a fresh CSRF token) as soon as the connection is back.
  const OUTBOX_KEY = "lf-outbox";
  const QUEUEABLE = [/^\/api\/entries\/$/, /^\/api\/journal\/$/];
  const isQueueable = (url) => QUEUEABLE.some((re) => re.test(new URL(url, location.origin).pathname));
  const readOutbox = () => { try { return JSON.parse(localStorage.getItem(OUTBOX_KEY) || "[]"); } catch (e) { return []; } };
  const writeOutbox = (items) => {
    try { localStorage.setItem(OUTBOX_KEY, JSON.stringify(items)); } catch (e) { /* storage unavailable */ }
    window.dispatchEvent(new CustomEvent("lf:outbox", { detail: { count: items.length } }));
  };
  function enqueue(url, body) {
    const items = readOutbox();
    items.push({ id: Date.now() + "-" + Math.random().toString(36).slice(2, 7), url, body, at: new Date().toISOString() });
    writeOutbox(items);
    return { queued: true };
  }
  let flushing = false;
  async function flushOutbox() {
    if (flushing || !navigator.onLine) return;
    const items = readOutbox();
    if (!items.length) return;
    flushing = true;
    let synced = 0;
    const remaining = [];
    for (const item of items) {
      try {
        const res = await fetch(item.url, {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken() },
          body: JSON.stringify(item.body),
        });
        if (res.ok) synced++;
        else if (res.status >= 500 || res.status === 403) remaining.push(item); // retry later (server down / session to renew)
        else {
          const data = await res.json().catch(() => ({}));
          toast(`${t("An offline entry could not be saved:")} ${data.detail || res.status}`, "error");
        }
      } catch (e) { remaining.push(item); }
    }
    writeOutbox(remaining);
    flushing = false;
    if (synced) {
      toast(t("%s offline item(s) synced").replace("%s", synced));
      window.dispatchEvent(new CustomEvent("lf:changed"));
    }
  }
  window.addEventListener("online", flushOutbox);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") flushOutbox(); });

  // ---------------------------------------------------------------- PWA
  if ("serviceWorker" in navigator && window.isSecureContext) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => { /* PWA optional */ });
      flushOutbox();
    });
  }
  let deferredInstall = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstall = e;
    window.dispatchEvent(new CustomEvent("lf:installable"));
  });
  window.addEventListener("appinstalled", () => { deferredInstall = null; window.dispatchEvent(new CustomEvent("lf:installable")); });
  const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

  /** Flatten DRF errors into {field: "message"} for forms. */
  function fieldErrors(err) {
    const out = {};
    const walk = (obj, prefix) => {
      Object.entries(obj || {}).forEach(([k, v]) => {
        const key = prefix ? `${prefix}.${k}` : k;
        if (Array.isArray(v)) out[key] = v.map((x) => (typeof x === "string" ? x : JSON.stringify(x))).join(" ");
        else if (v && typeof v === "object") walk(v, key);
        else out[key] = String(v);
      });
    };
    walk(err && err.errors);
    return out;
  }

  // ---------------------------------------------------------------- helpers
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseISO = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const addDays = (s, n) => { const d = parseISO(s); d.setDate(d.getDate() + n); return iso(d); };
  const toMin = (hhmm) => { if (!hhmm) return 0; const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
  // Minutes → "HH:MM", wrapping around midnight (1440 → "00:00", 1500 → "01:00").
  const fromMin = (m) => { m = ((Math.round(m) % 1440) + 1440) % 1440; return `${pad(Math.floor(m / 60))}:${pad(m % 60)}`; };
  // End in minutes relative to the start day: an end <= start means the next day (23:00 → 07:00 = 1860).
  const endMin = (hhmm, startHHMM) => { const e = toMin(hhmm), s = startHHMM ? toMin(startHHMM) : 0; return e <= s ? e + 1440 : e; };
  const isOvernight = (start, end) => end !== "00:00" && toMin(end) <= toMin(start);
  const fmtMinutes = (total) => {
    if (total === null || total === undefined || isNaN(total)) return "—";
    total = Math.round(total);
    const h = Math.floor(total / 60), m = total % 60;
    if (h && m) return `${h}h${pad(m)}`;
    if (h) return `${h}h`;
    return `${m}min`;
  };
  const fmtTime = (hhmm) => {
    if (!hhmm || cfg.timeFormat !== "12h") return hhmm;
    let [h, m] = hhmm.split(":").map(Number);
    const ap = h >= 12 ? "PM" : "AM";
    h = h % 12 || 12;
    return `${h}:${pad(m)} ${ap}`;
  };
  const fmtDate = (s, opts = { weekday: "long", day: "numeric", month: "long" }) =>
    parseISO(s).toLocaleDateString(cfg.locale || undefined, opts);
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="${cfg.sprite}#i-${name}"></use></svg>`;

  // ---------------------------------------------------------------- toasts / confirm
  function toast(message, type = "success", action = null) {
    window.dispatchEvent(new CustomEvent("lf:toast", { detail: { message, type, action } }));
  }

  function confirmDialog(message, { title = t("Are you sure?"), confirm = t("Confirm"), danger = false } = {}) {
    return new Promise((resolve) => {
      window.dispatchEvent(new CustomEvent("lf:confirm", { detail: { message, title, confirm, danger, resolve } }));
    });
  }

  /** Re-render the server-side <main> without a full page reload (keeps scroll). */
  async function refresh() {
    const main = document.getElementById("main");
    if (!main || main.dataset.noRefresh !== undefined) return;
    try {
      const res = await fetch(location.href, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } });
      if (!res.ok) return;
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const fresh = doc.getElementById("main");
      if (fresh) {
        main.innerHTML = fresh.innerHTML;
        window.dispatchEvent(new CustomEvent("lf:refreshed"));
      }
    } catch (e) { /* ignore: data will show on next navigation */ }
  }
  window.addEventListener("lf:changed", () => refresh());

  // ---------------------------------------------------------------- theme
  function applyTheme(theme) {
    const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.dataset.theme = theme;
    window.dispatchEvent(new CustomEvent("lf:theme"));
  }
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if ((document.documentElement.dataset.theme || "system") === "system") applyTheme("system");
  });

  // ---------------------------------------------------------------- charts
  const cssVar = (name) => `rgb(${getComputedStyle(document.documentElement).getPropertyValue(name).trim()})`;
  const cssVarA = (name, a) => `rgb(${getComputedStyle(document.documentElement).getPropertyValue(name).trim()} / ${a})`;
  const TONES = {
    slate: "100 116 139", indigo: "99 102 241", blue: "59 130 246", sky: "14 165 233", teal: "20 184 166",
    emerald: "16 185 129", lime: "132 204 22", amber: "245 158 11", orange: "249 115 22", rose: "244 63 94",
    pink: "236 72 153", violet: "139 92 246",
  };
  const tone = (name, a = 1) => `rgb(${TONES[name] || TONES.indigo} / ${a})`;

  const charts = new Set();
  function chart(canvas, config) {
    if (!window.Chart || !canvas) return null;
    const build = () => {
      const c = typeof config === "function" ? config() : config;
      Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
      Chart.defaults.font.size = 11;
      Chart.defaults.color = cssVar("--c-muted");
      Chart.defaults.borderColor = cssVarA("--c-line", 0.7);
      return new Chart(canvas, c);
    };
    let instance = build();
    const entry = { canvas, rebuild() { instance.destroy(); instance = build(); } };
    charts.add(entry);
    return instance;
  }
  window.addEventListener("lf:theme", () => charts.forEach((c) => (document.body.contains(c.canvas) ? c.rebuild() : charts.delete(c))));

  const baseScales = (opts = {}) => ({
    x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 }, ...(opts.x || {}) },
    y: { beginAtZero: true, grid: { color: cssVarA("--c-line", 0.6) }, border: { display: false }, ticks: { precision: 0 }, ...(opts.y || {}) },
  });
  const tooltip = {
    backgroundColor: cssVar("--c-ink"), titleColor: cssVar("--c-surface"), bodyColor: cssVar("--c-surface"),
    padding: 10, cornerRadius: 8, displayColors: false,
  };

  // ---------------------------------------------------------------- Alpine components
  document.addEventListener("alpine:init", () => {
    const Alpine = window.Alpine;

    Alpine.data("toaster", () => ({
      items: [],
      init() {
        window.addEventListener("lf:toast", (e) => {
          const id = Math.random().toString(36).slice(2);
          this.items.push({ id, ...e.detail });
          setTimeout(() => this.dismiss(id), e.detail.type === "error" ? 6000 : 3500);
        });
      },
      dismiss(id) { this.items = this.items.filter((i) => i.id !== id); },
    }));

    Alpine.data("confirmer", () => ({
      open: false, title: "", message: "", confirmLabel: "", danger: false, resolve: null,
      init() {
        window.addEventListener("lf:confirm", (e) => {
          Object.assign(this, { ...e.detail, confirmLabel: e.detail.confirm, open: true });
        });
      },
      answer(value) { this.open = false; if (this.resolve) this.resolve(value); this.resolve = null; },
    }));

    Alpine.data("connectivity", () => ({
      online: navigator.onLine,
      pending: readOutbox().length,
      init() {
        window.addEventListener("online", () => (this.online = true));
        window.addEventListener("offline", () => (this.online = false));
        window.addEventListener("lf:outbox", (e) => (this.pending = e.detail.count));
      },
      sync() { flushOutbox(); },
    }));

    Alpine.data("installApp", () => ({
      available: !!deferredInstall,
      installed: isStandalone(),
      ios: /iphone|ipad|ipod/i.test(navigator.userAgent) && !isStandalone(),
      init() { window.addEventListener("lf:installable", () => { this.available = !!deferredInstall; this.installed = isStandalone(); }); },
      async install() {
        if (!deferredInstall) return;
        deferredInstall.prompt();
        const choice = await deferredInstall.userChoice;
        if (choice.outcome === "accepted") toast(t("LifeFlow is installed"));
        deferredInstall = null;
        this.available = false;
      },
    }));

    // Web Push on this device ------------------------------------------------------
    Alpine.data("pushToggle", () => ({
      supported: "serviceWorker" in navigator && "PushManager" in window && "Notification" in window,
      serverEnabled: false, subscribed: false, busy: false, permission: ("Notification" in window) ? Notification.permission : "denied", devices: 0, key: null,
      async init() {
        if (!this.supported) return;
        try {
          const info = await api("/api/notifications/push/key/");
          Object.assign(this, { serverEnabled: info.enabled, key: info.public_key, devices: info.devices });
          const reg = await navigator.serviceWorker.ready;
          this.subscribed = !!(await reg.pushManager.getSubscription());
        } catch (e) { /* offline or SW not ready */ }
      },
      b64ToUint8(base64) {
        const pad = "=".repeat((4 - (base64.length % 4)) % 4);
        const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
        return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
      },
      async enable() {
        this.busy = true;
        try {
          this.permission = await Notification.requestPermission();
          if (this.permission !== "granted") { toast(t("Notifications are blocked in your browser settings."), "error"); return; }
          const reg = await navigator.serviceWorker.ready;
          const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: this.b64ToUint8(this.key) });
          await api("/api/notifications/push/subscribe/", { method: "POST", body: sub.toJSON() });
          this.subscribed = true;
          this.devices += 1;
          toast(t("Notifications enabled on this device"));
        } catch (e) { toast(e.message || t("Push notifications are not available on this browser."), "error"); }
        finally { this.busy = false; }
      },
      async disable() {
        this.busy = true;
        try {
          const reg = await navigator.serviceWorker.ready;
          const sub = await reg.pushManager.getSubscription();
          if (sub) {
            await api("/api/notifications/push/unsubscribe/", { method: "POST", body: { endpoint: sub.endpoint } });
            await sub.unsubscribe();
          }
          this.subscribed = false;
          toast(t("Notifications disabled on this device"));
        } catch (e) { toast(e.message, "error"); }
        finally { this.busy = false; }
      },
      async test() {
        try { const r = await api("/api/notifications/push/test/", { method: "POST" }); if (!r.sent) toast(t("Push notifications are not available on this browser."), "error"); }
        catch (e) { toast(e.message, "error"); }
      },
    }));

    Alpine.data("themeSwitch", (initial) => ({
      theme: initial || "system",
      async set(theme) {
        this.theme = theme;
        applyTheme(theme);
        try { await api("/api/auth/me/", { method: "PATCH", body: { profile: { theme } } }); } catch (e) { /* keep local */ }
      },
    }));

    Alpine.data("notifications", () => ({
      open: false, loading: false, items: [], unread: Number(cfg.unread || 0),
      async toggle() {
        this.open = !this.open;
        if (this.open) await this.load();
      },
      async load() {
        this.loading = true;
        try { const data = await api("/api/notifications/", { params: { page_size: 8 } }); this.items = data.results; }
        catch (e) { toast(e.message, "error"); }
        this.loading = false;
      },
      async readAll() {
        await api("/api/notifications/read-all/", { method: "POST" });
        this.items.forEach((i) => (i.is_read = true));
        this.unread = 0;
      },
      async openItem(item) {
        if (!item.is_read) {
          api(`/api/notifications/${item.id}/`, { method: "PATCH", body: { is_read: true } }).catch(() => {});
          this.unread = Math.max(0, this.unread - 1);
        }
        if (item.url) location.href = item.url;
      },
      ago(ts) {
        const s = (Date.now() - new Date(ts).getTime()) / 1000;
        const rtf = new Intl.RelativeTimeFormat(cfg.locale || undefined, { numeric: "auto" });
        if (s < 3600) return rtf.format(-Math.max(1, Math.round(s / 60)), "minute");
        if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
        return rtf.format(-Math.round(s / 86400), "day");
      },
    }));

    // Quick add (+) -------------------------------------------------------------
    Alpine.data("quickAdd", () => ({
      open: false,
      choose(kind) {
        this.open = false;
        const today = cfg.today;
        if (kind === "activity") window.dispatchEvent(new CustomEvent("lf:activity", { detail: { date: today } }));
        if (kind === "task") window.dispatchEvent(new CustomEvent("lf:activity", { detail: { date: today, task: true } }));
        if (kind === "entry") window.dispatchEvent(new CustomEvent("lf:entry", { detail: {} }));
        if (kind === "note") window.dispatchEvent(new CustomEvent("lf:note", { detail: {} }));
      },
    }));

    // Record a challenge entry --------------------------------------------------
    Alpine.data("entryModal", () => ({
      open: false, loading: false, saving: false, challenges: [], challengeId: "", date: cfg.today,
      values: {}, note: "", plannedActivity: null, errors: {}, fromPlanner: false, locked: false,
      get challenge() { return this.challenges.find((c) => String(c.id) === String(this.challengeId)); },
      get fields() { return this.challenge ? this.challenge.tracking_fields.filter((f) => f.is_active) : []; },
      init() {
        window.addEventListener("lf:entry", (e) => this.show(e.detail || {}));
      },
      async show(detail) {
        this.errors = {};
        this.note = detail.note || "";
        this.date = detail.date || cfg.today;
        this.plannedActivity = detail.planned_activity || null;
        this.fromPlanner = !!detail.planned_activity;
        this.locked = !!detail.challenge_id;
        this.open = true;
        if (!this.challenges.length || detail.reload) await this.loadChallenges();
        this.challengeId = detail.challenge_id ? String(detail.challenge_id) : (this.challenges[0] ? String(this.challenges[0].id) : "");
        this.resetValues(detail.values || {});
      },
      async loadChallenges() {
        this.loading = true;
        try {
          const data = await api("/api/challenges/", { params: { status: "active", page_size: 100 } });
          this.challenges = data.results;
        } catch (e) { toast(e.message, "error"); }
        this.loading = false;
      },
      resetValues(prefill = {}) {
        const v = {};
        this.fields.forEach((f) => {
          if (prefill[f.key] !== undefined) v[f.key] = prefill[f.key];
          else v[f.key] = f.field_type === "boolean" ? (this.fields.length === 1 ? true : null) : "";
        });
        this.values = v;
      },
      durationParts(key) {
        const total = Number(this.values[key] || 0);
        return { h: Math.floor(total / 60), m: total % 60 };
      },
      setDuration(key, h, m) {
        const total = (Number(h) || 0) * 60 + (Number(m) || 0);
        this.values[key] = total || "";
      },
      async submit() {
        if (!this.challenge) return;
        this.saving = true;
        this.errors = {};
        const values = {};
        Object.entries(this.values).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) values[k] = v; });
        try {
          const result = await api("/api/entries/", {
            method: "POST",
            body: { challenge: this.challenge.id, date: this.date, values, note: this.note, planned_activity: this.plannedActivity,
                    source: this.fromPlanner ? "planner" : "quick_add" },
          });
          this.open = false;
          if (result && result.queued) {
            toast(t("Saved offline — it will sync automatically"), "warning");
          } else {
            toast(t("Progress recorded"));
            window.dispatchEvent(new CustomEvent("lf:changed"));
          }
        } catch (e) {
          this.errors = fieldErrors(e);
          if (!Object.keys(this.errors).length) toast(e.message, "error");
        }
        this.saving = false;
      },
    }));

    // Journal quick note ----------------------------------------------------------
    Alpine.data("noteModal", () => ({
      open: false, saving: false, date: cfg.today, title: "", content: "", mood: null, challenge: null, errors: {},
      init() { window.addEventListener("lf:note", (e) => { Object.assign(this, { open: true, date: e.detail.date || cfg.today, title: "", content: "", mood: null, challenge: e.detail.challenge || null, errors: {} }); }); },
      async submit() {
        this.saving = true; this.errors = {};
        try {
          const result = await api("/api/journal/", { method: "POST", body: { date: this.date, title: this.title, content: this.content, mood: this.mood, scope: this.challenge ? "challenge" : "day", challenge: this.challenge } });
          this.open = false;
          toast(result && result.queued ? t("Saved offline — it will sync automatically") : t("Note saved"), result && result.queued ? "warning" : "success");
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) { this.errors = fieldErrors(e); if (!Object.keys(this.errors).length) toast(e.message, "error"); }
        this.saving = false;
      },
    }));

    // Create / edit a planned activity ------------------------------------------
    Alpine.data("activityModal", () => ({
      open: false, saving: false, mode: "create", errors: {}, meta: null, form: {}, repeat: "none", rule: { weekdays: [], interval_days: 2, end_date: "" },
      activity: null, scope: "occurrence", panel: "edit", completeMinutes: "", rescheduleDate: "", rescheduleStart: "", rescheduleEnd: "",
      weekdayLabels: cfg.weekdays || ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
      init() { window.addEventListener("lf:activity", (e) => this.show(e.detail || {})); },
      async ensureMeta() {
        if (this.meta) return;
        const [categories, challenges] = await Promise.all([
          api("/api/planner/categories/"),
          api("/api/challenges/", { params: { status: "active", page_size: 100 } }),
        ]);
        this.meta = { categories, challenges: challenges.results };
      },
      nextSlot() {
        const now = new Date();
        const m = Math.ceil((now.getHours() * 60 + now.getMinutes()) / 15) * 15;
        return Math.min(m, 1440 - 30);
      },
      async show(detail) {
        try { await this.ensureMeta(); } catch (e) { toast(e.message, "error"); return; }
        this.errors = {};
        this.panel = "edit";
        this.scope = "occurrence";
        this.repeat = "none";
        const a = detail.activity;
        this.activity = a || null;
        if (a) {
          this.mode = "edit";
          this.form = {
            title: a.title, description: a.description || "", date: a.date, start_time: a.start_time, end_time: a.end_time,
            category_id: a.category ? a.category.id : "", challenge_id: a.challenge ? a.challenge.id : "",
            priority: a.priority, color: a.color || "", notes: a.notes || "",
          };
          this.completeMinutes = a.actual_minutes || a.duration_minutes;
          this.rescheduleDate = addDays(a.date, 1);
          this.rescheduleStart = a.start_time;
          this.rescheduleEnd = a.end_time;
        } else {
          this.mode = "create";
          const start = detail.start !== undefined ? detail.start : this.nextSlot();
          const length = detail.task ? 15 : (detail.length || 60);
          const weekday = (parseISO(detail.date || cfg.today).getDay() + 6) % 7;
          this.form = {
            title: "", description: "", date: detail.date || cfg.today, start_time: fromMin(start), end_time: fromMin(Math.min(start + length, 1440)),
            category_id: "", challenge_id: detail.challenge_id || "", priority: "medium", color: "", notes: "",
          };
          this.rule = { weekdays: [weekday], interval_days: 2, end_date: "" };
        }
        this.open = true;
        this.$nextTick(() => this.$refs.title && this.$refs.title.focus());
      },
      get duration() { return endMin(this.form.end_time, this.form.start_time) - toMin(this.form.start_time); },
      get overnight() { return isOvernight(this.form.start_time, this.form.end_time); },
      setDuration(mins) { this.form.end_time = fromMin(toMin(this.form.start_time) + mins); },
      toggleWeekday(i) {
        const set = new Set(this.rule.weekdays);
        set.has(i) ? set.delete(i) : set.add(i);
        this.rule.weekdays = [...set].sort();
      },
      payload() {
        const f = { ...this.form };
        f.category_id = f.category_id || null;
        f.challenge_id = f.challenge_id || null;
        return f;
      },
      async submit() {
        this.saving = true; this.errors = {};
        try {
          let result;
          if (this.mode === "create" && this.repeat !== "none") {
            const body = {
              ...this.payload(), start_date: this.form.date, end_date: this.rule.end_date || null,
              frequency: this.repeat, weekdays: this.repeat === "weekly" ? this.rule.weekdays : [],
              interval_days: this.repeat === "interval" ? Number(this.rule.interval_days) : 1,
            };
            delete body.date;
            await api("/api/planner/rules/", { method: "POST", body });
            toast(t("Recurring activity created"));
          } else if (this.mode === "create") {
            result = await api("/api/planner/activities/", { method: "POST", body: this.payload() });
            toast(result.overlaps && result.overlaps.length ? t("Activity added (overlaps another activity)") : t("Activity added"), result.overlaps && result.overlaps.length ? "warning" : "success");
          } else if (this.scope === "series" && this.activity.recurring_rule) {
            const body = this.payload();
            delete body.date;
            await api(`/api/planner/rules/${this.activity.recurring_rule}/`, { method: "PATCH", body });
            toast(t("Series updated"));
          } else {
            result = await api(`/api/planner/activities/${this.activity.id}/`, { method: "PATCH", body: this.payload() });
            toast(t("Activity updated"));
          }
          this.open = false;
          window.dispatchEvent(new CustomEvent("lf:planner-changed"));
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) {
          this.errors = fieldErrors(e);
          if (!Object.keys(this.errors).length) toast(e.message, "error");
        }
        this.saving = false;
      },
      async setStatus(status) {
        this.saving = true;
        try {
          const body = { status };
          if (status === "completed" || status === "partial") body.actual_minutes = this.completeMinutes || null;
          const result = await api(`/api/planner/activities/${this.activity.id}/status/`, { method: "POST", body });
          this.open = false;
          window.dispatchEvent(new CustomEvent("lf:planner-changed"));
          window.dispatchEvent(new CustomEvent("lf:changed"));
          if (result.entry_suggestion && !result.has_entry) {
            const ok = await confirmDialog(
              t("Record this activity in your challenge “%s”?").replace("%s", result.entry_suggestion.challenge_name),
              { title: t("Activity completed"), confirm: t("Review & record") },
            );
            if (ok) window.dispatchEvent(new CustomEvent("lf:entry", { detail: { ...result.entry_suggestion, reload: false } }));
          } else {
            toast(t("Status updated"));
          }
        } catch (e) { toast(e.message, "error"); }
        this.saving = false;
      },
      async reschedule() {
        this.saving = true;
        try {
          await api(`/api/planner/activities/${this.activity.id}/reschedule/`, {
            method: "POST", body: { date: this.rescheduleDate, start_time: this.rescheduleStart, end_time: this.rescheduleEnd },
          });
          this.open = false;
          toast(t("Activity rescheduled"));
          window.dispatchEvent(new CustomEvent("lf:planner-changed"));
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) { this.errors = fieldErrors(e); toast(e.message, "error"); }
        this.saving = false;
      },
      async duplicate() {
        try {
          await api(`/api/planner/activities/${this.activity.id}/duplicate/`, { method: "POST", body: { date: this.form.date } });
          this.open = false;
          toast(t("Activity duplicated"));
          window.dispatchEvent(new CustomEvent("lf:planner-changed"));
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) { toast(e.message, "error"); }
      },
      async remove() {
        const series = this.activity.recurring_rule && this.scope === "series";
        const ok = await confirmDialog(series ? t("Delete the whole series? Past activities are kept.") : t("Delete this activity?"), { danger: true, confirm: t("Delete") });
        if (!ok) return;
        try {
          if (series) await api(`/api/planner/rules/${this.activity.recurring_rule}/`, { method: "DELETE" });
          else await api(`/api/planner/activities/${this.activity.id}/`, { method: "DELETE" });
          this.open = false;
          toast(t("Deleted"));
          window.dispatchEvent(new CustomEvent("lf:planner-changed"));
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) { toast(e.message, "error"); }
      },
      recordEntry() {
        this.open = false;
        api(`/api/planner/activities/${this.activity.id}/`).then((a) => {
          window.dispatchEvent(new CustomEvent("lf:entry", { detail: {
            challenge_id: a.challenge.id, date: a.date, planned_activity: a.id,
            values: {}, note: a.notes,
          } }));
        });
      },
    }));

    // Inline actions on server-rendered pages -----------------------------------
    Alpine.data("activityRow", (activity) => ({
      activity,
      edit() { window.dispatchEvent(new CustomEvent("lf:activity", { detail: { activity: this.activity } })); },
      async quick(status) {
        try {
          const result = await api(`/api/planner/activities/${this.activity.id}/status/`, { method: "POST", body: { status } });
          window.dispatchEvent(new CustomEvent("lf:changed"));
          if (result.entry_suggestion && !result.has_entry) {
            const ok = await confirmDialog(t("Record this activity in your challenge “%s”?").replace("%s", result.entry_suggestion.challenge_name),
              { title: t("Activity completed"), confirm: t("Review & record") });
            if (ok) window.dispatchEvent(new CustomEvent("lf:entry", { detail: result.entry_suggestion }));
          } else toast(t("Status updated"));
        } catch (e) { toast(e.message, "error"); }
      },
    }));
  });

  const runQueue = () => (window.__lfq || []).forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
  document.addEventListener("DOMContentLoaded", runQueue);
  window.addEventListener("lf:refreshed", runQueue);

  window.LF = {
    cfg, t, api, ApiError, fieldErrors, toast, confirm: confirmDialog, refresh, applyTheme, flushOutbox, isStandalone,
    chart, tone, cssVar, cssVarA, baseScales, tooltip,
    iso, parseISO, addDays, toMin, fromMin, endMin, isOvernight, fmtMinutes, fmtTime, fmtDate, escapeHtml, icon, pad,
  };
})();
