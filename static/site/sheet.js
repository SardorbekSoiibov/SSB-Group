// Telefonda kirish oynasi (pastki "sheet"): tepadagi tutqichdan pastga surilsa yopiladi,
// klaviatura ochilganda bosilgan maydon ko'rinadigan joyga suriladi.
(() => {
  'use strict';
  const dialog = document.getElementById('login-modal');
  if (!dialog) return;
  const phone = matchMedia('(max-width:640px)');
  let drag = null;

  dialog.addEventListener('pointerdown', event => {
    if (!phone.matches || !dialog.open || event.target.closest('input,button,a,label')) return;
    const top = dialog.getBoundingClientRect().top;
    if (event.clientY - top > 48 || dialog.scrollTop > 0) return; // faqat tepadagi tutqich hududi
    drag = { id: event.pointerId, y: event.clientY, t: performance.now(), dy: 0 };
    dialog.setPointerCapture(event.pointerId);
    dialog.style.transition = 'none';
  });
  dialog.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dy = event.clientY - drag.y;
    drag.dy = dy > 0 ? dy : dy / 6;
    dialog.style.transform = `translateY(${drag.dy}px)`;
  });
  const end = event => {
    if (!drag || drag.id !== event.pointerId) return;
    const { dy, t } = drag;
    drag = null;
    const fast = dy / Math.max(1, performance.now() - t) > 0.55 && dy > 30;
    dialog.style.transition = 'transform .3s cubic-bezier(.2,.8,.2,1)';
    if (dy > Math.min(140, dialog.offsetHeight * 0.25) || fast) {
      dialog.style.transform = 'translateY(100%)';
      setTimeout(() => { dialog.querySelector('.login-modal-close')?.click(); dialog.style.transform = ''; dialog.style.transition = ''; }, 260);
    } else {
      dialog.style.transform = '';
    }
  };
  dialog.addEventListener('pointerup', end);
  dialog.addEventListener('pointercancel', end);

  dialog.addEventListener('focusin', event => {
    if (!phone.matches || !event.target.matches('input')) return;
    setTimeout(() => event.target.scrollIntoView({ block: 'center', behavior: 'smooth' }), 300);
  });
})();
