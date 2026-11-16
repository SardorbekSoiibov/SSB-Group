// SSB zamonaviy ochiladigan ro'yxat.
// Yopiq <select> o'z uslubida qoladi (forma, validatsiya, yuborish o'zgarmaydi). Faqat ochilganda brauzerning
// eski ro'yxati o'rniga zamonaviy ro'yxat chiqadi: qorong'i/yorug' rejim, tanlangan belgisi, klaviatura, qidiruv.
// Telefonda (sensorli ekran) telefonning o'z tanlash oynasi qoladi — u qulayroq.
(function () {
  'use strict';
  if (window.__ssbSelect) return;
  window.__ssbSelect = true;
  var coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  if (coarse) return;

  var supportsPopover = typeof HTMLElement !== 'undefined' && 'popover' in HTMLElement.prototype;
  var state = null; // {select, panel, list, items, active, search}
  var uid = 0;

  function eligible(select) {
    return select && select.tagName === 'SELECT' && !select.multiple && !(select.size > 1) &&
      !select.disabled && !select.closest('[data-native-select]');
  }

  function close(restoreFocus) {
    if (!state) return;
    var s = state;
    state = null;
    s.select.removeAttribute('aria-expanded');
    try { if (s.popover) s.panel.hidePopover(); } catch (e) { /* allaqachon yopiq */ }
    s.panel.remove();
    window.removeEventListener('resize', onViewport, true);
    window.removeEventListener('scroll', onScroll, true);
    if (restoreFocus) s.select.focus({ preventScroll: true });
  }

  function onViewport() { close(false); }
  function onScroll(e) {
    if (state && !state.panel.contains(e.target)) close(false);
  }

  function choose(index) {
    var s = state;
    if (!s) return;
    var option = s.select.options[index];
    if (!option || option.disabled) return;
    var changed = s.select.selectedIndex !== index;
    s.select.selectedIndex = index;
    close(true);
    if (changed) {
      s.select.dispatchEvent(new Event('input', { bubbles: true }));
      s.select.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  function setActive(i, scroll) {
    var s = state;
    if (!s || !s.items.length) return;
    var visible = s.items.filter(function (it) { return !it.el.hidden && !it.disabled; });
    if (!visible.length) return;
    if (i < 0) i = 0;
    if (i >= visible.length) i = visible.length - 1;
    s.items.forEach(function (it) { it.el.classList.remove('is-active'); });
    var item = visible[i];
    item.el.classList.add('is-active');
    s.active = i;
    s.list.setAttribute('aria-activedescendant', item.el.id);
    if (scroll) item.el.scrollIntoView({ block: 'nearest' });
  }

  function visibleIndexOf(optionIndex) {
    var visible = state.items.filter(function (it) { return !it.el.hidden && !it.disabled; });
    for (var k = 0; k < visible.length; k++) if (visible[k].index === optionIndex) return k;
    return 0;
  }

  function filter(text) {
    var q = text.trim().toLowerCase();
    var shown = 0;
    state.items.forEach(function (it) {
      var hit = !q || it.label.toLowerCase().indexOf(q) !== -1;
      it.el.hidden = !hit;
      if (hit) shown++;
    });
    state.list.querySelectorAll('.ssb-select-group').forEach(function (g) {
      var next = g.nextElementSibling, any = false;
      while (next && !next.classList.contains('ssb-select-group')) { if (!next.hidden) any = true; next = next.nextElementSibling; }
      g.hidden = !any;
    });
    state.empty.hidden = shown > 0;
    setActive(0, true);
  }

  function position(select, panel) {
    var r = select.getBoundingClientRect();
    var vw = document.documentElement.clientWidth, vh = window.innerHeight;
    var width = Math.max(r.width, 200);
    panel.style.minWidth = width + 'px';
    panel.style.maxWidth = Math.max(width, Math.min(420, vw - 16)) + 'px';
    var below = vh - r.bottom - 12, above = r.top - 12;
    var up = below < 240 && above > below;
    var room = Math.max(160, Math.min(380, up ? above : below));
    panel.style.maxHeight = room + 'px';
    var left = Math.min(Math.max(8, r.left), vw - width - 8);
    panel.style.left = left + 'px';
    if (up) { panel.style.top = ''; panel.style.bottom = (vh - r.top + 6) + 'px'; panel.classList.add('is-up'); }
    else { panel.style.bottom = ''; panel.style.top = (r.bottom + 6) + 'px'; panel.classList.remove('is-up'); }
  }

  function open(select) {
    if (state && state.select === select) return close(true);
    close(false);
    var panel = document.createElement('div');
    panel.className = 'ssb-select-panel';
    var dialog = select.closest('dialog[open]');
    // Modal oyna ichida ro'yxat oynadan ustida turishi uchun top layer (popover) kerak; boshqa joyda oddiy qatlam yetarli.
    var usePopover = supportsPopover && !!dialog;
    if (usePopover) panel.setAttribute('popover', 'manual');
    var listId = 'ssb-select-' + (++uid);
    var search = null;
    if (select.options.length > 9) {
      search = document.createElement('input');
      search.type = 'search';
      search.className = 'ssb-select-search';
      search.placeholder = 'Qidirish…';
      search.setAttribute('aria-label', 'Ro‘yxatdan qidirish');
      search.autocomplete = 'off';
      panel.appendChild(search);
    }
    var list = document.createElement('div');
    list.className = 'ssb-select-list';
    list.id = listId;
    list.setAttribute('role', 'listbox');
    list.tabIndex = -1;
    var label = select.getAttribute('aria-label') || (select.labels && select.labels[0] && select.labels[0].textContent.trim()) || '';
    if (label) list.setAttribute('aria-label', label);
    panel.appendChild(list);
    var empty = document.createElement('p');
    empty.className = 'ssb-select-empty';
    empty.textContent = 'Hech narsa topilmadi';
    empty.hidden = true;
    panel.appendChild(empty);

    var items = [];
    var lastGroup = null;
    Array.prototype.forEach.call(select.options, function (option, index) {
      var group = option.parentElement && option.parentElement.tagName === 'OPTGROUP' ? option.parentElement : null;
      if (group && group !== lastGroup) {
        var g = document.createElement('div');
        g.className = 'ssb-select-group';
        g.textContent = group.label;
        list.appendChild(g);
      }
      lastGroup = group;
      if (option.hidden) return;
      var el = document.createElement('div');
      el.className = 'ssb-select-option' + (option.selected ? ' is-selected' : '') + (option.disabled ? ' is-disabled' : '');
      el.id = listId + '-' + index;
      el.setAttribute('role', 'option');
      el.setAttribute('aria-selected', option.selected ? 'true' : 'false');
      if (option.disabled) el.setAttribute('aria-disabled', 'true');
      var text = option.textContent.trim() || '—';
      var span = document.createElement('span');
      span.textContent = text;
      el.appendChild(span);
      el.addEventListener('mousedown', function (e) { e.preventDefault(); });
      el.addEventListener('click', function () { choose(index); });
      el.addEventListener('mousemove', function () {
        if (!el.classList.contains('is-active') && !option.disabled) setActive(visibleIndexOf(index), false);
      });
      list.appendChild(el);
      items.push({ el: el, index: index, label: text, disabled: option.disabled });
    });

    (dialog || document.body).appendChild(panel);
    state = { select: select, panel: panel, list: list, items: items, active: 0, search: search, empty: empty, popover: usePopover };
    if (usePopover) { try { panel.showPopover(); } catch (e) { /* eski brauzer */ } }
    position(select, panel);
    select.setAttribute('aria-expanded', 'true');
    setActive(visibleIndexOf(select.selectedIndex), true);
    if (search) {
      search.addEventListener('input', function () { filter(search.value); });
      search.addEventListener('keydown', keys);
      search.focus({ preventScroll: true });
    }
    window.addEventListener('resize', onViewport, true);
    window.addEventListener('scroll', onScroll, true);
  }

  function keys(e) {
    if (!state) return;
    var visible = state.items.filter(function (it) { return !it.el.hidden && !it.disabled; });
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(state.active + 1, true); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(state.active - 1, true); }
    else if (e.key === 'Home') { e.preventDefault(); setActive(0, true); }
    else if (e.key === 'End') { e.preventDefault(); setActive(visible.length - 1, true); }
    else if (e.key === 'PageDown') { e.preventDefault(); setActive(state.active + 8, true); }
    else if (e.key === 'PageUp') { e.preventDefault(); setActive(state.active - 8, true); }
    else if (e.key === 'Enter' || (e.key === ' ' && !state.search)) { e.preventDefault(); if (visible[state.active]) choose(visible[state.active].index); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(true); }
    else if (e.key === 'Tab') { close(false); }
    else if (!state.search && e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
      // Harf bosilsa — shu harf bilan boshlanadigan variantga o'tish.
      var ch = e.key.toLowerCase();
      for (var k = 1; k <= visible.length; k++) {
        var j = (state.active + k) % visible.length;
        if (visible[j].label.toLowerCase().indexOf(ch) === 0) { setActive(j, true); break; }
      }
    }
  }

  document.addEventListener('mousedown', function (e) {
    var select = e.target.closest && e.target.closest('select');
    if (select && e.button === 0 && eligible(select)) {
      e.preventDefault();
      select.focus({ preventScroll: true });
      open(select);
      return;
    }
    if (state && !state.panel.contains(e.target)) close(false);
  }, true);

  document.addEventListener('keydown', function (e) {
    if (state) {
      if (state.search && e.target === state.search) return;
      if (e.target === state.select || state.panel.contains(e.target)) return keys(e);
    }
    var select = e.target;
    if (!select || select.tagName !== 'SELECT' || !eligible(select)) return;
    if (e.key === ' ' || e.key === 'Enter' || (e.altKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) || e.key === 'F4') {
      e.preventDefault();
      open(select);
    }
  }, true);

  document.addEventListener('focusin', function (e) {
    if (state && e.target !== state.select && !state.panel.contains(e.target)) close(false);
  });
})();
