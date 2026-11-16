/* SSB Group ommaviy sayt — iOS uslubidagi interaktivlik.
   Menyu bo'limlarga aylantiradi (manzil satri o'zgarmaydi), 3D sahna sichqoncha va
   aylantirishga javob beradi, kartalar egiladi, bo'limlar ko'rinishga kirganda paydo bo'ladi.
   Matn tugunlari bo'linmaydi — til almashtirgich to'liq gaplarni tarjima qila oladi. */

/* Alpine komponentlari (shablonlar shu nomlar bilan chaqiradi) */
function ssbPublicShell() {
  return {menu: false};
}

/* Bosh sahifadagi loyiha brifi (4 qadam). Maydon nomlari InquiryForm bilan bir xil. */
function ssbBrief() {
  return {
    step: 0,
    sending: false,
    service: "",
    budget: "",
    method: "",
    desc: "",
    name: "",
    contact: "",
    init() {
      const checked = this.$root.querySelector("input[name=preferred_method]:checked");
      if (checked) this.method = checked.dataset.label;
    },
    get descOk() { return this.desc.trim().length >= 20; },
    get contactOk() { return this.name.trim().length >= 2 && this.contact.trim().length >= 5; },
    get ready() { return this.descOk && this.contactOk; },
    get progress() { return [this.service, this.budget, this.descOk, this.contactOk].filter(Boolean).length * 25; },
    get canNext() { return Boolean([this.service, this.budget, this.descOk][this.step]); },
    done(i) { return Boolean([this.service, this.budget, this.descOk, this.contactOk][i]); },
    go(i) {
      if (i < 0 || i > 3) return;
      for (let k = 0; k < i; k++) if (!this.done(k)) return;
      this.step = i;
      this.$nextTick(() => {
        const field = this.$root.querySelector(i === 2 ? "#brief-desc" : i === 3 ? "#brief-name" : null);
        if (field) field.focus({preventScroll: true});
      });
    },
    pick(key, el) {
      this[key] = el.dataset.label;
      if (key !== "method") setTimeout(() => this.go(this.step + 1), 280);
    },
    preselect(pk) {
      const input = this.$root.querySelector(`input[name=service][value="${pk}"]`);
      if (!input) return;
      input.checked = true;
      this.service = input.dataset.label;
      this.step = this.budget ? 2 : 1;
    },
    hasTag(tag) { return this.desc.includes(tag); },
    toggleTag(tag) {
      const safe = tag.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      if (this.hasTag(tag)) this.desc = this.desc.replace(new RegExp(`(,\\s*)?${safe}`), "").replace(/^,\s*/, "").trim();
      else this.desc = this.desc.trim() ? `${this.desc.trim()}, ${tag}` : tag;
      this.$refs.desc.focus({preventScroll: true});
    },
  };
}

(function () {
  "use strict";
  const root = document.documentElement;
  const reduceQuery = matchMedia("(prefers-reduced-motion: reduce)");
  const reduce = () => reduceQuery.matches;
  const fine = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const onScroll = (fn) => {
    let queued = false;
    const run = () => { queued = false; fn(); };
    addEventListener("scroll", () => { if (!queued) { queued = true; requestAnimationFrame(run); } }, {passive: true});
    addEventListener("resize", () => { if (!queued) { queued = true; requestAnimationFrame(run); } }, {passive: true});
    fn();
  };
  const headerOffset = () => {
    const h = document.querySelector(".topbar");
    return h ? h.getBoundingClientRect().bottom + 16 : 90;
  };

  /* ---- Menyu: faqat aylantirish */
  function scrollToSection(id, smooth = true) {
    const target = id && document.getElementById(id);
    if (!target) return false;
    const y = target.getBoundingClientRect().top + scrollY - headerOffset() + 4;
    scrollTo({top: Math.max(0, y), behavior: smooth && !reduce() ? "smooth" : "auto"});
    return true;
  }

  function initScrollNav() {
    document.addEventListener("click", (e) => {
      const link = e.target.closest("[data-scroll]");
      if (!link || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
      const id = link.dataset.scroll;
      if (!document.getElementById(id)) return; // boshqa sahifada: bosh sahifaga o'tadi
      e.preventDefault();
      document.dispatchEvent(new CustomEvent("ssb:close-menu"));
      scrollToSection(id);
      link.blur();
    });
    document.addEventListener("click", (e) => {
      const a = e.target.closest('a[href^="#"]');
      if (!a || a.hasAttribute("data-scroll") || e.defaultPrevented) return;
      const id = decodeURIComponent(a.getAttribute("href").slice(1));
      if (!id || !document.getElementById(id)) return;
      e.preventDefault();
      scrollToSection(id);
    });
    if (location.hash) {
      const id = decodeURIComponent(location.hash.slice(1));
      if (document.getElementById(id)) {
        history.replaceState(null, "", location.pathname + location.search);
        const go = () => scrollToSection(id, false);
        addEventListener("ssb:loaded", () => setTimeout(go, 30), {once: true});
        (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => setTimeout(go, 60));
      }
    }
  }

  /* ---- Menyu indikatori (suzuvchi "pill") va joriy bo'lim */
  function initNavIndicator() {
    const nav = document.querySelector(".topbar-nav");
    if (!nav) return;
    const pill = nav.querySelector(".topbar-pill");
    const links = [...nav.querySelectorAll("[data-scroll]")];
    let current = null;
    const moveTo = (el) => {
      if (!pill) return;
      if (!el) { pill.style.opacity = "0"; return; }
      pill.style.opacity = "1";
      pill.style.width = `${el.offsetWidth}px`;
      pill.style.transform = `translateX(${el.offsetLeft}px)`;
    };
    links.forEach((a) => {
      a.addEventListener("mouseenter", () => moveTo(a));
      a.addEventListener("focus", () => moveTo(a));
    });
    nav.addEventListener("mouseleave", () => moveTo(current));
    const sections = links.map((a) => document.getElementById(a.dataset.scroll)).filter(Boolean);
    if (!sections.length) { addEventListener("resize", () => moveTo(current)); return; }
    onScroll(() => {
      const line = headerOffset() + innerHeight * 0.2;
      let active = null, best = -Infinity;
      for (const s of sections) {
        const r = s.getBoundingClientRect();
        if (r.top <= line && r.top > best && r.bottom > headerOffset()) { best = r.top; active = s; }
      }
      const link = active ? links.find((a) => a.dataset.scroll === active.id) : null;
      if (link !== current) {
        links.forEach((a) => a.toggleAttribute("aria-current", a === link));
        current = link;
      }
      if (!nav.matches(":hover")) moveTo(current);
    });
  }

  /* ---- Yuqori panel holati va aylantirish progressi */
  function initHeader() {
    const bar = document.querySelector(".scroll-progress i");
    onScroll(() => {
      root.classList.toggle("scrolled", scrollY > 24);
      if (bar) {
        const max = root.scrollHeight - innerHeight;
        bar.style.transform = `scaleX(${max > 0 ? Math.min(1, scrollY / max) : 0})`;
      }
    });
  }

  /* ---- Mobil menyu (sheet) */
  function initMobileMenu() {
    const btn = document.querySelector("[data-menu-toggle]");
    const panel = document.getElementById("mobile-sheet");
    if (!btn || !panel) return;
    const set = (open) => {
      root.classList.toggle("menu-open", open);
      btn.setAttribute("aria-expanded", String(open));
      btn.setAttribute("aria-label", open ? "Yopish" : "Menyuni ochish");
      panel.toggleAttribute("inert", !open);
      panel.setAttribute("aria-hidden", String(!open));
    };
    set(false);
    btn.addEventListener("click", () => set(!root.classList.contains("menu-open")));
    document.addEventListener("ssb:close-menu", () => set(false));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && root.classList.contains("menu-open")) { set(false); btn.focus(); } });
    document.addEventListener("click", (e) => {
      if (!root.classList.contains("menu-open")) return;
      if (e.target.closest("a") && panel.contains(e.target)) { set(false); return; }
      if (!panel.contains(e.target) && !btn.contains(e.target)) set(false);
    });
    addEventListener("resize", () => { if (innerWidth > 980) set(false); });
  }

  /* ---- Paydo bo'lish */
  function initReveal() {
    const items = () => [...document.querySelectorAll("[data-reveal]:not(.is-in), [data-stagger] > *:not(.is-in)")];
    if (reduce() || !("IntersectionObserver" in window)) { items().forEach((el) => el.classList.add("is-in")); return; }
    const number = (scope) => scope.querySelectorAll("[data-stagger]").forEach((g) => [...g.children].forEach((c, i) => c.style.setProperty("--i", i % 6)));
    number(document);
    root.classList.add("motion");
    const io = new IntersectionObserver((entries) => entries.forEach((en) => {
      if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
    }), {rootMargin: "0px 0px -6% 0px", threshold: 0.06});
    items().forEach((el) => io.observe(el));
    document.addEventListener("htmx:afterSwap", (e) => {
      number(e.target);
      requestAnimationFrame(() => items().forEach((el) => io.observe(el)));
    });
  }

  /* ---- 3D egilish (kartalar) + yorug'lik dog'i */
  function initTilt() {
    if (!fine) return;
    let frame = 0, card = null, ev = null;
    const reset = (c) => { c.classList.remove("is-tilting"); c.style.removeProperty("--rx"); c.style.removeProperty("--ry"); };
    document.addEventListener("pointermove", (e) => {
      if (reduce()) return;
      const c = e.target.closest && e.target.closest("[data-tilt]");
      if (card && card !== c) reset(card);
      card = c; ev = e;
      if (!card || frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        if (!card) return;
        const r = card.getBoundingClientRect();
        const x = (ev.clientX - r.left) / r.width - 0.5;
        const y = (ev.clientY - r.top) / r.height - 0.5;
        const max = Number(card.dataset.tilt) || 6;
        card.style.setProperty("--rx", `${(-y * max).toFixed(2)}deg`);
        card.style.setProperty("--ry", `${(x * max).toFixed(2)}deg`);
        card.style.setProperty("--mx", `${((x + 0.5) * 100).toFixed(1)}%`);
        card.style.setProperty("--my", `${((y + 0.5) * 100).toFixed(1)}%`);
        card.classList.add("is-tilting");
      });
    }, {passive: true});
    document.addEventListener("pointerout", (e) => {
      if (card && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest("[data-tilt]") === card)) { reset(card); card = null; }
    });
  }

  /* ---- "Biz haqimizda" matni aylantirish bilan yorishadi (matn bo'linmaydi) */
  function initStatement() {
    const el = document.querySelector("[data-statement]");
    if (!el) return;
    onScroll(() => {
      if (reduce()) { el.style.setProperty("--p", "100%"); return; }
      const r = el.getBoundingClientRect();
      const p = Math.min(1, Math.max(0, (innerHeight * 0.82 - r.top) / (r.height + innerHeight * 0.3)));
      el.style.setProperty("--p", `${(p * 100).toFixed(1)}%`);
    });
  }

  /* ---- Hero: 3D sahna sichqoncha, aylantirish va qurilma og'ishiga javob beradi */
  function initHero() {
    const hero = document.querySelector("[data-hero]");
    if (!hero) return;
    const stage = hero.querySelector(".hero-stage");
    const world = hero.querySelector("[data-hero-stage]");
    const title = hero.querySelector("[data-hero-title]");
    const ready = () => { hero.classList.add("is-ready"); title && title.classList.add("is-in"); };
    const go = () => requestAnimationFrame(ready);
    if (root.classList.contains("ssb-loading")) addEventListener("ssb:loaded", go, {once: true});
    else go();
    setTimeout(ready, 5200);
    if (!world) return;
    const base = {rx: 10, ry: -18};
    let px = 0, py = 0, tx = 0, ty = 0, raf = 0, visible = true;
    const apply = () => {
      raf = 0;
      if (reduce()) { world.style.setProperty("--rx", `${base.rx}deg`); world.style.setProperty("--ry", `${base.ry}deg`); return; }
      px += (tx - px) * 0.08; py += (ty - py) * 0.08;
      const h = hero.offsetHeight || innerHeight;
      const p = Math.min(1, Math.max(0, scrollY / (h * 0.9)));
      world.style.setProperty("--rx", `${(base.rx + p * 14 - py * 8).toFixed(2)}deg`);
      world.style.setProperty("--ry", `${(base.ry * (1 - p * 0.6) + px * 14).toFixed(2)}deg`);
      world.style.setProperty("--lift", `${(-p * 60).toFixed(1)}px`);
      if (Math.abs(tx - px) > 0.002 || Math.abs(ty - py) > 0.002) raf = requestAnimationFrame(apply);
    };
    const kick = () => { if (!raf && visible) raf = requestAnimationFrame(apply); };
    if ("IntersectionObserver" in window) new IntersectionObserver(([en]) => { visible = en.isIntersecting; if (visible) kick(); }).observe(hero);
    if (fine && stage) {
      hero.addEventListener("pointermove", (e) => {
        const r = hero.getBoundingClientRect();
        tx = ((e.clientX - r.left) / r.width) * 2 - 1;
        ty = ((e.clientY - r.top) / r.height) * 2 - 1;
        stage.classList.add("is-pointer");
        kick();
      }, {passive: true});
      hero.addEventListener("pointerleave", () => { tx = 0; ty = 0; stage.classList.remove("is-pointer"); kick(); });
    }
    addEventListener("scroll", kick, {passive: true});
    addEventListener("resize", kick);
    reduceQuery.addEventListener?.("change", kick);
    kick();
  }

  /* ---- Tugmalar: barmoq bosilganda iOS kabi yengil "haptic" (faqat qo'llab-quvvatlanadigan qurilmalarda) */
  function initHaptics() {
    if (!("vibrate" in navigator) || fine) return;
    document.addEventListener("click", (e) => { if (e.target.closest(".btn-filled, .segmented button, .chip-option, .option")) { try { navigator.vibrate(8); } catch {} } }, {passive: true});
  }

  function start() {
    initHero();
    initScrollNav();
    initNavIndicator();
    initHeader();
    initMobileMenu();
    initReveal();
    initTilt();
    initStatement();
    initHaptics();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

/* Murojaat faqat server qabul qilgandan keyin tasdiqlanadi (iOS alert uslubida). */
(() => {
  if (!document.body.classList.contains("site") || !window.fetch || !window.HTMLDialogElement) return;
  const busy = new WeakSet();
  function showSuccess(form) {
    const dialog = document.createElement("dialog");
    dialog.className = "inquiry-success";
    dialog.setAttribute("aria-labelledby", "inquiry-success-title");
    dialog.innerHTML = '<div class="inquiry-success-inner"><span class="inquiry-success-icon" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m8 16.5 5.5 5.5L25 10"/></svg></span><p class="inquiry-success-label">SSB GROUP</p><h2 id="inquiry-success-title">Murojaatingiz qabul qilindi</h2><p>Rahmat! Bir ish kuni ichida siz bilan bog‘lanamiz.</p></div><button type="button" class="inquiry-success-close">Tushunarli</button>';
    document.body.append(dialog);
    const close = () => { dialog.close(); dialog.remove(); form.querySelector('input[name="name"]')?.focus({preventScroll: true}); };
    dialog.querySelector("button").addEventListener("click", close);
    dialog.addEventListener("cancel", (e) => { e.preventDefault(); close(); });
    dialog.showModal();
    dialog.querySelector("button").focus();
  }
  function alertBox(form, text) {
    const alert = document.createElement("div");
    alert.dataset.inquiryErrors = "true"; alert.className = "inquiry-error"; alert.setAttribute("role", "alert"); alert.tabIndex = -1;
    alert.textContent = text;
    (form.querySelector(".brief-body") || form).prepend(alert);
    alert.focus();
  }
  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || new URL(form.action, location.href).pathname !== "/aloqa/") return;
    event.preventDefault();
    if (busy.has(form)) return;
    busy.add(form);
    const buttons = [...form.querySelectorAll('[type="submit"]')];
    buttons.forEach((b) => (b.disabled = true));
    form.querySelectorAll("[data-inquiry-errors]").forEach((n) => n.remove());
    try {
      const response = await fetch(form.action, {method: "POST", body: new FormData(form), credentials: "same-origin", headers: {Accept: "text/html"}});
      if (response.ok && new URL(response.url).pathname === "/aloqa/rahmat/") {
        form.reset();
        const state = window.Alpine?.$data(form);
        if (state) { state.sending = false; if ("step" in state) { state.step = 0; for (const k of ["service", "budget", "method", "desc", "name", "contact"]) state[k] = ""; const m = form.querySelector("input[name=preferred_method]:checked"); if (m) state.method = m.dataset.label || ""; } }
        showSuccess(form);
      } else {
        const page = new DOMParser().parseFromString(await response.text(), "text/html");
        const errors = [...page.querySelectorAll('[role="alert"],.errorlist,.field-error')].map((n) => n.textContent.trim()).filter(Boolean);
        alertBox(form, errors.length ? [...new Set(errors)].join(" ") : "Murojaat yuborilmadi. Ma’lumotlarni tekshirib, qayta urinib ko‘ring.");
      }
    } catch {
      alertBox(form, "Aloqa uzildi. Murojaat yuborilganini tekshirib, qayta urinib ko‘ring.");
    } finally {
      busy.delete(form);
      buttons.forEach((b) => (b.disabled = false));
      const state = window.Alpine?.$data(form);
      if (state) state.sending = false;
    }
  }, true);
})();
