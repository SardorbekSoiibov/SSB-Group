// Pastki tab-panel: "Bo'limlar" menyuni ochadi va qayta bosilsa yopadi; xabarlar belgisi tepadagi qo'ng'iroq bilan bir xil.
(() => {
  'use strict';
  const bar = document.querySelector('.tabbar');
  if (!bar) return;

  bar.addEventListener('click', event => {
    const sections = event.target.closest('[data-open-nav]');
    if (!sections || !document.body.classList.contains('nav-open')) return;
    event.preventDefault();
    event.stopPropagation();
    document.querySelector('.scrim[data-close-nav]')?.click();
  }, true);

  const sync = () => {
    const open = document.body.classList.contains('nav-open');
    bar.querySelector('[data-open-nav]')?.setAttribute('aria-expanded', String(open));
  };
  new MutationObserver(sync).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  sync();

  const tabBell = bar.querySelector('[data-tab-bell]');
  const bell = document.querySelector('.notification-button');
  if (tabBell && bell) {
    const mirror = () => {
      const count = bell.querySelector('b');
      const value = count && !count.hidden ? count.textContent.trim() : '';
      tabBell.textContent = value;
      tabBell.hidden = !value || value === '0';
    };
    new MutationObserver(mirror).observe(bell, { childList: true, subtree: true, characterData: true, attributes: true });
  }
})();
