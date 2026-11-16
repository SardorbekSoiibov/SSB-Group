// Xodimlar chati — iPhone 16 ko'rinishidagi suzuvchi oyna.
// Tugma yoki chat havolasi bosilsa chiqadi; yuqori/pastki chetidan pastga surilsa yopiladi.
(() => {
  'use strict';
  const launcher = document.querySelector('[data-chat-launcher]');
  const phone = document.getElementById('chat-phone');
  if (!launcher || !phone) return;
  const frame = phone.querySelector('[data-chat-frame]');
  const loading = phone.querySelector('[data-chat-loading]');
  const clock = phone.querySelector('[data-chat-clock]');
  const home = new URL(launcher.dataset.chatSrc, location.href).pathname;
  const chatPath = new RegExp('^' + home.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(\\d+/)?$');
  const KEY = 'ssb-chat-phone';
  let current = null, clockTimer = null;

  const store = value => { try { value ? sessionStorage.setItem(KEY, value) : sessionStorage.removeItem(KEY); } catch {} };
  const read = () => { try { return sessionStorage.getItem(KEY); } catch { return null; } };
  const isOpen = () => phone.classList.contains('is-open');

  function tick() {
    const now = new Date();
    clock.textContent = now.getHours() + ':' + String(now.getMinutes()).padStart(2, '0');
  }

  function load(path) {
    if (current === path) return;
    current = path; loading.hidden = false;
    frame.src = path;
  }

  function open(path, instant) {
    load(path || current || home);
    if (instant) { phone.classList.add('no-anim'); requestAnimationFrame(() => requestAnimationFrame(() => phone.classList.remove('no-anim'))); }
    phone.style.transform = '';
    phone.classList.add('is-open');
    phone.removeAttribute('inert'); phone.setAttribute('aria-hidden', 'false');
    launcher.setAttribute('aria-expanded', 'true');
    document.body.classList.add('chat-phone-open');
    tick(); clearInterval(clockTimer); clockTimer = setInterval(tick, 15000);
    store(current);
  }

  function close() {
    const hadFocus = phone.contains(document.activeElement) || document.activeElement === frame;
    phone.style.transform = '';
    phone.classList.remove('is-open');
    phone.setAttribute('inert', ''); phone.setAttribute('aria-hidden', 'true');
    launcher.setAttribute('aria-expanded', 'false');
    document.body.classList.remove('chat-phone-open');
    clearInterval(clockTimer); store(null);
    if (hadFocus) launcher.focus();
  }

  frame.addEventListener('load', () => {
    loading.hidden = true;
    try {
      const path = frame.contentWindow.location.pathname;
      if (chatPath.test(path)) { current = path; if (isOpen()) store(path); }
    } catch {}
  });

  launcher.addEventListener('click', () => (isOpen() ? close() : open()));

  // Menyu, bildirishnoma va boshqa joylardagi chat havolalari endi sahifa emas, shu oynani ochadi.
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target === '_blank') return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || !chatPath.test(url.pathname)) return;
    event.preventDefault(); event.stopPropagation();
    document.querySelector('.scrim:not([hidden])')?.click(); // telefonda ochiq menyuni yopish
    open(url.pathname);
  }, true);

  document.addEventListener('keydown', event => { if (event.key === 'Escape' && isOpen() && !document.querySelector('dialog[open]')) close(); });

  // Pastga surib yopish
  let drag = null;
  phone.querySelectorAll('[data-chat-grab]').forEach(zone => {
    zone.addEventListener('pointerdown', event => {
      if (!isOpen() || (event.pointerType === 'mouse' && event.button !== 0)) return;
      drag = { id: event.pointerId, y: event.clientY, t: performance.now(), dy: 0, zone };
      zone.setPointerCapture(event.pointerId);
    });
    zone.addEventListener('pointermove', event => {
      if (!drag || drag.id !== event.pointerId) return;
      const dy = event.clientY - drag.y;
      drag.dy = dy > 0 ? dy : dy / 6; // yuqoriga deyarli qimirlamaydi
      if (Math.abs(drag.dy) > 3) phone.classList.add('is-dragging');
      phone.style.transform = `translateY(${drag.dy}px)`;
    });
    const end = event => {
      if (!drag || drag.id !== event.pointerId) return;
      const { dy, t } = drag; drag = null;
      const speed = dy / Math.max(1, performance.now() - t);
      phone.classList.remove('is-dragging');
      if (dy > Math.min(140, phone.offsetHeight * .22) || (speed > .55 && dy > 30)) close();
      else phone.style.transform = '';
    };
    zone.addEventListener('pointerup', end);
    zone.addEventListener('pointercancel', end);
  });

  // Sahifalar orasida o'tganda chat ochiq qolsin.
  const saved = read();
  if (saved && chatPath.test(saved)) open(saved, true);
})();
