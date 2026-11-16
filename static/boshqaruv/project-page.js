(() => {
  'use strict';
  // Loyiha sahifasi: bo'limlar (tablar), holatni tasdiqlash oynasi va bosqichlarni sahifani yangilamasdan boshqarish.
  const toast = (text, level = 'success') => document.dispatchEvent(new CustomEvent('ssb:toast', { detail: { text, level } }));

  // ---------------------------------------------------------------- bo'limlar
  const tabs = [...document.querySelectorAll('.pc-tabs [data-pc-tab]')];
  const panes = [...document.querySelectorAll('[data-pc-pane]')];
  const fallback = document.querySelector('.pc-tabs')?.dataset.default || 'bosqichlar';
  function show(name, scroll) {
    if (!panes.some(p => p.dataset.pcPane === name)) name = fallback;
    tabs.forEach(t => { const on = t.dataset.pcTab === name; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; });
    panes.forEach(p => { p.hidden = p.dataset.pcPane !== name; });
    if (location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
    if (scroll) document.querySelector('.pc-tabs')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }
  document.addEventListener('click', event => {
    const t = event.target.closest('[data-pc-tab]');
    if (!t) return;
    event.preventDefault();
    show(t.dataset.pcTab, !t.closest('.pc-tabs'));
  });
  tabs.forEach((t, i) => t.addEventListener('keydown', event => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    const next = tabs[(i + step + tabs.length) % tabs.length];
    show(next.dataset.pcTab); next.focus();
  }));
  if (tabs.length) show((location.hash || '#' + fallback).slice(1));

  // ---------------------------------------------------------------- holatni o'zgartirish
  const dialog = document.getElementById('pc-confirm');
  if (dialog) {
    const note = dialog.querySelector('textarea[name=comment]');
    const submit = dialog.querySelector('[data-pc-submit]');
    const blocked = dialog.querySelector('[data-pc-blocked]');
    document.addEventListener('click', event => {
      const btn = event.target.closest('[data-pc-action]');
      if (!btn) return;
      dialog.querySelector('[data-pc-to]').value = btn.dataset.pcAction;
      dialog.querySelector('[data-pc-title]').textContent = btn.dataset.label;
      dialog.querySelector('[data-pc-effect]').textContent = btn.dataset.effect || '';
      const needs = btn.dataset.needsComment === '1';
      note.required = needs; note.minLength = needs ? 5 : 0; note.value = '';
      dialog.querySelector('[data-pc-note-label]').textContent = needs ? 'Sabab (majburiy)' : 'Izoh (ixtiyoriy)';
      const reasons = btn.dataset.blocked || '';
      blocked.hidden = !reasons;
      blocked.textContent = reasons ? `Hozircha yakunlab bo‘lmaydi: ${reasons}. Avval bosqichlarni bajarilgan deb belgilang.` : '';
      submit.disabled = Boolean(reasons);
      submit.className = 'button ' + (btn.classList.contains('danger') ? 'danger' : 'primary');
      submit.textContent = btn.dataset.label;
      dialog.showModal();
      (needs ? note : submit).focus();
    });
    dialog.querySelector('[data-pc-cancel]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
    dialog.querySelector('form').addEventListener('submit', () => { submit.disabled = true; });
  }

  // ---------------------------------------------------------------- bosqichlar
  const list = document.querySelector('[data-pc-steps]');
  const empty = document.querySelector('[data-pc-steps-empty]');
  const setProgress = (progress, done, total) => {
    document.querySelectorAll('[data-pc-progress]').forEach(n => { n.textContent = progress + '%'; });
    document.querySelectorAll('[data-pc-bar]').forEach(n => { n.style.width = progress + '%'; });
    if (done != null) document.querySelectorAll('[data-pc-done]').forEach(n => { n.textContent = done; });
    if (total != null) document.querySelectorAll('[data-pc-total]').forEach(n => { n.textContent = total; });
    const tab = document.querySelector('.pc-tabs [data-pc-tab="bosqichlar"] b');
    if (tab && done != null && total != null) tab.textContent = `${done}/${total}`;
  };
  const counts = () => {
    const items = [...(list?.children || [])];
    return [items.filter(li => li.classList.contains('is-done')).length, items.length];
  };
  const post = (form, data) => fetch(form.action, {
    method: 'POST', body: data || new FormData(form), credentials: 'same-origin', headers: { Accept: 'application/json' },
  }).then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok || !j.ok) throw Error(j.error || 'Saqlab bo‘lmadi.'); return j; });

  document.addEventListener('submit', async event => {
    const toggle = event.target.closest('form[data-pc-toggle]');
    if (!toggle) return;
    event.preventDefault();
    const li = toggle.closest('li'), btn = toggle.querySelector('button');
    btn.disabled = true;
    try {
      const j = await post(toggle);
      li.classList.toggle('is-done', j.done);
      li.querySelector('small').textContent = j.done ? 'Bajarilgan' : 'Bajarilmagan';
      btn.setAttribute('aria-label', j.done ? 'Qayta ochish' : 'Bajarildi deb belgilash');
      setProgress(j.progress, j.done_count, j.total);
      if (j.done_count === j.total && j.total) toast('Barcha bosqichlar bajarildi — loyihani tekshiruvga topshirish mumkin.');
    } catch (error) { toast(error.message, 'error'); }
    finally { btn.disabled = false; }
  });

  const add = document.querySelector('form[data-pc-add]');
  add?.addEventListener('submit', async event => {
    event.preventDefault();
    const input = add.querySelector('input[name=title]'), title = input.value.trim();
    if (!title) { input.focus(); return; }
    const btn = add.querySelector('button'); btn.disabled = true;
    try {
      const j = await post(add);
      // Yangi qator: belgilash tugmasi bilan; o'chirish tugmasi sahifa yangilanganda paydo bo'ladi (parol talab qilinadi).
      const li = document.createElement('li');
      const form = document.createElement('form');
      form.method = 'post'; form.action = j.toggle_url; form.dataset.pcToggle = '';
      form.innerHTML = add.querySelector('input[name=csrfmiddlewaretoken]').outerHTML
        + '<button class="project-step-check" aria-label="Bajarildi deb belgilash">' + (document.querySelector('[data-pc-check-icon]')?.innerHTML || '✓') + '</button>';
      const text = document.createElement('div');
      text.innerHTML = '<strong></strong><small>Bajarilmagan</small>';
      text.querySelector('strong').textContent = j.title;
      li.append(form, text);
      list.append(li);
      if (empty) empty.hidden = true;
      input.value = ''; input.focus();
      const [done, total] = counts();
      setProgress(j.progress, done, total);
    } catch (error) { toast(error.message, 'error'); }
    finally { btn.disabled = false; }
  });
})();
