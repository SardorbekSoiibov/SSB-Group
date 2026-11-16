// Browsers cannot truly stop a screenshot. For accounts without permission this makes one hard and traceable:
// the page hides while another tool has focus, Print Screen is answered at once, and every view carries a name mark.
// The Windows app uses real OS-level capture protection instead, so this file is not loaded there.
(() => {
  'use strict';
  const mark = document.body.dataset.captureMark || '';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="180"><text x="20" y="100" transform="rotate(-24 150 90)" fill="#888" font-family="sans-serif" font-size="15">${mark.replace(/[<&"]/g, '')}</text></svg>`;
  const layer = document.createElement('div');
  layer.className = 'capture-mark'; layer.setAttribute('aria-hidden', 'true');
  layer.style.backgroundImage = `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
  const veil = document.createElement('div');
  veil.className = 'capture-veil'; veil.textContent = 'Skrinshot olish uchun ruxsat yo‘q'; veil.hidden = true;
  document.body.append(layer, veil);
  const hide = () => { veil.hidden = false; };
  const show = () => { veil.hidden = true; };
  window.addEventListener('blur', hide);
  window.addEventListener('focus', show);
  document.addEventListener('visibilitychange', () => { document.hidden ? hide() : show(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'PrintScreen' || (event.metaKey && event.shiftKey)) hide();
  });
  document.addEventListener('keyup', event => {
    if (event.key !== 'PrintScreen') return;
    hide(); navigator.clipboard?.writeText('').catch(() => {});
    setTimeout(show, 1500);
  });
})();
