(() => {
  'use strict';
  const bell = document.querySelector('.notification-button');
  if (!bell) return;
  const endpoint = '/management/enterprise/api/notifications/';
  let cursor = null, user = null, pending = false, stopped = false, timer;
  const native = /Electron\//i.test(navigator.userAgent);
  function badge(count) {
    let node = bell.querySelector('b');
    if (count && !node) { node = document.createElement('b'); bell.append(node); }
    if (node) { node.textContent = count > 99 ? '99+' : String(count); node.hidden = !count; }
    bell.setAttribute('aria-label', `Bildirishnomalar: ${count} ta o‘qilmagan`);
  }
  function announce(items) {
    // Native Windows notifications are displayed by the Electron main process.
    if (!items.length || native) return;
    const region = document.querySelector('#toast-region');
    if (!region) return;
    const link = document.createElement('a');
    link.className = 'toast'; link.href = bell.href;
    link.textContent = items.length === 1 ? `Yangi xabar: ${items[0].title}` : `${items.length} ta yangi bildirishnoma`;
    region.append(link);
    setTimeout(() => link.remove(), 12000);
  }
  // Shu brauzerning boshqa oynasida boshqa hisobga kirilsa — sahifa o'zidan o'zi yangilanmaydi,
  // faqat ogohlantirish chiqadi (bitta brauzer bir vaqtda bitta hisobni ushlaydi).
  function accountChanged() {
    stopped = true;
    if (document.getElementById('account-changed')) return;
    const box = document.createElement('div');
    box.id = 'account-changed'; box.setAttribute('role', 'alertdialog');
    box.style.cssText = 'position:fixed;inset:0;z-index:2147483000;display:grid;place-items:center;padding:16px;background:rgb(0 0 0/.5);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)';
    box.innerHTML = '<div style="max-width:420px;padding:24px;border-radius:24px;background:var(--surface,#fff);color:var(--ink,#111);box-shadow:0 30px 70px -20px rgb(0 0 0/.5);text-align:center;font:inherit">'
      + '<strong style="display:block;font-size:18px;margin-bottom:8px">Boshqa oynada hisob almashtirildi</strong>'
      + '<p style="margin:0 0 16px;color:var(--ink-secondary,#666);font-size:14px;line-height:1.5">Shu brauzerda boshqa hisobga kirildi yoki hisobdan chiqildi. Davom etish uchun sahifani yangilang. Ikki hisobni bir vaqtda ochish uchun ikkinchisini «Inkognito» oynada oching.</p>'
      + '<button type="button" class="button primary">Sahifani yangilash</button></div>';
    box.querySelector('button').addEventListener('click', () => location.reload());
    document.body.append(box);
  }
  async function poll() {
    clearTimeout(timer); timer = null;
    if (pending || stopped) return;
    if (document.hidden) { timer = setTimeout(poll, 15000); return; }
    pending = true;
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(endpoint + (cursor === null ? '' : `?after=${cursor}`), {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: { Accept: 'application/json' }
      });
      if ([401, 403].includes(response.status)) { stopped = true; badge(0); return; }
      if (!response.ok) throw Error('Unavailable');
      const data = await response.json();
      if (!Array.isArray(data.items) || !Number.isSafeInteger(data.cursor)) throw Error('Invalid response');
      if (user !== null && user !== data.user) { accountChanged(); return; }
      const initial = cursor === null;
      user = data.user; cursor = data.cursor; badge(data.unread);
      document.querySelectorAll('[data-chat-unread]').forEach(node => { const count = data.chat_unread || 0; node.textContent = count > 99 ? '99+' : count; node.hidden = !count; });
      const sections = data.sections || {};
      document.querySelectorAll('[data-nav-unread]').forEach(node => {
        const count = Number(sections[node.dataset.navUnread]) || 0;
        node.textContent = count > 99 ? '99+' : String(count); node.hidden = !count;
        node.closest('a')?.classList.toggle('has-unread', !!count);
      });
      if (!initial) announce(data.items);
      timer = setTimeout(poll, data.has_more ? 50 : 15000);
    } catch {
      // A lost connection keeps the last known count; retry without losing the cursor.
    } finally {
      clearTimeout(timeout); pending = false;
      if (!timer && !stopped) timer = setTimeout(poll, 15000);
    }
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  window.addEventListener('online', poll);
  window.addEventListener('pageshow', poll);
  poll();
})();
