(() => {
  'use strict';
  // Moliya sahifasi: "Nima qilmoqchisiz?" tugmalari alohida sahifa ochmaydi — forma shu yerda modalda ochiladi.
  const dialog = document.getElementById('fin-modal');
  if (!dialog) return;
  const body = dialog.querySelector('[data-fin-modal-body]');
  const title = dialog.querySelector('[data-fin-modal-title]');
  let busy = false;

  const loading = text => { body.innerHTML = `<div class="fin-modal-state" role="status">${text}</div>`; };
  const failed = href => {
    body.innerHTML = '<div class="fin-modal-state" role="alert"><p>Formani yuklab bo‘lmadi. Internet aloqasini tekshirib, qayta urinib ko‘ring.</p></div>';
    if (href) {
      const a = document.createElement('a');
      a.className = 'button compact'; a.href = href; a.textContent = 'Alohida sahifada ochish';
      body.firstElementChild.append(a);
    }
  };

  function mount(html) {
    body.innerHTML = html;
    window.SSBOperation?.init(body);
    window.SSBPayout?.init(body);
    document.dispatchEvent(new CustomEvent('ssb:formready', { detail: { root: body } }));
    body.querySelector('.form-alert, .field.invalid')?.scrollIntoView({ block: 'center' });
  }

  let token = 0;
  async function open(href, label) {
    const mine = ++token;
    title.textContent = label || 'Moliyaviy amal';
    loading('Forma yuklanmoqda…');
    if (!dialog.open) dialog.showModal();
    try {
      const response = await fetch(href, { credentials: 'same-origin', headers: { 'X-Modal': '1' } });
      if (response.redirected && !response.url.includes('/finance/')) { location.href = response.url; return; }
      if (!response.ok) throw Error(response.status);
      const html = await response.text();
      if (mine === token && dialog.open) mount(html);
    } catch {
      if (mine === token) failed(href);
    }
  }

  document.addEventListener('click', event => {
    const link = event.target.closest('a[data-fin-modal]');
    if (!link || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    open(link.href, link.dataset.finModal);
  });

  // Forma yuborilganda: muvaffaqiyat bo'lsa sahifa yangilanadi (xabar chiqadi), xato bo'lsa modal ichida ko'rsatiladi.
  body.addEventListener('submit', async event => {
    if (event.defaultPrevented) return;
    const form = event.target;
    event.preventDefault();
    if (busy) return;
    busy = true;
    const buttons = [...form.querySelectorAll('button[type=submit], button:not([type])')];
    buttons.forEach(b => { b.disabled = true; });
    form.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(form.action, { method: 'POST', body: new FormData(form, event.submitter), credentials: 'same-origin', headers: { 'X-Modal': '1' } });
      if (!response.ok) throw Error(response.status);
      if ((response.headers.get('content-type') || '').includes('application/json')) {
        const data = await response.json();
        dialog.close();
        const target = new URL(data.redirect, location.href);
        // Moliya sahifasidan tashqarida (masalan, loyiha sahifasida) — o'sha sahifa yangilanadi, foydalanuvchi joyida qoladi.
        if (!location.pathname.includes('/enterprise/finance/')) location.reload();
        else if (target.pathname === location.pathname && target.search === location.search) location.reload();
        else location.assign(target);
        return;
      }
      form.closest('dialog.payout-dialog')?.close();
      mount(await response.text());
    } catch {
      const note = document.createElement('p');
      note.className = 'form-alert'; note.setAttribute('role', 'alert');
      note.textContent = 'Saqlab bo‘lmadi: aloqa uzildi. Kiritilgan ma’lumotlar saqlanib qoldi — qayta urinib ko‘ring.';
      form.prepend(note);
      buttons.forEach(b => { b.disabled = false; });
    } finally {
      busy = false;
      form.removeAttribute('aria-busy');
    }
  });

  dialog.addEventListener('click', event => {
    if (event.target === dialog || event.target.closest('[data-fin-modal-close]')) dialog.close();
  });
  // Yopilgach tozalanadi; agar shu orada qayta ochilgan bo'lsa — yangi formaga tegilmaydi.
  dialog.addEventListener('close', () => { if (!dialog.open) { token++; body.innerHTML = ''; } });
})();
