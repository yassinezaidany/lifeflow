/* LifeFlow challenges: creation wizard + settings editor. */
(function () {
  "use strict";
  const { api, toast, t, fieldErrors, addDays, confirm } = window.LF;

  const MEASURES = {
    check: { fields: [{ ref: "primary", label: "Done", field_type: "boolean", unit: "" }], goal: { period: "daily", aggregation: "count", target: 1 } },
    number: { fields: [{ ref: "primary", label: "Amount", field_type: "integer", unit: "pages" }], goal: { period: "daily", aggregation: "sum", target: 10 } },
    duration: { fields: [{ ref: "primary", label: "Duration", field_type: "duration", unit: "" }], goal: { period: "daily", aggregation: "sum", target: 30 } },
    sessions: { fields: [], goal: { period: "weekly", aggregation: "count", target: 3 } },
    decimal: { fields: [{ ref: "primary", label: "Distance", field_type: "decimal", unit: "km" }], goal: { period: "weekly", aggregation: "sum", target: 10 } },
  };

  const newField = () => ({ ref: "f" + Math.random().toString(36).slice(2, 8), label: "", field_type: "text", unit: "", options: [], optionsText: "", required: false });

  document.addEventListener("alpine:init", () => {
    window.Alpine.data("challengeWizard", (opts) => ({
      step: 1,
      steps: opts.steps,
      saving: false,
      errors: {},
      categories: opts.categories,
      icons: opts.icons,
      colors: opts.colors,
      weekdayLabels: opts.weekdays,
      measure: "",
      duration: "30",
      form: {
        name: "", description: "", category: opts.categories.length ? opts.categories[0].id : null, icon: "target", color: "indigo",
        fields: [], metric: null,
        goal: { period: "daily", aggregation: "sum", target: 1, min_per_entry: null },
        schedule: { frequency: "daily", weekdays: [0, 2, 4], interval_days: 2 },
        start_date: opts.today, end_date: addDays(opts.today, 29), milestones: [], template: null,
      },
      init() {
        const tpl = opts.template;
        if (tpl) this.applyTemplate(tpl);
        this.$watch("duration", () => this.syncEnd());
        this.$watch("form.start_date", () => this.syncEnd());
      },
      applyTemplate(tpl) {
        const def = tpl.definition || {};
        Object.assign(this.form, { name: tpl.name, description: tpl.description || "", icon: tpl.icon || "target", color: tpl.color || "indigo", template: tpl.id || null });
        const cat = this.categories.find((c) => c.name.toLowerCase() === (tpl.category_name || "").toLowerCase());
        if (cat) this.form.category = cat.id;
        this.form.fields = (def.fields || []).map((f) => ({ ...newField(), ...f, ref: f.key || f.label, optionsText: (f.options || []).join(", ") }));
        this.form.metric = def.goal && def.goal.metric ? def.goal.metric : null;
        if (def.goal) this.form.goal = { min_per_entry: null, ...def.goal };
        if (def.schedule) this.form.schedule = { weekdays: [0, 2, 4], interval_days: 2, ...def.schedule };
        if (tpl.duration_days) { this.duration = String(tpl.duration_days); }
        this.measure = "custom";
        this.syncEnd();
      },
      syncEnd() {
        if (this.duration === "open") this.form.end_date = null;
        else if (this.duration !== "custom") this.form.end_date = addDays(this.form.start_date, Number(this.duration) - 1);
      },
      chooseMeasure(kind) {
        this.measure = kind;
        if (kind === "custom") { if (!this.form.fields.length) this.form.fields = [{ ...newField(), ref: "primary", label: "Value", field_type: "integer" }]; this.form.metric = this.form.fields[0].ref; return; }
        const m = MEASURES[kind];
        const extras = this.form.fields.filter((f) => f.ref !== "primary");
        this.form.fields = [...m.fields.map((f) => ({ ...newField(), ...f, label: t(f.label), unit: f.unit ? t(f.unit) : "" })), ...extras];
        this.form.metric = m.fields.length ? "primary" : null;
        this.form.goal = { ...this.form.goal, ...m.goal, min_per_entry: null };
      },
      get primary() { return this.form.fields.find((f) => f.ref === this.form.metric) || null; },
      get measurableFields() { return this.form.fields.filter((f) => ["boolean", "integer", "decimal", "duration"].includes(f.field_type) && f.label.trim()); },
      get unitLabel() {
        const p = this.primary;
        if (!p) return t("sessions");
        if (p.field_type === "boolean") return t("days");
        if (this.form.goal.aggregation === "count") return t("sessions");
        if (p.field_type === "duration") return t("minutes");
        return p.unit || "";
      },
      get canUseMinimum() { const p = this.primary; return p && ["integer", "decimal", "duration"].includes(p.field_type); },
      get goalSentence() {
        const per = { daily: t("per day"), weekly: t("per week"), monthly: t("per month"), total: t("in total") }[this.form.goal.period];
        let target = this.form.goal.target;
        if (this.primary && this.primary.field_type === "duration" && this.form.goal.aggregation === "sum") target = LF.fmtMinutes(Number(target));
        else target = `${target} ${this.unitLabel}`;
        let s = `${target} ${per}`;
        if (this.form.goal.min_per_entry && this.canUseMinimum) s += ` · ${t("min.")} ${this.form.goal.min_per_entry} ${this.primary.field_type === "duration" ? "min" : this.primary.unit} ${t("per entry")}`;
        return s;
      },
      get scheduleSentence() {
        const s = this.form.schedule;
        if (s.frequency === "daily") return t("Every day");
        if (s.frequency === "weekdays") return s.weekdays.map((d) => this.weekdayLabels[d]).join(", ") || "—";
        return t("Every %s days").replace("%s", s.interval_days);
      },
      get categoryName() { const c = this.categories.find((c) => c.id === this.form.category); return c ? c.name : "—"; },
      toggleWeekday(i) {
        const set = new Set(this.form.schedule.weekdays);
        set.has(i) ? set.delete(i) : set.add(i);
        this.form.schedule.weekdays = [...set].sort();
      },
      addField() { this.form.fields.push(newField()); },
      removeField(i) {
        const f = this.form.fields[i];
        this.form.fields.splice(i, 1);
        if (this.form.metric === f.ref) this.form.metric = this.measurableFields.length ? this.measurableFields[0].ref : null;
      },
      addMilestones() {
        const total = Number(this.form.goal.target);
        if (this.form.goal.period === "total" && total > 0) {
          this.form.milestones = [25, 50, 75, 100].map((p) => ({ title: `${p}%`, target_value: Math.round(total * p / 100 * 100) / 100 }));
        } else this.form.milestones.push({ title: "", target_value: "" });
      },
      validateStep() {
        this.errors = {};
        if (this.step === 1 && !this.form.name.trim()) this.errors.name = t("Give your challenge a name.");
        if (this.step === 2 && !this.measure) this.errors.measure = t("Choose what you want to measure.");
        if (this.step === 2) this.form.fields.forEach((f, i) => { if (!f.label.trim()) this.errors[`field_${i}`] = t("Name this field."); });
        if (this.step === 3 && !(Number(this.form.goal.target) > 0)) this.errors.target = t("The target must be greater than zero.");
        if (this.step === 4 && this.form.schedule.frequency === "weekdays" && !this.form.schedule.weekdays.length) this.errors.weekdays = t("Select at least one day.");
        if (this.step === 5 && this.form.end_date && this.form.end_date < this.form.start_date) this.errors.end_date = t("End date must be on or after the start date.");
        return !Object.keys(this.errors).length;
      },
      next() { if (this.validateStep()) { this.step = Math.min(this.step + 1, this.steps.length); window.scrollTo({ top: 0, behavior: "smooth" }); } },
      back() { this.step = Math.max(this.step - 1, 1); },
      goTo(n) { if (n < this.step) this.step = n; },
      payload() {
        const f = this.form;
        return {
          name: f.name, description: f.description, category: f.category, icon: f.icon, color: f.color, template: f.template,
          start_date: f.start_date, end_date: f.end_date || null,
          fields: f.fields.map((x) => ({
            ref: x.ref, key: x.key || "", label: x.label, field_type: x.field_type, unit: x.field_type === "duration" ? "" : (x.unit || ""), required: !!x.required,
            options: x.field_type === "select" ? (x.optionsText || "").split(",").map((o) => o.trim()).filter(Boolean) : [],
          })),
          goal: { metric: f.metric, period: f.goal.period, aggregation: f.goal.aggregation, target: f.goal.target, min_per_entry: this.canUseMinimum ? (f.goal.min_per_entry || null) : null },
          schedule: { frequency: f.schedule.frequency, weekdays: f.schedule.weekdays, interval_days: Number(f.schedule.interval_days) || 1 },
          milestones: f.milestones.filter((m) => m.title && Number(m.target_value) > 0),
        };
      },
      async submit() {
        this.saving = true;
        this.errors = {};
        try {
          const created = await api("/api/challenges/", { method: "POST", body: this.payload() });
          toast(t("Challenge created"));
          location.href = opts.next || `/challenges/${created.id}/`;
        } catch (e) {
          this.errors = fieldErrors(e);
          toast(e.message, "error");
          this.saving = false;
        }
      },
    }));

    // ------------------------------------------------------------------ settings
    window.Alpine.data("challengeSettings", (opts) => ({
      c: opts.challenge,
      categories: opts.categories,
      icons: opts.icons,
      colors: opts.colors,
      weekdayLabels: opts.weekdays,
      today: opts.today,
      errors: {},
      saving: "",
      general: {},
      goal: {},
      schedule: {},
      newField: null,
      milestone: { title: "", target_value: "" },
      init() { this.reset(); },
      reset() {
        const c = this.c;
        this.general = { name: c.name, description: c.description, category_id: c.category ? c.category.id : null, icon: c.icon, color: c.color, start_date: c.start_date, end_date: c.end_date, reminder_time: c.reminder_time ? c.reminder_time.slice(0, 5) : "" };
        const g = c.goal || {};
        this.goal = { metric: g.metric_key || "", period: g.period || "daily", aggregation: g.aggregation || "count", target: g.target || 1, min_per_entry: g.min_per_entry, effective_from: this.today < c.start_date ? c.start_date : this.today };
        const s = c.schedule || {};
        this.schedule = { frequency: s.frequency || "daily", weekdays: s.weekdays || [], interval_days: s.interval_days || 2, effective_from: this.goal.effective_from };
      },
      get activeFields() { return this.c.tracking_fields.filter((f) => f.is_active); },
      get measurable() { return this.activeFields.filter((f) => ["boolean", "integer", "decimal", "duration"].includes(f.field_type)); },
      get metricField() { return this.activeFields.find((f) => f.key === this.goal.metric); },
      toggleWeekday(i) {
        const set = new Set(this.schedule.weekdays);
        set.has(i) ? set.delete(i) : set.add(i);
        this.schedule.weekdays = [...set].sort();
      },
      async run(section, fn, message) {
        this.saving = section; this.errors = {};
        try { const r = await fn(); if (r && r.id) this.c = r; this.reset(); toast(message || t("Saved")); }
        catch (e) { this.errors = fieldErrors(e); toast(e.message, "error"); }
        this.saving = "";
      },
      saveGeneral() {
        return this.run("general", () => api(`/api/challenges/${this.c.id}/`, { method: "PATCH", body: { ...this.general, end_date: this.general.end_date || null, reminder_time: this.general.reminder_time || null } }));
      },
      saveGoal() {
        return this.run("goal", () => api(`/api/challenges/${this.c.id}/goal/`, { method: "PUT", body: { ...this.goal, metric: this.goal.metric || null, min_per_entry: this.goal.min_per_entry || null } }),
          t("Goal updated — earlier days keep the previous goal"));
      },
      saveSchedule() {
        return this.run("schedule", () => api(`/api/challenges/${this.c.id}/schedule/`, { method: "PUT", body: this.schedule }), t("Schedule updated"));
      },
      startField() { this.newField = { label: "", field_type: "integer", unit: "", optionsText: "", required: false }; },
      async addField() {
        const f = this.newField;
        await this.run("field", async () => {
          await api(`/api/challenges/${this.c.id}/fields/`, { method: "POST", body: { ...f, options: f.optionsText.split(",").map((o) => o.trim()).filter(Boolean) } });
          this.newField = null;
          return api(`/api/challenges/${this.c.id}/`);
        }, t("Field added"));
      },
      async toggleRequired(field) {
        await this.run("field", async () => {
          await api(`/api/challenges/${this.c.id}/fields/${field.id}/`, { method: "PATCH", body: { required: !field.required } });
          return api(`/api/challenges/${this.c.id}/`);
        });
      },
      async renameField(field, label) {
        if (!label.trim() || label === field.label) return;
        await this.run("field", async () => {
          await api(`/api/challenges/${this.c.id}/fields/${field.id}/`, { method: "PATCH", body: { label } });
          return api(`/api/challenges/${this.c.id}/`);
        }, t("Field renamed"));
      },
      async removeField(field) {
        if (!(await confirm(t("Remove this field? Recorded values are kept in history."), { danger: true, confirm: t("Remove") }))) return;
        await this.run("field", async () => {
          await api(`/api/challenges/${this.c.id}/fields/${field.id}/`, { method: "DELETE" });
          return api(`/api/challenges/${this.c.id}/`);
        }, t("Field removed"));
      },
      async addMilestone() {
        await this.run("milestone", async () => {
          await api(`/api/challenges/${this.c.id}/milestones/`, { method: "POST", body: this.milestone });
          this.milestone = { title: "", target_value: "" };
          location.reload();
        }, t("Milestone added"));
      },
      async removeMilestone(id) {
        await api(`/api/challenges/${this.c.id}/milestones/`, { method: "DELETE", body: { id } });
        location.reload();
      },
      async setStatus(status) {
        await this.run("status", () => api(`/api/challenges/${this.c.id}/status/`, { method: "POST", body: { status } }), t("Status updated"));
        location.reload();
      },
      async destroy() {
        if (!(await confirm(t("Delete this challenge and all its entries? This cannot be undone. Archiving keeps your history."), { danger: true, confirm: t("Delete forever") }))) return;
        try { await api(`/api/challenges/${this.c.id}/`, { method: "DELETE" }); location.href = "/challenges/"; }
        catch (e) { toast(e.message, "error"); }
      },
      async duplicate() {
        try { const r = await api(`/api/challenges/${this.c.id}/duplicate/`, { method: "POST", body: { start_date: this.today, end_date: null } }); location.href = `/challenges/${r.id}/settings/`; }
        catch (e) { toast(e.message, "error"); }
      },
    }));

    // ------------------------------------------------------------------ entries table actions
    window.Alpine.data("entryActions", (entry) => ({
      async remove() {
        if (!(await confirm(t("Delete this entry?"), { danger: true, confirm: t("Delete") }))) return;
        try { await api(`/api/entries/${entry}/`, { method: "DELETE" }); toast(t("Entry deleted")); window.dispatchEvent(new CustomEvent("lf:changed")); }
        catch (e) { toast(e.message, "error"); }
      },
    }));

    window.Alpine.data("entryEditor", (entry, fields) => ({
      open: false, saving: false, errors: {}, date: entry.date, note: entry.note, values: { ...entry.values }, fields,
      async save() {
        this.saving = true; this.errors = {};
        try {
          await api(`/api/entries/${entry.id}/`, { method: "PUT", body: { date: this.date, note: this.note, values: this.values } });
          this.open = false; toast(t("Entry updated")); window.dispatchEvent(new CustomEvent("lf:changed"));
        } catch (e) { this.errors = fieldErrors(e); toast(e.message, "error"); }
        this.saving = false;
      },
    }));
  });
})();
