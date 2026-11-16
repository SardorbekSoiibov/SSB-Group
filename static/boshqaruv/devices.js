(() => {
  'use strict';
  // Brauzer saqlangan loginni sidebar qidiruviga avtomatik yozib qo'ymasin: foydalanuvchi o'zi yozmagan matn tozalanadi.
  const search = document.getElementById('sidebar-search');
  if (search) {
    let typed = false;
    ['keydown', 'paste', 'drop'].forEach(t => search.addEventListener(t, () => { typed = true; }));
    const guard = () => {
      if (!typed && search.value) { search.value = ''; search.dispatchEvent(new Event('input', { bubbles: true })); }
    };
    search.addEventListener('input', e => { if (!e.inputType && !typed) guard(); });
    search.addEventListener('focus', guard);
    window.addEventListener('pageshow', () => { typed = false; guard(); });
    [0, 300, 1000, 2500].forEach(ms => setTimeout(guard, ms));
  }
})();

(() => {
  'use strict';
  // "Qurilmalar" — modal oyna. Ro'yxat va chiqarish natijasi serverdan HTML bo'lib keladi.
  const dialog = document.getElementById('devices-dialog');
  if (!dialog) return;
  const box = dialog.querySelector('.dv-content');
  const url = box.dataset.devicesUrl;
  let busy = false;

  const show = html => { box.innerHTML = html; };
  const fail = text => show(`<div class="dv-loading" role="alert">${text}<br><button type="button" class="button compact" data-devices-close>Yopish</button></div>`);

  async function load(request) {
    busy = true;
    try {
      const response = await fetch(request.url, { credentials: 'same-origin', cache: 'no-store', ...request.init,
        headers: { 'X-Requested-With': 'fetch', ...(request.init?.headers || {}) } });
      if (response.redirected || response.status === 401 || response.status === 403) { location.reload(); return; }
      if (!response.ok) throw Error(String(response.status));
      show(await response.text());
    } catch {
      fail('Qurilmalar ro‘yxatini yuklab bo‘lmadi. Internetni tekshirib, qayta urinib ko‘ring.');
    } finally { busy = false; }
  }

  function open(event) {
    event?.preventDefault();
    document.querySelectorAll('details.account-menu[open]').forEach(d => d.removeAttribute('open'));
    show('<div class="dv-loading" role="status">Qurilmalar yuklanmoqda…</div>');
    if (!dialog.open) dialog.showModal();
    load({ url });
  }

  document.addEventListener('click', event => {
    const trigger = event.target.closest('[data-open-devices]');
    if (trigger) open(event);
  });
  dialog.addEventListener('click', event => {
    if (event.target === dialog || event.target.closest('[data-devices-close]')) dialog.close();
  });
  dialog.addEventListener('submit', event => {
    const form = event.target.closest('[data-devices-action]');
    if (!form) return;
    event.preventDefault();
    if (busy) return;
    const button = form.querySelector('button');
    // "Barchasidan chiqish" — ikki bosqichli tasdiq (brauzerning confirm oynasisiz).
    if (form.dataset.confirmText && form.dataset.armed !== '1') {
      form.dataset.armed = '1';
      button.classList.add('is-armed');
      button.lastChild.textContent = ' Tasdiqlash uchun yana bosing';
      setTimeout(() => { if (form.isConnected) { form.dataset.armed = ''; button.classList.remove('is-armed'); } }, 5000);
      return;
    }
    button.disabled = true;
    load({ url: form.action, init: { method: 'POST', body: new FormData(form) } });
  });
  // Profil sahifasidan ?qurilmalar=1 bilan kelinsa — darhol ochiladi.
  if (new URLSearchParams(location.search).has('qurilmalar')) open();
})();
