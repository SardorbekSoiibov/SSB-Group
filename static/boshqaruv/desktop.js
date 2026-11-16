(() => {
  'use strict';
  const dialog = document.querySelector('#desktop-dialog');
  if (!dialog) return;
  const view = name => dialog.querySelectorAll('[data-desktop-view]').forEach(node => { node.hidden = node.dataset.desktopView !== name; });
  document.querySelector('[data-desktop-open]').addEventListener('click', () => { view('start'); dialog.showModal(); });
  dialog.addEventListener('click', event => {
    const box = dialog.getBoundingClientRect();
    const outside = event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom);
    if (outside || event.target.closest('[data-desktop-close]')) dialog.close();
  });
  // The link downloads natively; this only tells the person that it started.
  dialog.querySelector('#desktop-download').addEventListener('click', () => setTimeout(() => view('done'), 150));
})();
