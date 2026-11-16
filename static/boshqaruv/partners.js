(() => {
  'use strict';
  const open = id => {
    const dialog = document.getElementById(`partner-dialog-${id}`);
    if (dialog && !dialog.open) dialog.showModal();
  };
  document.querySelectorAll('[data-open-partner]').forEach(button =>
    button.addEventListener('click', () => open(button.dataset.openPartner)));
  document.querySelectorAll('.pt-dialog').forEach(dialog => {
    dialog.querySelectorAll('[data-close-dialog]').forEach(b => b.addEventListener('click', () => dialog.close()));
    dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
    if (dialog.hasAttribute('data-open-on-load')) dialog.showModal();
  });

  // Fayl tanlanganda: logo — oldindan ko'rish, shartnoma — fayl nomi.
  document.querySelectorAll('.pt-drop').forEach(drop => {
    const input = drop.querySelector('input[type=file]');
    const name = drop.querySelector('[data-file-name]');
    const preview = drop.querySelector('[data-logo-preview]');
    if (!input) return;
    const show = () => {
      const file = input.files && input.files[0];
      if (!file) return;
      drop.classList.add('has-file');
      name.textContent = `${file.name} · ${(file.size / 1048576).toFixed(file.size > 1048576 ? 1 : 2)} MB`;
      if (preview && file.type.startsWith('image/')) {
        const img = document.createElement('img');
        img.alt = '';
        img.src = URL.createObjectURL(file);
        img.onload = () => URL.revokeObjectURL(img.src);
        preview.replaceChildren(img);
      }
    };
    input.addEventListener('change', show);
    ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, () => drop.classList.remove('is-over')));
    drop.addEventListener('drop', e => {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; show(); }
    });
  });

  // Ikki marta yuborishning oldini olish
  document.querySelectorAll('[data-partner-form]').forEach(form => form.addEventListener('submit', () => {
    const submit = form.querySelector('[type=submit]');
    if (submit) { submit.disabled = true; submit.lastChild.textContent = ' Saqlanmoqda…'; }
  }));
})();
