(() => {
  'use strict';
  // "Xodimga pul berish" formasi: alohida sahifada ham, moliya sahifasidagi modalda ham ishlaydi.
  function init(root) {
    const form = root.querySelector('#payout-form');
    const dialog = root.querySelector('#payout-summary');
    if (!form || !dialog || form.dataset.bound) return;
    form.dataset.bound = '1';
    const inModal = Boolean(form.closest('.fin-modal'));
    const baseUrl = form.getAttribute('action') || location.pathname;
    const field = name => form.elements[name];
    const label = name => {
      const el = field(name);
      if (!el) return '';
      if (el.tagName === 'SELECT') return el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : '';
      return el.value;
    };
    const review = form.querySelector('[data-payout-review]');
    const amountBox = field('amount').closest('.field') || field('amount').parentElement;
    const warn = document.createElement('p');
    warn.className = 'field-error payout-limit'; warn.setAttribute('role', 'alert'); warn.hidden = true;
    amountBox.append(warn);
    const aside = () => root.querySelector('#payout-aside');
    const fmt = n => Number(n).toLocaleString('ru-RU', { maximumFractionDigits: 2 }).replace(/,/g, '.');

    // Summa qarzdan oshsa — darhol ogohlantirish (server ham baribir tekshiradi).
    const limit = () => {
      const box = aside();
      if (!box || !box.dataset.employee || box.dataset.employee !== field('employee').value) return null;
      let max = Number(box.dataset.payable || 0);
      const project = field('project').value;
      if (project) {
        const row = box.querySelector(`.payout-pick[data-project="${project}"]`);
        max = Math.min(max, row ? Number(row.dataset.amount) : 0);
      }
      return Math.max(0, max);
    };
    const check = () => {
      const max = limit(), amount = Number(field('amount').value || 0);
      let text = '';
      if (max !== null && max <= 0) text = field('project').value
        ? (Number(aside().dataset.payable || 0) > 0
            ? 'Tanlangan loyihadan bu xodimga to‘lanadigan pul qolmagan. Loyihani o‘zgartiring yoki o‘ngdagi ro‘yxatdan qarzni tanlang.'
            : 'Bu loyihadan xodimga hali pul hisoblanmagan: loyiha yakunlanib tasdiqlanmagan yoki mijoz to‘lovi qayd etilmagan.')
        : `Bu xodimga ${field('currency').value} da to‘lanadigan pul yo‘q. Avval ish haqi, mukofot yoki loyiha ulushi hisoblanishi kerak.`;
      else if (max !== null && amount > max) text = `Summa qarzdan oshmoqda. Ko‘pi bilan ${fmt(max)} ${field('currency').value} to‘lash mumkin.`;
      warn.textContent = text; warn.hidden = !text;
      field('amount').toggleAttribute('aria-invalid', Boolean(text));
      review.disabled = Boolean(text);
    };

    // Xodim yoki valyuta o'zgarsa — faqat qarz paneli va ro'yxat yangilanadi, kiritilgan ma'lumotlar saqlanadi.
    let pending;
    const refresh = async () => {
      const params = new URLSearchParams();
      ['employee', 'currency'].forEach(name => { if (field(name).value) params.set(name, field(name).value); });
      const url = baseUrl.split('?')[0] + '?' + params;
      if (!inModal) history.replaceState(null, '', url);
      pending?.abort(); pending = new AbortController();
      aside()?.classList.add('is-loading');
      try {
        const response = await fetch(url, { credentials: 'same-origin', signal: pending.signal, headers: { 'X-Modal': '1' } });
        if (!response.ok) throw Error();
        const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
        const fresh = doc.getElementById('payout-aside'), options = doc.querySelector('#payout-form [name=employee]');
        if (fresh) aside().replaceWith(fresh);
        if (options) {
          const value = field('employee').value;
          field('employee').replaceChildren(...[...options.options].map(o => o.cloneNode(true)));
          field('employee').value = value;
        }
        bind(); check();
      } catch (error) {
        if (error.name !== 'AbortError' && !inModal) location.href = url;
      } finally { aside()?.classList.remove('is-loading'); }
    };
    const bind = () => {
      root.querySelectorAll('.payout-pick').forEach(button => button.addEventListener('click', () => {
        field('project').value = button.dataset.project;
        field('amount').value = button.dataset.amount;
        root.querySelectorAll('.payout-pick').forEach(b => b.classList.toggle('is-picked', b === button));
        check(); field('amount').focus();
      }));
      root.querySelectorAll('[data-switch-currency]').forEach(button => button.addEventListener('click', () => {
        field('currency').value = button.dataset.switchCurrency; refresh();
      }));
    };
    ['employee', 'currency'].forEach(name => field(name).addEventListener('change', refresh));
    ['input', 'change'].forEach(type => { field('amount').addEventListener(type, check); field('project').addEventListener(type, check); });
    bind(); check();

    review.addEventListener('click', () => {
      check();
      if (review.disabled) return;
      const confirmBox = dialog.querySelector('[name=transfer_confirmed]');
      confirmBox.required = false;
      const valid = form.reportValidity();
      confirmBox.required = true;
      if (!valid) return;
      const amount = Number(field('amount').value || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }).replace(/,/g, '.');
      const values = {
        employee: label('employee'), project: label('project'), amount: amount + ' ' + field('currency').value,
        paid_on: field('paid_on').value.split('-').reverse().join('.'), method: label('method'), description: field('description').value,
        reference: [field('reference').value, field('proof').files.length ? field('proof').files[0].name : ''].filter(Boolean).join(' · ') || '—',
      };
      dialog.querySelectorAll('[data-sum]').forEach(node => { node.textContent = values[node.dataset.sum] || '—'; });
      confirmBox.checked = false;
      dialog.showModal();
    });
    dialog.querySelector('[data-payout-cancel]').addEventListener('click', () => dialog.close());
    form.addEventListener('submit', event => {
      if (!dialog.open) { event.preventDefault(); review.click(); }
    });
  }
  window.SSBPayout = { init };
  if (!document.querySelector('.fin-modal #payout-form')) init(document);
})();
