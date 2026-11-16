(() => {
  'use strict';
  // Moliyaviy amal formasi: alohida sahifada ham, moliya sahifasidagi modalda ham ishlaydi.
  function init(root) {
  const form = root.querySelector('#op-form');
  if (!form || form.dataset.bound) return;
  form.dataset.bound = '1';
  const inModal = Boolean(form.closest('.fin-modal'));
  const $ = name => form.elements[name];
  const box = name => form.querySelector(`.field[data-field="${name}"]`);
  const agreements = JSON.parse(root.querySelector('#op-agreements')?.textContent || '{}');
  const preview = root.querySelector('[data-op-preview]');
  const title = root.querySelector('[data-op-title]');
  const help = root.querySelector('[data-op-help]');
  const submit = root.querySelector('[data-op-submit]');
  const cards = [...root.querySelectorAll('.op-kinds [data-kind]')];

  // Har bir amal turi: qaysi maydonlar kerak, summa yorlig'i, tushuntirish.
  const KINDS = {
    agreement: {
      title: 'Loyiha kelishuvi', button: 'Kelishuvni saqlash',
      fields: ['project', 'amount', 'currency', 'company_percent', 'eligible', 'distribution', 'description'],
      required: ['project'], amount: 'Shartnoma summasi (mijoz jami qancha to‘laydi)',
      help: 'Loyiha boshida bir marta kiritiladi. Mijozdan keladigan har bir to‘lov shu foizlar bo‘yicha bo‘linadi.',
    },
    receipt: {
      title: 'Mijozdan pul keldi', button: 'Tushumni saqlash',
      fields: ['project', 'amount', 'currency', 'description'],
      required: ['project'], amount: 'Mijozdan kelgan summa',
      help: 'Mijoz pul to‘laganda kiriting (to‘liq yoki qisman). Pul kelishuvdagi ulushlarga avtomatik bo‘linadi.',
    },
    salary: {
      title: 'Ish haqi hisoblash', button: 'Ish haqini saqlash',
      fields: ['employee', 'amount', 'currency', 'description'], required: ['employee'], amount: 'Ish haqi summasi',
      help: 'Xodimga oylik yoziladi (u «to‘lanishi kerak» bo‘ladi). Pulni bergach — «Xodimga pul berish» orqali qayd eting.',
    },
    bonus: {
      title: 'Mukofot', button: 'Mukofotni saqlash',
      fields: ['employee', 'amount', 'currency', 'description'], required: ['employee'], amount: 'Mukofot summasi',
      help: 'Xodimga bonus yoziladi. Pulni bergach — «Xodimga pul berish» orqali qayd eting.',
    },
    expense: {
      title: 'Kompaniya xarajati', button: 'Xarajatni saqlash',
      fields: ['amount', 'currency', 'project', 'description'], required: [], amount: 'Xarajat summasi',
      help: 'Ijara, internet, xarid kabi kompaniya chiqimlari. Kassadan chiqim bo‘lib yoziladi va foydadan ayriladi.',
    },
    correction: {
      title: 'Tuzatish', button: 'Tuzatishni saqlash',
      fields: ['correction_entry', 'amount', 'currency', 'description'], required: ['correction_entry'], amount: 'Qaytariladigan (kamaytiriladigan) summa',
      help: 'Reyestrdagi xato yozuvni kamaytiradi. Yozuv ID sini reyestrdagi yozuvni ochib nusxa oling. Asl yozuv o‘chirilmaydi.',
    },
  };
  const ALL = ['project', 'employee', 'amount', 'currency', 'company_percent', 'eligible', 'distribution', 'correction_entry', 'description'];
  const amountLabel = box('amount')?.querySelector('label');
  const amountLabelText = amountLabel ? amountLabel.firstChild : null;
  if (box('kind')) box('kind').hidden = true;
  if (box('description')) {
    const d = $('description');
    d.placeholder = 'Masalan: Kardly loyihasi, 1-to‘lov, bank o‘tkazmasi №123';
  }

  const num = v => Number(String(v || '').replace(/\s/g, '').replace(',', '.')) || 0;
  const fmt = n => Number(n).toLocaleString('ru-RU', { maximumFractionDigits: 2 }).replace(/,/g, '.');
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const row = (label, value, cls = '') => `<li class="${cls}"><span>${esc(label)}</span><strong>${value}</strong></li>`;

  function setKind(kind) {
    if (!KINDS[kind]) kind = 'receipt';
    const k = KINDS[kind];
    $('kind').value = kind;
    cards.forEach(c => c.setAttribute('aria-checked', String(c.dataset.kind === kind)));
    ALL.forEach(name => { const el = box(name); if (el) el.hidden = !k.fields.includes(name); });
    ALL.forEach(name => {
      const el = $(name);
      if (el && 'required' in el) el.required = k.fields.includes(name) && (k.required.includes(name) || name === 'amount' || name === 'description');
      // Yashirilgan maydon qiymati serverga yuborilmasin (masalan, kelishuvdan qolgan xodim tanlovi).
      if (el && 'disabled' in el) el.disabled = !k.fields.includes(name);
    });
    if (amountLabelText) amountLabelText.textContent = k.amount;
    title.textContent = k.title; help.textContent = k.help; submit.textContent = k.button;
    if (!inModal) { const url = new URL(location.href); url.searchParams.set('kind', kind); history.replaceState(null, '', url); }
    update();
  }

  function sharesFromForm() {
    const company = num($('company_percent')?.value);
    try {
      const custom = JSON.parse($('distribution')?.value || '[]');
      if (Array.isArray(custom) && custom.length) {
        const names = new Map([...($('eligible')?.options || [])].map(o => [o.value, o.textContent.split(' · ')[0]]));
        return { company, shares: custom.map(s => ({ name: names.get(String(s.employee)) || 'Xodim', percent: num(s.percent) })) };
      }
    } catch {}
    const people = [...($('eligible')?.selectedOptions || [])];
    const each = people.length ? (100 - company) / people.length : 0;
    return { company, shares: people.map(o => ({ name: o.textContent.split(' · ')[0], percent: each })) };
  }

  function split(amount, company, shares, currency) {
    const items = [row(`Kompaniya · ${fmt(company)}%`, `${fmt(amount * company / 100)} ${currency}`, 'is-company')];
    shares.forEach(s => items.push(row(`${s.name} · ${fmt(s.percent)}%`, `${fmt(amount * s.percent / 100)} ${currency}`)));
    const total = company + shares.reduce((n, s) => n + Number(s.percent), 0);
    return `<ul class="op-split">${items.join('')}</ul>` + (Math.abs(total - 100) > 0.001
      ? `<p class="op-warn">Jami ${fmt(total)}% — 100% bo‘lishi kerak.</p>` : '');
  }

  function update() {
    const kind = $('kind').value, currency = $('currency')?.value || '';
    const amount = num($('amount')?.value);
    let html = '';
    if (kind === 'agreement') {
      const { company, shares } = sharesFromForm();
      html = `<p class="op-say">Mijoz <b>${fmt(amount)} ${currency}</b> to‘lasa, pul shunday bo‘linadi:</p>` + split(amount, company, shares, currency)
        + (shares.length ? '' : '<p class="op-warn">Kelishuvdagi xodimlarni tanlang (Ctrl bosib bir nechtasini).</p>')
        + '<p class="op-note">Kompaniya ulushi foydaga qoladi, xarajatlar shundan chiqadi. Xodimlar ulushi ularga «to‘lanishi kerak» bo‘lib yoziladi.</p>';
    } else if (kind === 'receipt') {
      const a = agreements[$('project')?.value || ''];
      if (!$('project')?.value) html = '<p class="text-tertiary">Loyihani tanlang — pul qanday bo‘linishi chiqadi.</p>';
      else if (!a) html = '<p class="op-warn">Bu loyihada hali kelishuv yo‘q. Avval <b>1-qadam: Loyiha kelishuvi</b>ni kiriting — aks holda pulni bo‘lib bo‘lmaydi.</p><button type="button" class="button compact" data-go-kind="agreement">Kelishuv kiritish</button>';
      else if (a.currency !== currency) html = `<p class="op-warn">Bu loyiha kelishuvi <b>${esc(a.currency)}</b> da. Valyutani ${esc(a.currency)} qiling.</p>`;
      else html = `<p class="op-say"><b>${fmt(amount)} ${currency}</b> shunday bo‘linadi:</p>` + split(amount, num(a.company), a.shares.map(s => ({ name: s.name, percent: num(s.percent) })), currency)
        + `<p class="op-note">Kelishuv summasi: ${fmt(num(a.amount))} ${esc(a.currency)}. Xodimlar ulushi «to‘lanishi kerak» bo‘ladi — pulni bergach «Xodimga pul berish» orqali qayd eting.</p>`;
    } else if (kind === 'salary' || kind === 'bonus') {
      const who = $('employee')?.selectedOptions[0]?.textContent.split(' · ')[0];
      html = who && $('employee').value
        ? `<p class="op-say"><b>${esc(who)}</b>ga <b>${fmt(amount)} ${currency}</b> ${kind === 'salary' ? 'ish haqi' : 'mukofot'} yoziladi.</p><ul class="op-split">${row('Xodimga to‘lanishi kerak', '+' + fmt(amount) + ' ' + currency)}${row('Kompaniya foydasidan', '−' + fmt(amount) + ' ' + currency, 'is-out')}</ul><p class="op-note">Bu hali to‘lov emas. Pulni qo‘liga bergach «Xodimga pul berish» orqali qayd eting.</p>`
        : '<p class="text-tertiary">Xodimni tanlang.</p>';
    } else if (kind === 'expense') {
      html = `<ul class="op-split">${row('Kassadan chiqim', '−' + fmt(amount) + ' ' + currency, 'is-out')}${row('Kompaniya foydasidan', '−' + fmt(amount) + ' ' + currency, 'is-out')}</ul>`;
    } else if (kind === 'correction') {
      html = '<p class="op-say">Tanlangan yozuv shu summaga kamaytiriladi. Agar u mijoz tushumi bo‘lsa, xodimlar ulushi ham mutanosib kamayadi.</p>';
    }
    preview.innerHTML = html;
    preview.querySelectorAll('[data-go-kind]').forEach(b => b.addEventListener('click', () => setKind(b.dataset.goKind)));
  }

  cards.forEach(card => card.addEventListener('click', () => setKind(card.dataset.kind)));
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  setKind($('kind').value);
  }
  window.SSBOperation = { init };
  if (!document.querySelector('.fin-modal #op-form')) init(document);
})();
