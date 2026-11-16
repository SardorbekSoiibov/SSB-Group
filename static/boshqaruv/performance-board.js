// Rahbar bahosi: sahifani yangilamasdan saqlash, izoh maydonini o'stirish, xatoni joyida ko'rsatish.
(function () {
  var forms = document.querySelectorAll('[data-score-form]');
  if (!forms.length) return;
  var scoredEl = document.querySelector('[data-scored]');
  var totalEl = document.querySelector('[data-scorable]');
  var bar = document.querySelector('[data-progress]');

  function grow(area) { area.style.height = 'auto'; area.style.height = Math.min(area.scrollHeight + 2, 160) + 'px'; }
  function setStatus(form, text, isError) {
    var el = form.querySelector('[data-status]');
    el.textContent = text || '';
    el.classList.toggle('is-error', !!isError);
  }

  forms.forEach(function (form) {
    var score = form.querySelector('input[name="score"]');
    var comment = form.querySelector('textarea[name="comment"]');
    var button = form.querySelector('button[type="submit"]');
    if (!score || !comment || !button) return;
    grow(comment);
    function dirty() {
      button.classList.add('is-dirty');
      button.textContent = form.classList.contains('is-scored') ? 'Yangilash' : 'Saqlash';
      score.classList.remove('is-invalid');
      comment.classList.remove('is-invalid');
    }
    comment.addEventListener('input', function () { grow(comment); dirty(); });
    score.addEventListener('input', dirty);
    comment.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); form.requestSubmit ? form.requestSubmit() : button.click(); }
    });

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var value = score.value.trim();
      var n = Number(value);
      if (value === '' || !isFinite(n) || n < 0 || n > 100 || Math.round(n) !== n) {
        score.classList.add('is-invalid'); score.focus();
        return setStatus(form, 'Ball 0 dan 100 gacha butun son bo‘lsin.', true);
      }
      if (comment.value.trim().length < 10) {
        comment.classList.add('is-invalid'); comment.focus();
        return setStatus(form, 'Izoh kamida 10 belgi bo‘lsin — xodim nima uchun shu bahoni olganini bilsin.', true);
      }
      button.disabled = true;
      button.textContent = 'Saqlanmoqda…';
      setStatus(form, '');
      fetch(window.location.pathname, {
        method: 'POST', body: new FormData(form), credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      }).then(function (r) {
        return r.json().catch(function () { return { ok: false, error: 'Saqlab bo‘lmadi (' + r.status + '). Sahifani yangilab ko‘ring.' }; });
      }).then(function (data) {
        if (!data.ok) throw new Error(data.error || 'Saqlab bo‘lmadi.');
        form.classList.add('is-scored');
        button.classList.remove('is-dirty');
        button.textContent = 'Saqlandi ✓';
        setStatus(form, data.by);
        if (scoredEl && totalEl && bar) {
          var total = Number(totalEl.textContent) || 0;
          scoredEl.textContent = data.scored;
          bar.style.setProperty('--done', (total ? Math.round(data.scored * 100 / total) : 0) + '%');
        }
      }).catch(function (err) {
        button.textContent = form.classList.contains('is-scored') ? 'Yangilash' : 'Saqlash';
        setStatus(form, err.message || 'Internet aloqasini tekshiring.', true);
      }).then(function () { button.disabled = false; });
    });
  });
})();

// Dushanba 00:00 gacha teskari sanoq. Vaqt tugaganda sahifa natijani ko'rsatish uchun yangilanadi.
(function () {
  var box = document.querySelector('[data-close-at]');
  if (!box) return;
  var target = Date.parse(box.getAttribute('data-close-at'));
  if (isNaN(target)) return;
  var cells = {};
  ['d', 'h', 'm', 's'].forEach(function (k) { cells[k] = box.querySelector('[data-unit="' + k + '"]'); });
  var reloaded = false;
  function pad(n) { return n < 10 ? '0' + n : String(n); }
  function tick() {
    var left = Math.max(0, Math.floor((target - Date.now()) / 1000));
    cells.d.textContent = Math.floor(left / 86400);
    cells.h.textContent = pad(Math.floor(left % 86400 / 3600));
    cells.m.textContent = pad(Math.floor(left % 3600 / 60));
    cells.s.textContent = pad(left % 60);
    if (left === 0 && !reloaded) {
      reloaded = true;
      // AI tahlili bir necha daqiqa olishi mumkin: biroz kutib yangilaymiz.
      setTimeout(function () { window.location.reload(); }, 90000);
    }
  }
  tick();
  setInterval(tick, 1000);
})();
