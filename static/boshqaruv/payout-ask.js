(() => {
  'use strict';
  // Xodim javob bermagan to'lovlar: istalgan sahifada oyna chiqadi, javob shu yerning o'zida yuboriladi.
  const dialog = document.getElementById('payout-ask');
  if (!dialog) return;
  const KEY = 'ssb-payout-ask-later';
  const items = () => [...dialog.querySelectorAll('[data-pask]')];
  const ids = () => items().map(i => i.dataset.pask).sort().join(',');
  const toast = (text, level = 'success') => document.dispatchEvent(new CustomEvent('ssb:toast', { detail: { text, level } }));

  // "Keyinroq" bosilsa — oyna o'rniga kichik eslatma tugmasi turadi.
  const pill = document.createElement('button');
  pill.type = 'button'; pill.className = 'pask-pill'; pill.hidden = true;
  document.body.append(pill);
  const updatePill = () => {
    const n = items().length;
    pill.textContent = `To‘lovni tasdiqlang · ${n}`;
    pill.hidden = !n || dialog.open;
  };
  pill.addEventListener('click', () => { dialog.showModal(); updatePill(); });

  function later() {
    try { sessionStorage.setItem(KEY, ids()); } catch {}
    dialog.close();
  }

  dialog.addEventListener('click', event => {
    const item = event.target.closest('[data-pask]');
    if (event.target.closest('[data-pask-no]')) {
      item.querySelector('.pask-dispute').hidden = false;
      item.querySelector('.pask-actions').hidden = true;
      item.querySelector('textarea').focus();
    } else if (event.target.closest('[data-pask-back]')) {
      item.querySelector('.pask-dispute').hidden = true;
      item.querySelector('.pask-actions').hidden = false;
    } else if (event.target.closest('[data-pask-later]') || event.target === dialog) {
      later();
    }
  });
  dialog.addEventListener('cancel', event => { event.preventDefault(); later(); });
  dialog.addEventListener('close', updatePill);

  dialog.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target, item = form.closest('[data-pask]');
    const data = new FormData(form, event.submitter);
    form.querySelectorAll('button').forEach(b => { b.disabled = true; });
    try {
      const response = await fetch(form.action, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'X-Modal': '1', Accept: 'application/json' } });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.ok) throw Error(result.message || 'Javobni yuborib bo‘lmadi.');
      item.classList.add('is-done');
      setTimeout(() => {
        item.remove();
        if (!items().length) { dialog.close(); try { sessionStorage.removeItem(KEY); } catch {} }
        updatePill();
      }, 250);
      toast(result.message);
    } catch (error) {
      form.querySelectorAll('button').forEach(b => { b.disabled = false; });
      toast(error.message || 'Aloqa uzildi. Qayta urinib ko‘ring.', 'error');
    }
  });

  let dismissed = '';
  try { dismissed = sessionStorage.getItem(KEY) || ''; } catch {}
  // Yangi to'lov qo'shilgan bo'lsa, "Keyinroq" bekor bo'ladi va oyna qayta chiqadi.
  if (dismissed === ids()) updatePill();
  else setTimeout(() => { if (!document.querySelector('dialog[open]')) dialog.showModal(); updatePill(); }, 400);
})();
