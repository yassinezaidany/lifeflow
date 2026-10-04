/* LifeFlow planner: week & day time grid with drag/drop, resize and lanes for overlaps. */
(function () {
  "use strict";
  const { api, toast, t, addDays, toMin, fromMin, endMin, fmtTime, fmtMinutes, iso, parseISO } = window.LF;
  const HOUR_PX = 60;
  const PPM = HOUR_PX / 60;
  const SNAP = 15;
  const DRAG_THRESHOLD = 4;

  /** Assign side-by-side lanes to overlapping activities of one day.
   *  `carryover` = previous day's overnight activities, shown from 00:00 to their end. */
  function layout(activities, carryover = []) {
    const visible = (a) => a.status !== "rescheduled" && !(a.status === "cancelled" && a.is_recurring);
    const items = [
      ...carryover.filter(visible).map((a) => ({ a, s: 0, e: toMin(a.end_time), spill: true })),
      ...activities.filter(visible).map((a) => ({ a, s: toMin(a.start_time), e: Math.min(endMin(a.end_time, a.start_time), 1440) })),
    ].sort((x, y) => x.s - y.s || y.e - x.e);
    const out = [];
    let cluster = [], clusterEnd = -1;
    const flush = () => {
      const lanes = [];
      cluster.forEach((it) => {
        let lane = lanes.findIndex((end) => end <= it.s);
        if (lane === -1) { lane = lanes.length; lanes.push(it.e); } else lanes[lane] = it.e;
        it.lane = lane;
      });
      cluster.forEach((it) => { it.lanes = lanes.length; out.push(it); });
      cluster = [];
    };
    items.forEach((it) => {
      if (cluster.length && it.s >= clusterEnd) { flush(); clusterEnd = -1; }
      cluster.push(it);
      clusterEnd = Math.max(clusterEnd, it.e);
    });
    if (cluster.length) flush();
    return out;
  }

  document.addEventListener("alpine:init", () => {
    window.Alpine.data("planner", (opts) => ({
      mode: opts.mode || "week",
      anchor: opts.date,
      today: opts.today,
      dayStart: (opts.dayStart ?? 5) * 60,
      dayEnd: (opts.dayEnd ?? 24) * 60,
      weekdays: opts.weekdays || [],
      days: [],
      selected: opts.date,
      summary: null,
      loading: true,
      error: null,
      drag: null,
      nowMin: 0,
      templates: [],
      templatesOpen: false,
      applyDays: [],
      applyReplace: false,
      saveName: "",
      hourPx: HOUR_PX,

      init() {
        this.load();
        this.tickNow();
        setInterval(() => this.tickNow(), 60000);
        window.addEventListener("lf:planner-changed", () => this.load(false));
        this.$nextTick(() => this.scrollToNow());
      },
      tickNow() { const n = new Date(); this.nowMin = n.getHours() * 60 + n.getMinutes(); },
      get hours() {
        const list = [];
        for (let m = this.dayStart; m < this.dayEnd; m += 60) list.push(m);
        return list;
      },
      get gridHeight() { return (this.dayEnd - this.dayStart) * PPM; },
      get title() {
        if (!this.days.length) return "";
        if (this.mode === "day") return LF.fmtDate(this.days[0].date);
        const a = parseISO(this.days[0].date), b = parseISO(this.days[6].date);
        const sameMonth = a.getMonth() === b.getMonth();
        const left = a.toLocaleDateString(LF.cfg.locale, sameMonth ? { day: "numeric" } : { day: "numeric", month: "short" });
        const right = b.toLocaleDateString(LF.cfg.locale, { day: "numeric", month: "short", year: "numeric" });
        return `${left} – ${right}`;
      },
      async load(showSpinner = true) {
        if (showSpinner) this.loading = true;
        this.error = null;
        try {
          if (this.mode === "week") {
            const data = await api("/api/planner/week/", { params: { start: this.anchor } });
            this.days = data.days;
            this.summary = data.summary;
            if (!this.days.some((d) => d.date === this.selected)) {
              this.selected = this.days.some((d) => d.date === this.today) ? this.today : this.days[0].date;
            }
          } else {
            const data = await api("/api/planner/", { params: { date: this.anchor } });
            this.days = [data];
            this.summary = data.summary;
            this.selected = data.date;
          }
        } catch (e) { this.error = e.message; }
        this.loading = false;
      },
      scrollToNow() {
        const el = this.$refs.scroller;
        if (!el) return;
        const target = Math.max((Math.max(this.nowMin, this.dayStart) - this.dayStart - 90) * PPM, 0);
        el.scrollTop = target;
      },
      shift(n) {
        this.anchor = addDays(this.anchor, this.mode === "week" ? 7 * n : n);
        if (this.mode === "week") this.selected = addDays(this.selected, 7 * n);
        this.load();
        this.syncUrl();
      },
      goToday() { this.anchor = this.today; this.selected = this.today; this.load(); this.syncUrl(); this.$nextTick(() => this.scrollToNow()); },
      setMode(mode) {
        this.mode = mode;
        this.anchor = this.selected;
        this.load();
        this.syncUrl();
      },
      syncUrl() {
        const url = new URL(location.href);
        url.searchParams.set("date", this.anchor);
        url.searchParams.set("view", this.mode);
        history.replaceState(null, "", url);
      },
      blocks(day) { return layout(day.activities, day.carryover || []); },
      blockStyle(it) {
        const top = (Math.max(it.s, this.dayStart) - this.dayStart) * PPM;
        const height = Math.max((Math.min(it.e, this.dayEnd) - Math.max(it.s, this.dayStart)) * PPM - 2, 18);
        const width = 100 / it.lanes;
        return `top:${top}px;height:${height}px;left:calc(${it.lane * width}% + 2px);width:calc(${width}% - 4px)`;
      },
      visible(it) { return it.e > this.dayStart && it.s < this.dayEnd; },
      isCompact(it) { return (it.e - it.s) < 40; },
      label(it) {
        if (it.spill) return `→ ${fmtTime(it.a.end_time)}`;
        return `${fmtTime(it.a.start_time)} – ${fmtTime(it.a.end_time)}${it.a.overnight ? " (+1)" : ""}`;
      },
      dayLabel(day) {
        const d = parseISO(day.date);
        return { weekday: d.toLocaleDateString(LF.cfg.locale, { weekday: "short" }), num: d.getDate() };
      },
      nowTop() { return (this.nowMin - this.dayStart) * PPM; },
      showNow(day) { return day.date === this.today && this.nowMin >= this.dayStart && this.nowMin <= this.dayEnd; },
      hourLabel(m) { return fmtTime(fromMin(m)); },
      fmtMinutes,

      // ---- create by clicking the grid
      createAt(day, event) {
        if (this.drag && this.drag.moved) return;
        const rect = event.currentTarget.getBoundingClientRect();
        const minute = this.dayStart + Math.floor((event.clientY - rect.top) / PPM / 30) * 30;
        window.dispatchEvent(new CustomEvent("lf:activity", { detail: { date: day.date, start: Math.min(minute, 1440 - 30) } }));
      },
      open(activity) {
        window.dispatchEvent(new CustomEvent("lf:activity", { detail: { activity } }));
      },

      // ---- drag & resize
      startDrag(event, it, day, kind) {
        if (event.button !== undefined && event.button !== 0) return;
        event.stopPropagation();
        const columns = [...this.$root.querySelectorAll("[data-day-col]")];
        this.drag = {
          kind, it, a: it.a, moved: false, x0: event.clientX, y0: event.clientY,
          s0: it.s, e0: it.s + it.a.duration_minutes, spill: !!it.spill, date0: day.date, columns, pointerId: event.pointerId,
          origStart: it.a.start_time, origEnd: it.a.end_time, origDate: it.a.date,
        };
        event.currentTarget.setPointerCapture && event.currentTarget.setPointerCapture(event.pointerId);
      },
      onDrag(event) {
        const d = this.drag;
        if (!d || d.spill) return; // the after-midnight part is edited from its start day
        const dx = event.clientX - d.x0, dy = event.clientY - d.y0;
        if (!d.moved && Math.abs(dx) < DRAG_THRESHOLD && Math.abs(dy) < DRAG_THRESHOLD) return;
        d.moved = true;
        const delta = Math.round(dy / PPM / SNAP) * SNAP;
        if (d.kind === "resize") {
          const e = Math.min(Math.max(d.e0 + delta, d.s0 + SNAP), d.s0 + 1440 - SNAP);
          d.a.end_time = fromMin(e);
        } else {
          const len = d.e0 - d.s0;
          const s = Math.min(Math.max(d.s0 + delta, 0), 1440 - SNAP);
          d.a.start_time = fromMin(s);
          d.a.end_time = fromMin(s + len);
          const col = d.columns.find((c) => { const r = c.getBoundingClientRect(); return event.clientX >= r.left && event.clientX <= r.right; });
          if (col && col.dataset.dayCol !== d.a.date) this.moveBetweenDays(d.a, col.dataset.dayCol);
        }
      },
      moveBetweenDays(activity, date) {
        const from = this.days.find((x) => x.date === activity.date);
        const to = this.days.find((x) => x.date === date);
        if (!from || !to) return;
        from.activities = from.activities.filter((a) => a.id !== activity.id);
        activity.date = date;
        to.activities = [...to.activities, activity];
      },
      async endDrag() {
        const d = this.drag;
        if (!d) return;
        setTimeout(() => (this.drag = null), 0);
        if (!d.moved) { this.open(d.a); return; }
        const a = d.a;
        if (a.start_time === d.origStart && a.end_time === d.origEnd && a.date === d.origDate) return;
        try {
          const res = await api(`/api/planner/activities/${a.id}/move/`, { method: "POST", body: { date: a.date, start_time: a.start_time, end_time: a.end_time } });
          if (res.overlaps && res.overlaps.length) toast(t("Moved — overlaps %s").replace("%s", res.overlaps.map((o) => o.title).join(", ")), "warning");
          else toast(t("Activity moved"));
          await this.load(false);
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) {
          toast(e.message, "error");
          this.load(false);
        }
      },
      keyMove(event, it) {
        // Keyboard accessibility: Alt+Arrow moves by 15 min, Alt+Shift+Arrow changes the day
        if (!event.altKey) return;
        const a = it.a;
        let date = a.date, s = it.s, e = it.e;
        if (event.key === "ArrowUp") { s -= SNAP; e -= SNAP; }
        else if (event.key === "ArrowDown") { s += SNAP; e += SNAP; }
        else if (event.key === "ArrowLeft") date = addDays(date, -1);
        else if (event.key === "ArrowRight") date = addDays(date, 1);
        else return;
        event.preventDefault();
        if (s < 0 || e > 1440) return;
        api(`/api/planner/activities/${a.id}/move/`, { method: "POST", body: { date, start_time: fromMin(s), end_time: fromMin(e) } })
          .then(() => this.load(false)).catch((err) => toast(err.message, "error"));
      },

      // ---- templates
      async openTemplates() {
        this.templatesOpen = true;
        this.applyDays = [this.selected];
        try { this.templates = await api("/api/planner/templates/"); } catch (e) { toast(e.message, "error"); }
      },
      toggleApplyDay(date) {
        const set = new Set(this.applyDays);
        set.has(date) ? set.delete(date) : set.add(date);
        this.applyDays = [...set];
      },
      async applyTemplate(tpl) {
        if (!this.applyDays.length) { toast(t("Choose at least one day."), "error"); return; }
        try {
          const res = await api(`/api/planner/templates/${tpl.id}/apply/`, { method: "POST", body: { dates: this.applyDays, replace: this.applyReplace } });
          toast(t("%s activities added").replace("%s", res.created));
          this.templatesOpen = false;
          this.load(false);
          window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) { toast(e.message, "error"); }
      },
      async saveDayAsTemplate() {
        if (!this.saveName.trim()) { toast(t("Give the template a name."), "error"); return; }
        try {
          await api("/api/planner/templates/from-day/", { method: "POST", body: { date: this.selected, name: this.saveName } });
          toast(t("Template saved"));
          this.saveName = "";
          this.templates = await api("/api/planner/templates/");
        } catch (e) { toast(e.message, "error"); }
      },
    }));
  });
})();
