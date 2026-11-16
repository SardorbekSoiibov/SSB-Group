(() => {
  'use strict';
  const form = document.querySelector('#financial-report-filters'); if (!form) return;
  const select = form.querySelector('[name=report]'), start = form.querySelector('[name=dan]'), end = form.querySelector('[name=gacha]');
  function update() {
    const allTime = ['outstanding','profitability'].includes(select.value);
    start.disabled = allTime; document.querySelector('#report-date-hint').hidden = !allTime;
    if (allTime) end.removeAttribute('min'); else end.min = start.value;
  }
  select.addEventListener('change',update);start.addEventListener('change',update);update();

  // Tezkor davr tugmalari: sanalarni to'ldiradi va hisobotni darhol qayta hisoblaydi.
  const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const ranges = {
    'month': t => [new Date(t.getFullYear(), t.getMonth(), 1), t],
    'last-month': t => [new Date(t.getFullYear(), t.getMonth() - 1, 1), new Date(t.getFullYear(), t.getMonth(), 0)],
    'quarter': t => [new Date(t.getFullYear(), Math.floor(t.getMonth() / 3) * 3, 1), t],
    'year': t => [new Date(t.getFullYear(), 0, 1), t],
    'last-year': t => [new Date(t.getFullYear() - 1, 0, 1), new Date(t.getFullYear() - 1, 11, 31)],
    'all': t => [new Date(2000, 0, 1), t],
  };
  const presets = document.querySelectorAll('.report-presets [data-range]');
  const mark = () => presets.forEach(b => {
    const [a, z] = ranges[b.dataset.range](new Date());
    b.classList.toggle('primary', start.value === iso(a) && end.value === iso(z));
  });
  presets.forEach(button => button.addEventListener('click', () => {
    const [a, z] = ranges[button.dataset.range](new Date());
    start.value = iso(a); end.value = iso(z); update();
    form.requestSubmit ? form.requestSubmit() : form.submit();
  }));
  mark();
})();
