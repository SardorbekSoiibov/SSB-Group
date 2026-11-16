(() => {
  'use strict';
  // Qo'llanma modali: "?" tugmasi ochadi, lavozim tugmalari yo'riqnomalarni almashtiradi.
  const dialog = document.getElementById('guide-dialog');
  if (!dialog) return;
  const tabs = [...dialog.querySelectorAll('[data-guide-tab]')];
  const panels = [...dialog.querySelectorAll('[data-guide-panel]')];
  const body = dialog.querySelector('.guide-body');
  const KEY = 'ssb-guide-tab';

  function select(name, focus) {
    if (!panels.some(p => p.dataset.guidePanel === name)) name = dialog.dataset.defaultTab;
    tabs.forEach(tab => {
      const on = tab.dataset.guideTab === name;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;
      if (on) { tab.scrollIntoView({ block: 'nearest', inline: 'nearest' }); if (focus) tab.focus(); }
    });
    panels.forEach(panel => { panel.hidden = panel.dataset.guidePanel !== name; });
    body.scrollTop = 0;
    try { sessionStorage.setItem(KEY, name); } catch {}
  }

  function open(event) {
    event?.preventDefault();
    document.querySelectorAll('details[open]').forEach(d => d.removeAttribute('open'));
    let name = dialog.dataset.defaultTab;
    try { name = sessionStorage.getItem(KEY) || name; } catch {}
    if (!dialog.open) dialog.showModal();
    select(name);
  }

  document.addEventListener('click', event => { if (event.target.closest('[data-open-guide]')) open(event); });
  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => select(tab.dataset.guideTab));
    tab.addEventListener('keydown', event => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      select(tabs[(i + step + tabs.length) % tabs.length].dataset.guideTab, true);
    });
  });
  dialog.addEventListener('click', event => {
    if (event.target === dialog || event.target.closest('[data-guide-close]')) dialog.close();
  });
  // ?qollanma manzili bilan kelinsa — darhol ochiladi (masalan, yangi xodimga havola yuborish uchun).
  if (new URLSearchParams(location.search).has('qollanma')) open();
})();
