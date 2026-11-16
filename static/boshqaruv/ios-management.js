(() => {
  document.querySelectorAll('.app-navigation .nav-group').forEach((group, index) => {
    const title = group.querySelector(':scope > p');
    if (!title) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'nav-group-collapse';
    button.setAttribute('aria-label', `${title.textContent.trim()} bo‘limini yig‘ish yoki ochish`);
    button.setAttribute('aria-expanded', 'true');
    button.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">expand_more</span><i data-lucide="chevron-down" aria-hidden="true"></i>';
    title.append(button);
    const storageKey = `ssb-nav-group-v3:${index}`;
    const hasActivePage = Boolean(group.querySelector('[aria-current="page"]'));
    try {
      if (!hasActivePage && localStorage.getItem(storageKey) === 'closed') {
        group.classList.add('is-collapsed');
        button.setAttribute('aria-expanded', 'false');
      }
    } catch {}
    const toggle = () => {
      const collapsed = group.classList.toggle('is-collapsed');
      button.setAttribute('aria-expanded', String(!collapsed));
      try { localStorage.setItem(storageKey, collapsed ? 'closed' : 'open'); } catch {}
    };
    button.addEventListener('click', event => { event.stopPropagation(); toggle(); });
    title.addEventListener('click', event => { if (!event.target.closest('button')) toggle(); });
  });

  document.querySelectorAll('.panel').forEach((panel, index) => {
    if (panel.closest('dialog') || panel.dataset.iosCollapsible === 'false') return;
    const head = panel.querySelector(':scope > .panel-head');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'panel-collapse-button';
    button.setAttribute('aria-label', 'Bo‘limni yig‘ish yoki ochish');
    button.setAttribute('aria-expanded', 'true');
    button.innerHTML = '<span class="material-symbols-rounded" aria-hidden="true">expand_more</span><i data-lucide="chevron-down" aria-hidden="true"></i>';
    panel.dataset.iosCollapsible = 'true';
    if (head) head.append(button);
    else {
      panel.classList.add('panel-collapse-no-head');
      panel.prepend(button);
    }
    const storageKey = `ssb-panel:${location.pathname}:${index}`;
    try {
      if (localStorage.getItem(storageKey) === 'closed') {
        panel.classList.add('is-collapsed');
        button.setAttribute('aria-expanded', 'false');
      }
    } catch {}
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      const collapsed = panel.classList.toggle('is-collapsed');
      button.setAttribute('aria-expanded', String(!collapsed));
      try { localStorage.setItem(storageKey, collapsed ? 'closed' : 'open'); } catch {}
    });
  });

  if (document.querySelector('[data-lucide]')) {
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js';
    script.defer = true;
    script.onload = () => {
      window.lucide?.createIcons();
      document.body.classList.add('lucide-ready');
    };
    document.head.append(script);
  }
})();
