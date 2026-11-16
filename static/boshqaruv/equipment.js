(() => {
  'use strict';
  document.querySelectorAll('[data-eq-open]').forEach(b => b.addEventListener('click', () => {
    const d = document.getElementById(b.dataset.eqOpen);
    if (d && !d.open) d.showModal();
  }));
  document.querySelectorAll('.eq-dialog').forEach(d => {
    d.querySelectorAll('[data-eq-close]').forEach(b => b.addEventListener('click', () => d.close()));
    d.addEventListener('click', e => { if (e.target === d) d.close(); });
    if (d.hasAttribute('data-open-on-load')) d.showModal();
  });
  // Qidiruv: yozishdan to'xtagach avtomatik filtrlash
  const search = document.querySelector('.eq-search input');
  let t;
  search?.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => search.form.submit(), 500); });
})();
