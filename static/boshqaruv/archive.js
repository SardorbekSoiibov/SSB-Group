(() => {
  'use strict';
  const focusField = root => root.querySelector('.invalid input, input:not([type=hidden])')?.focus();
  const gate = document.querySelector('[data-archive-gate]');
  if (gate) {
    // Rendered open so it also works without JavaScript; showModal makes the page behind inert.
    if (gate.showModal) { gate.removeAttribute('open'); gate.showModal(); }
    // The gate cannot be dismissed: leaving is an explicit link, and nothing sits behind it anyway.
    // Browsers may ignore preventDefault on cancel before any user activation, so reopen as a last resort.
    gate.addEventListener('cancel', event => event.preventDefault());
    gate.addEventListener('keydown', event => { if (event.key === 'Escape') event.preventDefault(); });
    gate.addEventListener('close', () => { gate.showModal(); focusField(gate.querySelector('[data-archive-view]:not([hidden])') || gate); });
    gate.addEventListener('click', event => {
      const button = event.target.closest('[data-archive-switch]');
      if (!button) return;
      gate.querySelectorAll('[data-archive-view]').forEach(view => { view.hidden = view.dataset.archiveView !== button.dataset.archiveSwitch; });
      focusField(gate.querySelector('[data-archive-view]:not([hidden])'));
    });
    focusField(gate.querySelector('[data-archive-view]:not([hidden])') || gate);
  }
  // Download question: leaving the sheet returns to the archive; a cookie confirms the file really started.
  const challenge = document.querySelector('#archive-challenge');
  if (challenge) {
    const back = () => location.assign(challenge.dataset.archiveBack);
    if (challenge.showModal) { challenge.removeAttribute('open'); challenge.showModal(); }
    challenge.addEventListener('close', back);
    focusField(challenge);
    const form = challenge.querySelector('#archive-challenge-form');
    form.addEventListener('submit', () => {
      const token = Array.from(crypto.getRandomValues(new Uint8Array(12)), byte => byte.toString(16).padStart(2, '0')).join('');
      const button = form.querySelector('button[type=submit]'), label = form.querySelector('[data-challenge-label]');
      form.elements.download_token.value = token;
      // Disabled only after this tick, so the browser still submits the form normally.
      setTimeout(() => { button.disabled = true; label.textContent = 'Tekshirilmoqda…'; });
      const started = Date.now(), timer = setInterval(() => {
        if (document.cookie.split('; ').includes('ssb_archive_download=' + token)) {
          clearInterval(timer);
          challenge.querySelector('[data-challenge-view=question]').hidden = true;
          challenge.querySelector('[data-challenge-view=done]').hidden = false;
          challenge.querySelector('[data-challenge-view=done] a')?.focus();
        } else if (Date.now() - started > 120000) { clearInterval(timer); button.disabled = false; label.textContent = 'Qayta urinish'; }
      }, 200);
    });
  }
  const open = dialog => { dialog.showModal(); focusField(dialog); };
  document.querySelectorAll('[data-archive-open]').forEach(button => button.addEventListener('click', () => open(document.getElementById(button.dataset.archiveOpen))));
  document.querySelectorAll('dialog.archive-modal:not([data-archive-gate]):not(#archive-challenge)').forEach(dialog => {
    dialog.addEventListener('click', event => {
      // The dialog's own padding is also event.target, so only a click truly outside it counts as the backdrop.
      const box = dialog.getBoundingClientRect();
      const outside = event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom);
      if (outside || event.target.closest('[data-archive-close]')) dialog.close();
    });
    if (dialog.hasAttribute('data-archive-autoopen')) open(dialog);
  });
  document.querySelectorAll('[data-archive-autosubmit]').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));

  // Upload sheet: the file input becomes a drop zone and suggests a project name from the file.
  const size = bytes => bytes < 1048576 ? (bytes / 1024).toFixed(1) + ' KB' : (bytes / 1048576).toFixed(1) + ' MB';
  document.addEventListener('ssb:formready', event => {
    const form = event.detail.root.querySelector('.archive-upload-form'), field = form?.querySelector('[data-field=file]');
    const input = field?.querySelector('input[type=file]');
    if (!input || field.querySelector('.archive-drop')) return;
    const zone = document.createElement('div'), title = document.createElement('strong'), hint = document.createElement('small');
    zone.className = 'archive-drop'; title.textContent = 'Faylni shu yerga tashlang yoki tanlang';
    hint.textContent = field.querySelector(':scope > small')?.textContent || 'RAR yoki ZIP';
    field.querySelector(':scope > small')?.remove();
    input.before(zone); zone.append(title, hint, input);
    ['dragenter', 'dragover'].forEach(name => zone.addEventListener(name, () => zone.classList.add('is-over')));
    ['dragleave', 'drop'].forEach(name => zone.addEventListener(name, () => zone.classList.remove('is-over')));
    input.addEventListener('change', () => {
      const file = input.files[0]; zone.classList.toggle('has-file', !!file);
      if (!file) return;
      title.textContent = file.name; hint.textContent = size(file.size);
      const name = form.querySelector('[name=project_name]');
      if (name && !name.value.trim()) name.value = file.name.replace(/[.][^.]+$/, '').replace(/[-_]+/g, ' ').trim().slice(0, 200);
    });
  });
  // A rejected upload without the sheet (plain form post) reopens it so the error is visible.
  document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('#archive-upload .field-error, #archive-upload .form-alert')) document.querySelector('[data-record-template=archive-upload]')?.click();
  });
})();
