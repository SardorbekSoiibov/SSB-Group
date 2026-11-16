(() => {
  'use strict';
  const $ = s => document.querySelector(s), root = $('#staff-chat');
  if (!root) return;
  const API = '/management/chat/api/';
  const peer = JSON.parse($('#chat-peer-data').textContent), REACTIONS = JSON.parse($('#chat-reactions-data').textContent);
  const list = $('#chat-contacts'), connection = $('#chat-connection'), error = $('#chat-error');
  const form = $('#chat-form'), input = $('#chat-body'), timeline = $('#chat-timeline'), stream = $('#chat-messages');
  const menu = $('#chat-menu'), uploadLimit = Number(root.dataset.uploadMb || 10) * 1024 * 1024;
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
  const EMOJI = '😀 😁 😂 🤣 😊 😍 😘 😎 🤔 😅 😉 🙂 😢 😭 😡 😮 🥳 😴 👍 👎 👏 🙏 💪 🤝 👌 ✌️ 👋 ❤️ 🔥 ⭐ 🎉 ✅ ❌ ⚠️ 📌 📎 📅 ⏰ 💡 🚀'.split(' ');
  const MONTHS = ['yanvar','fevral','mart','aprel','may','iyun','iyul','avgust','sentabr','oktabr','noyabr','dekabr'];

  // Conversation state
  const items = new Map(), nodes = new Map();
  let newest = 0, oldest = 0, readThrough = 0, serverTime = '', firstUnread = 0, initial = true;
  let loading = false, sending = false, olderLoading = false, stopped = false, scrollToEnd = true;
  let timer, queryTimer, findTimer, contactsController, user = null, contactsSignature = '', feedbackKind = '';
  let epoch = 0, replyTo = null, editing = null, file = null, filePreviewURL = '', pending = null, lastTyping = 0, missed = 0, menuFor = null, forwardSource = null;
  const draftKey = peer ? `ssb-chat-draft:${root.dataset.userId}:${peer.id}` : null;

  // ---------- helpers ----------
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() :
    ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)));
  const initials = name => (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]).join('').toUpperCase();
  const hue = id => [211, 152, 28, 268, 340, 190, 95, 0][Math.abs(Number(id) || 0) % 8];
  const pad = n => String(n).padStart(2, '0');
  // Times follow the company zone and the server clock, not the settings of this computer.
  const zoneFormat = new Intl.DateTimeFormat('en-GB', {timeZone: root.dataset.timeZone || undefined, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
  let clockSkew = 0;
  const now = () => Date.now() + clockSkew;
  function clock(value) { const out = {}; zoneFormat.formatToParts(new Date(value)).forEach(part => { out[part.type] = part.value; }); return out; }
  const time = value => { const c = clock(value); return `${c.hour}:${c.minute}`; };
  const dayNumber = value => { const c = clock(value); return Math.floor(Date.UTC(+c.year, +c.month - 1, +c.day) / 864e5); };
  const dayKey = value => dayNumber(value);
  const daysAgo = value => dayNumber(now()) - dayNumber(value);
  function dayLabel(value) {
    const age = daysAgo(value), c = clock(value);
    if (age <= 0) return 'Bugun';
    if (age === 1) return 'Kecha';
    return `${Number(c.day)}-${MONTHS[Number(c.month) - 1]}` + (c.year !== clock(now()).year ? ` ${c.year}` : '');
  }
  function shortStamp(value) {
    if (!value) return '';
    const age = daysAgo(value), c = clock(value);
    if (age <= 0) return time(value);
    if (age === 1) return 'Kecha';
    if (age < 7) return ['Ya','Du','Se','Ch','Pa','Ju','Sh'][new Date(dayNumber(value) * 864e5).getUTCDay()];
    return `${c.day}.${c.month}` + (c.year !== clock(now()).year ? `.${c.year.slice(2)}` : '');
  }
  function lastSeen(value) {
    if (!value) return '';
    const label = dayLabel(value);
    return 'oxirgi marta ' + (label === 'Bugun' ? 'bugun ' : label === 'Kecha' ? 'kecha ' : label + ' ') + time(value);
  }
  const size = bytes => bytes < 1024 ? bytes + ' B' : bytes < 1048576 ? (bytes / 1024).toFixed(1) + ' KB' : (bytes / 1048576).toFixed(1) + ' MB';
  const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text != null) node.textContent = text; return node; };
  function avatar(person, className = 'chat-avatar') {
    const node = el('span', className, initials(person.name)); node.style.setProperty('--avatar-hue', hue(person.id)); node.setAttribute('aria-hidden', 'true');
    if (person.photo) { const image = el('img'); image.src = person.photo; image.alt = ''; image.loading = 'lazy'; image.addEventListener('error', () => image.remove()); node.append(image); }
    if (person.online) node.append(el('i', 'chat-online'));
    return node;
  }
  function linkify(target, text) {
    // Text is only ever inserted as text nodes; links are limited to http(s).
    const parts = text.split(/(https?:\/\/[^\s<>"']+)/g);
    parts.forEach((part, index) => {
      if (index % 2) { const a = el('a', '', part); a.href = part; a.target = '_blank'; a.rel = 'noopener noreferrer'; target.append(a); }
      else if (part) target.append(document.createTextNode(part));
    });
  }
  function feedback(text = '', kind = 'action') { feedbackKind = kind; if (error) { error.hidden = !text; error.textContent = text; } }
  function toast(text) { document.dispatchEvent(new CustomEvent('ssb:toast', {detail: {level: 'success', message: text, text}})); }
  async function api(url, options = {}) {
    const json = typeof options.body === 'string';
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options,
      signal: options.signal || AbortSignal.timeout(options.timeout || 10000),
      headers: {'Accept': 'application/json', ...(options.method ? {'X-CSRFToken': csrf} : {}), ...(json ? {'Content-Type': 'application/json'} : {}), ...options.headers}});
    if ([401, 403].includes(response.status) && !options.allowForbidden) { stopped = true; throw Error('Sessiya tugagan. Sahifani yangilab qayta kiring.'); }
    let data = {};
    try { data = await response.json(); } catch { if (!response.ok) throw Error('So‘rov bajarilmadi. Qayta urinib ko‘ring.'); }
    if (!response.ok) throw Error(data.error || data.detail || 'So‘rov bajarilmadi. Qayta urinib ko‘ring.');
    if (data.user) { if (user !== null && user !== data.user) { stopped = true; location.reload(); throw Error('Hisob o‘zgardi.'); } user = data.user; }
    return data;
  }

  const VERIFIED = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.6 2 3.3-.3 1 3.1 2.8 1.8-1 3.2 1 3.2-2.8 1.8-1 3.1-3.3-.3L12 22l-2.6-2-3.3.3-1-3.1-2.8-1.8 1-3.2-1-3.2 2.8-1.8 1-3.1 3.3.3z"/><path class="tick" d="m8 12 3 3 5-6"/></svg>';
  function nameNode(person, tag = 'strong') {
    const node = el(tag);
    node.append(el('span', 'chat-name-text', person.name));
    if (person.verified) { const badge = el('span', 'chat-verified'); badge.title = 'Tasdiqlangan hisob'; badge.setAttribute('aria-label', 'Tasdiqlangan hisob'); badge.innerHTML = VERIFIED; node.append(badge); }
    return node;
  }
  // ---------- contacts ----------
  function personNode(person) {
    const a = el('a', 'chat-contact'); a.href = person.url;
    if (person.id === peer?.id) a.setAttribute('aria-current', 'page');
    if (!person.active) a.classList.add('is-inactive');
    const text = el('span', 'chat-contact-text'), top = el('span', 'chat-contact-top'), bottom = el('span', 'chat-contact-bottom');
    const name = nameNode(person);
    if (!person.active) name.append(el('em', 'chat-inactive-tag', 'Faol emas'));
    top.append(name, el('time', '', shortStamp(person.last_at)));
    const sub = el('small');
    if (person.typing) { sub.textContent = 'yozmoqda…'; sub.className = 'is-typing'; }
    else if ($('#chat-search').value.trim()) sub.textContent = person.active ? person.role : `${person.role} · faol emas`;
    else if (person.last) {
      if (person.last_mine) { const tick = el('span', 'chat-ticks' + (person.last_read ? ' read' : ''), person.last_read ? '✓✓' : '✓'); sub.append(tick, document.createTextNode(' Siz: ')); }
      sub.append(document.createTextNode(person.last));
    } else sub.textContent = person.active ? person.role : 'Faol emas';
    bottom.append(sub);
    if (person.unread) bottom.append(el('b', '', person.unread > 99 ? '99+' : String(person.unread)));
    text.append(top, bottom); a.append(avatar(person), text);
    return a;
  }
  async function contacts() {
    contactsController?.abort(); contactsController = new AbortController();
    try {
      const data = await api(API + 'contacts/?q=' + encodeURIComponent($('#chat-search').value), {signal: contactsController.signal});
      const signature = JSON.stringify([data.items, data.has_more]);
      if (signature !== contactsSignature) {
        const fragment = document.createDocumentFragment();
        data.items.forEach(person => fragment.append(personNode(person)));
        if (!data.items.length || data.has_more) fragment.append(el('p', 'chat-empty', data.has_more ? 'Boshqa xodimni topish uchun qidiruvdan foydalaning.' : 'Xodim topilmadi.'));
        list.replaceChildren(fragment); contactsSignature = signature;
      }
      $('#chat-total').textContent = data.unread; $('#chat-total').hidden = !data.unread;
      document.querySelectorAll('[data-chat-unread]').forEach(node => { node.textContent = data.unread > 99 ? '99+' : data.unread; node.hidden = !data.unread; });
      return data;
    } catch (e) { if (e.name !== 'AbortError') throw e; }
  }

  // ---------- messages ----------
  function meta(data) {
    const node = el('small', 'chat-meta');
    if (data.edited) node.append(el('span', 'chat-edited', 'tahrirlandi'));
    node.append(document.createTextNode(time(data.created_at)));
    if (data.mine && !data.deleted) {
      const read = !!data.read_at || data.id <= readThrough;
      const ticks = el('span', 'chat-ticks' + (read ? ' read' : ''), read ? '✓✓' : '✓'); ticks.title = read ? 'O‘qildi' : 'Yuborildi';
      node.append(ticks, el('span', 'sr-only', read ? ' · O‘qildi' : ' · Yuborildi'));
    }
    return node;
  }
  function render(data) {
    const row = el('article', 'chat-message' + (data.mine ? ' mine' : '') + (data.deleted ? ' deleted' : '') + (data.pinned ? ' pinned' : ''));
    row.dataset.message = data.id; row.tabIndex = -1;
    const bubble = el('div', 'chat-bubble');
    if (data.forwarded_from) bubble.append(el('span', 'chat-forwarded', '↪ Uzatildi: ' + data.forwarded_from));
    if (data.reply_to) {
      const quote = el('button', 'chat-quote'); quote.type = 'button'; quote.dataset.jump = data.reply_to.id;
      quote.append(el('strong', '', data.reply_to.mine ? 'Siz' : data.reply_to.name), el('span', '', data.reply_to.preview));
      bubble.append(quote);
    }
    if (data.attachment) {
      if (data.attachment.image) {
        const media = el('button', 'chat-media'); media.type = 'button'; media.dataset.view = data.id; media.setAttribute('aria-label', 'Rasmni ochish: ' + data.attachment.name);
        const img = el('img'); img.src = data.attachment.url; img.alt = data.attachment.name; img.loading = 'lazy'; img.decoding = 'async';
        img.addEventListener('load', () => { if (scrollToEnd || nearBottom(220)) toBottom(); }, {once: true});
        media.append(img); bubble.append(media); row.classList.add('has-media');
      } else {
        const link = el('a', 'chat-file'); link.href = data.attachment.url + '?download=1'; link.download = data.attachment.name;
        const label = el('span', 'chat-file-text'); label.append(el('strong', '', data.attachment.name), el('span', '', size(data.attachment.size)));
        link.append(el('span', 'chat-file-icon', '📄'), label); bubble.append(link);
      }
    }
    if (data.deleted) bubble.append(el('p', 'chat-text is-deleted', '🚫 Bu xabar o‘chirildi'));
    else if (data.body) { const text = el('p', 'chat-text'); linkify(text, data.body); bubble.append(text); }
    bubble.append(meta(data));
    row.append(bubble);
    if (data.reactions?.length) {
      const bar = el('div', 'chat-reactions');
      data.reactions.forEach(r => { const b = el('button', 'chat-reaction' + (r.mine ? ' mine' : ''), `${r.emoji} ${r.count}`); b.type = 'button'; b.dataset.react = r.emoji; b.setAttribute('aria-pressed', String(r.mine)); bar.append(b); });
      row.append(bar);
    }
    if (!data.deleted) { const more = el('button', 'chat-more', '⋯'); more.type = 'button'; more.dataset.menu = data.id; more.setAttribute('aria-label', 'Xabar amallari'); bubble.append(more); }
    return row;
  }
  function insert(row, id) {
    const last = stream.lastElementChild && [...stream.querySelectorAll('.chat-message')].pop();
    if (!last || Number(last.dataset.message) < id) { stream.append(row); return; }
    for (const node of stream.querySelectorAll('.chat-message')) if (Number(node.dataset.message) > id) { node.before(row); return; }
    stream.append(row);
  }
  const nearBottom = (gap = 120) => !timeline || timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < gap;
  function reveal(node, block = 'center', smooth = false) {
    const box = timeline.getBoundingClientRect(), rect = node.getBoundingClientRect();
    const offset = block === 'center' ? (timeline.clientHeight - rect.height) / 2 : 0;
    timeline.scrollTo({top: timeline.scrollTop + rect.top - box.top - offset, behavior: smooth ? 'smooth' : 'auto'});
  }
  function toBottom(smooth = false) { timeline.scrollTo({top: timeline.scrollHeight, behavior: smooth ? 'smooth' : 'auto'}); }
  function paint(list, {prepend = false, cursor = true} = {}) {
    const wasNear = nearBottom(), height = timeline?.scrollHeight || 0;
    let added = 0, incoming = 0;
    const fragment = document.createDocumentFragment();
    for (const data of list) {
      if (cursor) { newest = Math.max(newest, data.id); oldest = oldest ? Math.min(oldest, data.id) : data.id; }
      if (nodes.has(data.id)) { upsert(data); continue; }
      items.set(data.id, data);
      if (initial && !firstUnread && !data.mine && !data.read_at) firstUnread = data.id;
      const row = render(data); nodes.set(data.id, row); added++;
      if (!data.mine && !initial) incoming++;
      if (prepend) fragment.append(row); else insert(row, data.id);
    }
    if (prepend) stream.prepend(fragment);
    if (added) layout();
    $('#chat-empty').hidden = items.size > 0;
    if (!items.size) $('#chat-empty').textContent = 'Hali xabar yo‘q. Birinchi xabarni yuboring.';
    if (prepend) timeline.scrollTop += timeline.scrollHeight - height;
    else if (initial && firstUnread && nodes.get(firstUnread)) { reveal(nodes.get(firstUnread).previousElementSibling || nodes.get(firstUnread), 'start'); scrollToEnd = false; }
    else if (scrollToEnd || (wasNear && added)) { toBottom(); scrollToEnd = false; }
    else if (incoming) { missed += incoming; downButton(); }
  }
  function upsert(data) {
    const old = nodes.get(data.id);
    if (!old) return;
    items.set(data.id, data);
    const row = render(data); old.replaceWith(row); nodes.set(data.id, row);
    row.classList.toggle('grouped', old.classList.contains('grouped')); row.classList.toggle('tail', old.classList.contains('tail'));
    if (editing?.id === data.id && data.deleted) clearContext();
  }
  function layout() {
    stream.querySelectorAll('.chat-day,.chat-unread-divider').forEach(node => node.remove());
    let day = '', prev = null, prevRow = null;
    for (const row of stream.querySelectorAll('.chat-message')) {
      const data = items.get(Number(row.dataset.message)); if (!data) continue;
      let breakGroup = false;
      if (dayKey(data.created_at) !== day) { day = dayKey(data.created_at); const sep = el('div', 'chat-day'); sep.append(el('span', '', dayLabel(data.created_at))); row.before(sep); breakGroup = true; }
      if (data.id === firstUnread) { const divider = el('div', 'chat-unread-divider'); divider.append(el('span', '', 'Yangi xabarlar')); row.before(divider); breakGroup = true; }
      const grouped = !breakGroup && prev && prev.mine === data.mine && new Date(data.created_at) - new Date(prev.created_at) < 5 * 60000;
      row.classList.toggle('grouped', !!grouped);
      if (prevRow) prevRow.classList.toggle('tail', !grouped);
      prev = data; prevRow = row;
    }
    prevRow?.classList.add('tail');
  }
  function readReceipts(value) {
    if (value <= readThrough) return;
    readThrough = value;
    for (const [id, data] of items) if (data.mine && id <= value && !data.read_at) {
      data.read_at = data.read_at || true; const row = nodes.get(id); row?.querySelector('.chat-meta')?.replaceWith(meta(data));
    }
  }
  function downButton() {
    const button = $('#chat-down'), count = $('#chat-down-count'); if (!button) return;
    button.parentElement.style.setProperty('--composer', form.offsetHeight + 'px'); const away = !nearBottom(300); button.hidden = !away; if (!away) missed = 0;
    count.hidden = !missed; count.textContent = missed > 99 ? '99+' : missed;
  }
  function peerStatus(data) {
    const status = $('#peer-status'), face = $('#peer-initials'); if (!status) return;
    status.classList.toggle('is-typing', !!data.typing); status.classList.toggle('is-online', !data.typing && !!data.online);
    status.textContent = data.typing ? 'yozmoqda…' : data.online ? 'onlayn' : !data.active ? 'Faol emas' : (lastSeen(data.last_seen) || 'hali kirmagan');
    status.title = data.role;
    const title = $('#peer-name'); if (title) title.replaceChildren(...nameNode(data, 'span').childNodes);
    face.replaceWith(Object.assign(avatar(data), {id: 'peer-initials'}));
  }
  function pinnedBar(pinned) {
    const bar = $('#chat-pinned'); if (!bar) return;
    bar.hidden = !pinned; bar.dataset.message = pinned?.id || '';
    $('#chat-pinned-text').textContent = pinned?.preview || '';
  }
  async function acknowledge() {
    if (!peer || document.hidden || !newest) return;
    const lastIncoming = [...items.values()].filter(d => !d.mine && !d.read_at).reduce((m, d) => Math.max(m, d.id), 0);
    if (!lastIncoming) return;
    await api(`${API}${peer.id}/read/`, {method: 'POST', body: JSON.stringify({through: newest})});
    for (const data of items.values()) if (!data.mine && data.id <= newest) data.read_at = data.read_at || true;
  }
  async function poll() {
    clearTimeout(timer); timer = null;
    if (loading || stopped) return;
    if (document.hidden) { timer = setTimeout(poll, 3000); return; }
    loading = true;
    try {
      if (peer) {
        const params = new URLSearchParams();
        if (newest) params.set('after', newest);
        if (serverTime) params.set('since', serverTime);
        const started = epoch;
        const data = await api(`${API}${peer.id}/messages/?${params}`);
        if (started !== epoch) return;
        const wasInitial = initial;
        paint(data.items);
        data.changes?.forEach(upsert);
        readReceipts(data.read_through);
        if (wasInitial) { $('#chat-older').hidden = !data.has_more; initial = false; }
        serverTime = data.server_time;
        clockSkew = Date.parse(data.server_time) - Date.now();
        peerStatus(data.peer); pinnedBar(data.pinned);
        const disabled = !data.peer.active;
        [input, $('#chat-attach'), $('#chat-emoji'), form.querySelector('.chat-send')].forEach(node => { if (node && !(sending && node.classList.contains('chat-send'))) node.disabled = disabled; });
        if (disabled) feedback('Xodim faol emas. Suhbat tarixini ko‘rishingiz mumkin.', 'inactive');
        else if (feedbackKind === 'inactive') feedback();
        await acknowledge();
        if (!wasInitial && data.has_more && data.items.length === 100) timer = setTimeout(poll, 50);
      }
      await contacts(); connection.textContent = 'Ulangan'; connection.classList.remove('is-offline');
      if (feedbackKind === 'connection') feedback();
    } catch (e) {
      connection.textContent = stopped ? 'Qayta kirish kerak' : 'Qayta ulanmoqda…'; connection.classList.add('is-offline');
      feedback(e.message || 'Ulanish uzildi. Qayta uriniladi.', 'connection');
    } finally { loading = false; if (!timer && !stopped) timer = setTimeout(poll, 3000); }
  }

  // ---------- jump / search ----------
  function flash(row) { reveal(row, 'center', true); row.classList.remove('flash'); void row.offsetWidth; row.classList.add('flash'); row.focus({preventScroll: true}); }
  async function jump(id) {
    id = Number(id); if (!id) return;
    if (nodes.has(id)) { flash(nodes.get(id)); return; }
    try {
      const data = await api(`${API}${peer.id}/messages/?around=${id}`);
      epoch++; items.clear(); nodes.clear(); stream.replaceChildren(); newest = 0; oldest = 0; firstUnread = 0; scrollToEnd = false;
      paint(data.items); $('#chat-older').hidden = !data.has_more;
      if (nodes.has(id)) flash(nodes.get(id));
      clearTimeout(timer); timer = setTimeout(poll, 50);
    } catch (e) { feedback(e.message); }
  }
  async function find() {
    const query = $('#chat-find').value.trim(), box = $('#chat-find-results');
    if (query.length < 2) { box.replaceChildren(); return; }
    try {
      const data = await api(`${API}${peer.id}/messages/?q=${encodeURIComponent(query)}`);
      const fragment = document.createDocumentFragment();
      data.results.forEach(result => {
        const b = el('button', 'chat-find-result'); b.type = 'button'; b.dataset.jump = result.id;
        b.append(el('strong', '', result.mine ? 'Siz' : peer.name), el('span', '', result.preview), el('time', '', `${dayLabel(result.created_at)} ${time(result.created_at)}`));
        fragment.append(b);
      });
      if (!data.results.length) fragment.append(el('p', 'chat-empty', 'Hech narsa topilmadi.'));
      box.replaceChildren(fragment);
    } catch (e) { feedback(e.message); }
  }

  // ---------- composer ----------
  function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; }
  function saveDraft() { if (editing) return; try { input.value ? sessionStorage.setItem(draftKey, input.value) : sessionStorage.removeItem(draftKey); } catch {} }
  function setContext(kind, data) {
    replyTo = kind === 'reply' ? data : null; editing = kind === 'edit' ? data : null;
    const box = $('#chat-context'); box.hidden = false;
    $('#chat-context-icon').textContent = kind === 'edit' ? '✎' : '↩';
    $('#chat-context-title').textContent = kind === 'edit' ? 'Tahrirlash' : (data.mine ? 'Javob: o‘zingizga' : 'Javob: ' + peer.name);
    $('#chat-context-text').textContent = data.deleted ? 'Xabar o‘chirildi' : data.body || (data.attachment ? (data.attachment.image ? '🖼 Rasm' : '📎 ' + data.attachment.name) : '');
    if (kind === 'edit') { input.value = data.body; clearFile(); }
    autosize(); input.focus(); input.setSelectionRange(input.value.length, input.value.length);
  }
  function clearContext() {
    const wasEditing = !!editing; replyTo = null; editing = null; $('#chat-context').hidden = true;
    if (wasEditing) { try { input.value = sessionStorage.getItem(draftKey) || ''; } catch { input.value = ''; } autosize(); }
  }
  function clearFile() {
    file = null; if (filePreviewURL) URL.revokeObjectURL(filePreviewURL); filePreviewURL = '';
    $('#chat-attachment').hidden = true; $('#chat-file').value = '';
  }
  function chooseFile(chosen) {
    if (!chosen || input.disabled) return;
    if (editing) clearContext();
    if (chosen.size > uploadLimit) { feedback(`Fayl hajmi ${Math.round(uploadLimit / 1048576)} MB dan oshmasligi kerak.`); return; }
    clearFile(); file = chosen; feedback();
    $('#chat-attachment').hidden = false; $('#chat-attachment-name').textContent = chosen.name; $('#chat-attachment-size').textContent = size(chosen.size);
    const thumb = $('#chat-attachment-thumb'); thumb.replaceChildren();
    if (/^image\/(png|jpe?g|webp)$/.test(chosen.type)) { filePreviewURL = URL.createObjectURL(chosen); const img = el('img'); img.src = filePreviewURL; img.alt = ''; thumb.append(img); }
    else thumb.textContent = '📎';
    input.focus();
  }
  function insertAtCursor(text) {
    const start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? start;
    input.setRangeText(text, start, end, 'end'); input.dispatchEvent(new Event('input')); input.focus();
  }
  async function submit() {
    if (sending || stopped || input.disabled) return;
    const text = input.value.trim(), button = form.querySelector('.chat-send');
    if (editing) {
      if (!text && !editing.attachment) return;
      sending = true; button.disabled = true;
      try { const data = await api(`${API}messages/${editing.id}/`, {method: 'PATCH', body: JSON.stringify({body: text})}); upsert(data.item); input.value = ''; clearContext(); autosize(); feedback(); }
      catch (e) { feedback(e.message); } finally { sending = false; button.disabled = input.disabled; }
      return;
    }
    if (!text && !file) return;
    const key = JSON.stringify([text, file?.name, file?.size, replyTo?.id]);
    if (!pending || pending.key !== key) pending = {key, client_id: uuid()};
    sending = true; button.disabled = true; form.setAttribute('aria-busy', 'true'); feedback();
    let options;
    if (file) {
      const body = new FormData(); body.append('body', text); body.append('client_id', pending.client_id);
      if (replyTo) body.append('reply_to', replyTo.id); body.append('file', file, file.name);
      options = {method: 'POST', body, timeout: 120000};
    } else options = {method: 'POST', body: JSON.stringify({body: text, client_id: pending.client_id, reply_to: replyTo?.id || null})};
    try {
      const data = await api(`${API}${peer.id}/messages/`, options);
      if (input.value.trim() === text) { input.value = ''; try { sessionStorage.removeItem(draftKey); } catch {} }
      pending = null; clearFile(); clearContext(); autosize(); scrollToEnd = true;
      // Shown immediately but not used as the fetch cursor, so an earlier incoming message is never skipped.
      paint([data.item], {cursor: false}); toBottom();
      poll(); input.focus();
    } catch (e) { feedback(e.message || 'Yuborilmadi. Xabaringiz saqlandi, qayta yuboring.'); }
    finally { sending = false; button.disabled = input.disabled; form.removeAttribute('aria-busy'); }
  }

  // ---------- message actions ----------
  function closeMenu() { if (menu.hidden) return; menu.hidden = true; const row = nodes.get(menuFor); row?.classList.remove('menu-open'); menuFor = null; }
  function openMenu(id, x, y) {
    const data = items.get(Number(id)); if (!data || data.deleted) return;
    closeMenu(); menuFor = data.id; nodes.get(data.id)?.classList.add('menu-open');
    const reactions = $('#chat-menu-reactions'); reactions.replaceChildren();
    if (peer && !input.disabled) REACTIONS.forEach(emoji => { const b = el('button', 'chat-menu-react', emoji); b.type = 'button'; b.dataset.action = 'react'; b.dataset.emoji = emoji; b.setAttribute('role', 'menuitem'); b.setAttribute('aria-label', 'Reaksiya ' + emoji); reactions.append(b); });
    reactions.hidden = !reactions.children.length;
    const actions = [['reply', '↩', 'Javob berish', !input.disabled], ['copy', '⧉', 'Matnni nusxalash', !!data.body], ['edit', '✎', 'Tahrirlash', data.editable],
      ['pin', '📌', data.pinned ? 'Qadashni olib tashlash' : 'Qadash', true], ['forward', '↪', 'Uzatish', true],
      ['download', '⤓', 'Yuklab olish', !!data.attachment], ['delete', '🗑', 'Hamma uchun o‘chirish', data.mine]];
    const box = $('#chat-menu-actions'); box.replaceChildren();
    actions.filter(a => a[3]).forEach(([action, icon, label]) => { const b = el('button', 'chat-menu-item' + (action === 'delete' ? ' danger' : '')); b.type = 'button'; b.dataset.action = action; b.setAttribute('role', 'menuitem'); b.append(el('span', '', icon), document.createTextNode(label)); box.append(b); });
    menu.hidden = false;
    const rect = root.getBoundingClientRect(), w = menu.offsetWidth, h = menu.offsetHeight;
    menu.style.left = Math.max(8, Math.min(x - rect.left, rect.width - w - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y - rect.top, rect.height - h - 8)) + 'px';
    menu.querySelector('button')?.focus();
  }
  async function react(id, emoji) {
    try { const data = await api(`${API}messages/${id}/react/`, {method: 'POST', body: JSON.stringify({emoji})}); upsert(data.item); } catch (e) { feedback(e.message); }
  }
  async function action(name, data) {
    if (name === 'reply') setContext('reply', data);
    else if (name === 'edit') setContext('edit', data);
    else if (name === 'copy') { try { await navigator.clipboard.writeText(data.body); toast('Matn nusxalandi.'); } catch { feedback('Nusxalab bo‘lmadi.'); } }
    else if (name === 'download') { const a = el('a'); a.href = data.attachment.url + '?download=1'; a.download = data.attachment.name; document.body.append(a); a.click(); a.remove(); }
    else if (name === 'pin') {
      try { const result = await api(`${API}messages/${data.id}/pin/`, {method: 'POST', body: JSON.stringify({pinned: !data.pinned})}); upsert(result.item); pinnedBar(result.item.pinned ? {id: result.item.id, preview: result.item.body || 'Fayl'} : null); poll(); }
      catch (e) { feedback(e.message); }
    } else if (name === 'delete') {
      if (!await window.ssbConfirm({title: 'Xabarni o‘chirasizmi?', text: 'Xabar ikkala tomondan ham o‘chiriladi. Buni qaytarib bo‘lmaydi.', accept: 'O‘chirish', danger: true})) return;
      try { const result = await api(`${API}messages/${data.id}/`, {method: 'DELETE'}); upsert(result.item); } catch (e) { feedback(e.message); }
    } else if (name === 'forward') openForward(data);
  }
  async function openForward(data) {
    forwardSource = data; const dialog = $('#chat-forward'); $('#chat-forward-search').value = '';
    await fillForward(); dialog.showModal(); $('#chat-forward-search').focus();
  }
  async function fillForward() {
    const box = $('#chat-forward-list');
    try {
      const data = await api(API + 'contacts/?q=' + encodeURIComponent($('#chat-forward-search').value));
      const fragment = document.createDocumentFragment();
      data.items.filter(p => p.active).forEach(person => {
        const b = el('button', 'chat-forward-person'); b.type = 'button'; b.dataset.forward = person.id; b.dataset.url = person.url;
        b.append(avatar(person), el('span', '', person.name), el('small', '', person.role)); fragment.append(b);
      });
      if (!fragment.children.length) fragment.append(el('p', 'chat-empty', 'Xodim topilmadi.'));
      box.replaceChildren(fragment);
    } catch (e) { box.replaceChildren(el('p', 'chat-empty', e.message)); }
  }
  async function forwardTo(button) {
    if (!forwardSource || button.disabled) return;
    button.disabled = true;
    try {
      await api(`${API}${button.dataset.forward}/forward/`, {method: 'POST', body: JSON.stringify({message: forwardSource.id, client_id: uuid()}), timeout: 60000});
      $('#chat-forward').close(); forwardSource = null;
      if (Number(button.dataset.forward) === peer?.id) { scrollToEnd = true; poll(); toast('Xabar uzatildi.'); }
      else location.assign(button.dataset.url);
    } catch (e) { feedback(e.message); button.disabled = false; }
  }
  function openViewer(id) {
    const data = items.get(Number(id)); if (!data?.attachment) return;
    $('#chat-viewer-image').src = data.attachment.url; $('#chat-viewer-image').alt = data.attachment.name;
    $('#chat-viewer-name').textContent = data.attachment.name; $('#chat-viewer-download').href = data.attachment.url + '?download=1';
    $('#chat-viewer-download').setAttribute('download', data.attachment.name); $('#chat-viewer').showModal();
  }

  // ---------- events ----------
  $('#chat-search').addEventListener('input', () => { clearTimeout(queryTimer); queryTimer = setTimeout(() => contacts().catch(e => feedback(e.message)), 250); });
  document.querySelectorAll('.chat-dialog,.chat-viewer').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog || event.target.closest('[data-dialog-close]')) dialog.close(); }));
  if (peer) {
    try { input.value = sessionStorage.getItem(draftKey) || ''; } catch {}
    autosize();
    input.addEventListener('input', () => {
      autosize(); saveDraft();
      if (input.value.trim() && Date.now() - lastTyping > 4000 && !editing) { lastTyping = Date.now(); api(`${API}${peer.id}/typing/`, {method: 'POST', body: '{}'}).catch(() => {}); }
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submit(); }
      else if (event.key === 'Escape' && (replyTo || editing)) { event.preventDefault(); clearContext(); }
      else if (event.key === 'ArrowUp' && !input.value && !replyTo && !editing) {
        const last = [...items.values()].reverse().find(d => d.mine && d.editable);
        if (last) { event.preventDefault(); setContext('edit', last); }
      }
    });
    input.addEventListener('paste', event => { const pasted = [...(event.clipboardData?.files || [])][0]; if (pasted) { event.preventDefault(); chooseFile(pasted); } });
    form.addEventListener('submit', event => { event.preventDefault(); submit(); });
    $('#chat-context-cancel').addEventListener('click', clearContext);
    $('#chat-attach').addEventListener('click', () => $('#chat-file').click());
    $('#chat-file').addEventListener('change', event => chooseFile(event.target.files[0]));
    $('#chat-attachment-remove').addEventListener('click', clearFile);
    const panel = $('#chat-emoji-panel');
    EMOJI.forEach(emoji => { const b = el('button', '', emoji); b.type = 'button'; b.dataset.emoji = emoji; b.setAttribute('aria-label', emoji); panel.append(b); });
    $('#chat-emoji').addEventListener('click', () => { panel.hidden = !panel.hidden; $('#chat-emoji').setAttribute('aria-expanded', String(!panel.hidden)); });
    panel.addEventListener('click', event => { const b = event.target.closest('[data-emoji]'); if (b) insertAtCursor(b.dataset.emoji); });
    $('#chat-older').addEventListener('click', async () => {
      if (olderLoading || !oldest) return;
      olderLoading = true; const button = $('#chat-older'); button.disabled = true;
      try { const data = await api(`${API}${peer.id}/messages/?before=${oldest}`); paint(data.items, {prepend: true}); button.hidden = !data.has_more; }
      catch (e) { feedback(e.message); } finally { olderLoading = false; button.disabled = false; }
    });
    timeline.addEventListener('scroll', downButton, {passive: true});
    ['wheel', 'touchmove'].forEach(name => timeline.addEventListener(name, closeMenu, {passive: true}));
    $('#chat-down').addEventListener('click', () => { missed = 0; toBottom(true); });
    $('#chat-find-toggle').addEventListener('click', () => {
      const bar = $('#chat-findbar'); bar.hidden = !bar.hidden; $('#chat-find-toggle').setAttribute('aria-expanded', String(!bar.hidden));
      if (!bar.hidden) $('#chat-find').focus(); else { $('#chat-find').value = ''; $('#chat-find-results').replaceChildren(); }
    });
    $('#chat-find-results').addEventListener('click', event => { const b = event.target.closest('[data-jump]'); if (b) jump(b.dataset.jump); });
    $('#chat-find').addEventListener('input', () => { clearTimeout(findTimer); findTimer = setTimeout(find, 300); });
    $('#chat-find').addEventListener('keydown', event => { if (event.key === 'Escape') $('#chat-find-toggle').click(); });
    $('#chat-pinned-open').addEventListener('click', () => jump($('#chat-pinned').dataset.message));
    $('#chat-pinned-remove').addEventListener('click', () => { const data = items.get(Number($('#chat-pinned').dataset.message)) || {id: Number($('#chat-pinned').dataset.message), pinned: true}; action('pin', data); });
    $('#chat-forward-search').addEventListener('input', () => { clearTimeout(queryTimer); queryTimer = setTimeout(fillForward, 250); });
    $('#chat-forward-list').addEventListener('click', event => { const b = event.target.closest('[data-forward]'); if (b) forwardTo(b); });
    // Delegated message interactions: right click / long press / ⋯ for the menu, double click to reply.
    stream.addEventListener('click', event => {
      const more = event.target.closest('[data-menu]'); if (more) { const r = more.getBoundingClientRect(); openMenu(more.dataset.menu, r.left, r.bottom); return; }
      const quote = event.target.closest('[data-jump]'); if (quote) { jump(quote.dataset.jump); return; }
      const media = event.target.closest('[data-view]'); if (media) { openViewer(media.dataset.view); return; }
      const reaction = event.target.closest('[data-react]'); if (reaction && !input.disabled) react(reaction.closest('.chat-message').dataset.message, reaction.dataset.react);
    });
    stream.addEventListener('contextmenu', event => { const row = event.target.closest('.chat-message'); if (!row || event.target.closest('a')) return; event.preventDefault(); openMenu(row.dataset.message, event.clientX, event.clientY); });
    stream.addEventListener('dblclick', event => { const row = event.target.closest('.chat-message'); if (!row || input.disabled || event.target.closest('a,button')) return; const data = items.get(Number(row.dataset.message)); if (data && !data.deleted) { window.getSelection()?.removeAllRanges(); setContext('reply', data); } });
    let press;
    stream.addEventListener('touchstart', event => { const row = event.target.closest('.chat-message'); if (!row) return; const t = event.touches[0]; press = setTimeout(() => openMenu(row.dataset.message, t.clientX, t.clientY), 500); }, {passive: true});
    ['touchend', 'touchmove', 'touchcancel'].forEach(name => stream.addEventListener(name, () => clearTimeout(press), {passive: true}));
    menu.addEventListener('click', event => {
      const b = event.target.closest('[data-action]'); if (!b) return;
      const data = items.get(menuFor); closeMenu(); if (!data) return;
      if (b.dataset.action === 'react') react(data.id, b.dataset.emoji); else action(b.dataset.action, data);
    });
    menu.addEventListener('keydown', event => {
      const buttons = [...menu.querySelectorAll('button')], index = buttons.indexOf(document.activeElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowRight') { event.preventDefault(); buttons[(index + 1) % buttons.length]?.focus(); }
      if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') { event.preventDefault(); buttons[(index - 1 + buttons.length) % buttons.length]?.focus(); }
    });
    // Drag & drop files onto the conversation.
    const conversation = $('.chat-conversation'), drop = $('#chat-drop'); let depth = 0;
    conversation.addEventListener('dragenter', event => { if (![...event.dataTransfer.types].includes('Files') || input.disabled) return; depth++; drop.hidden = false; });
    conversation.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) drop.hidden = true; });
    conversation.addEventListener('dragover', event => { if ([...event.dataTransfer.types].includes('Files')) event.preventDefault(); });
    conversation.addEventListener('drop', event => { event.preventDefault(); depth = 0; drop.hidden = true; chooseFile(event.dataTransfer.files[0]); });
  }
  document.addEventListener('click', event => {
    if (!menu.hidden && !menu.contains(event.target) && !event.target.closest('[data-menu]')) closeMenu();
    const panel = $('#chat-emoji-panel');
    if (panel && !panel.hidden && !panel.contains(event.target) && !event.target.closest('#chat-emoji')) { panel.hidden = true; $('#chat-emoji').setAttribute('aria-expanded', 'false'); }
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !menu.hidden) { const row = nodes.get(menuFor); closeMenu(); row?.focus(); } });
  window.addEventListener('resize', closeMenu);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  window.addEventListener('online', poll); poll();
})();
