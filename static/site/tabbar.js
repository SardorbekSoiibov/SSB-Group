// Pastki tab-panel: bosh sahifada ekranda turgan bo'limga mos tabni faol qiladi.
// Bosilganda aylantirishni ios.js ([data-scroll]) bajaradi — yangi sahifa ochilmaydi.
(() => {
  'use strict';
  const bar = document.querySelector('[data-site-tabbar]');
  if (!bar) return;
  const tabs = [...bar.querySelectorAll('[data-tab-section]')];
  const sections = tabs
    .map(tab => ({ tab, el: tab.dataset.tabSection === 'top' ? null : document.getElementById(tab.dataset.tabSection) }))
    .filter(item => item.tab.dataset.tabSection === 'top' || item.el);
  if (sections.length < 2) return; // boshqa sahifa: bo'limlar yo'q, server belgilagan holat qoladi

  let lock = 0;
  const setActive = tab => tabs.forEach(t => t === tab ? t.setAttribute('aria-current', 'page') : t.removeAttribute('aria-current'));

  function update() {
    if (Date.now() < lock) return;
    const line = innerHeight * 0.45;
    let current = sections[0].tab;
    for (const { tab, el } of sections) {
      if (el && el.getBoundingClientRect().top <= line) current = tab;
    }
    // Sahifa oxiriga yetganda — oxirgi bo'lim (Aloqa)
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) current = sections[sections.length - 1].tab;
    setActive(current);
  }

  let frame = 0;
  addEventListener('scroll', () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; update(); }); }, { passive: true });
  addEventListener('resize', update);

  // Bosilgan tab darhol faol bo'ladi; silliq aylanish tugaguncha kuzatuv to'xtab turadi
  bar.addEventListener('click', event => {
    const tab = event.target.closest('[data-tab-section]');
    if (!tab) return;
    setActive(tab);
    lock = Date.now() + 900;
    setTimeout(update, 950);
  });

  update();
})();
