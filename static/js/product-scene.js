/* "Qanday mahsulotlar quramiz": aylantirish bilan boshqariladigan sahna.
   Bo'lim ekranga qotadi; foydalanuvchi pastga aylantirgan sari qurilma 3D holatdan tekislanadi,
   ichidagi sahna esa sayt → CRM → Telegram bot bo'ylab "o'ynaydi". Hisob faqat bo'lim ko'rinib
   turganda va faqat transform/opacity bilan bajariladi. */
(function () {
  const reel = document.querySelector("[data-reel]");
  if (!reel) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const device = reel.querySelector(".reel-device");
  const screen = reel.querySelector(".reel-screen");
  const scene = reel.querySelector("[data-scene]");
  const chapters = [...reel.querySelectorAll(".reel-chapter")];
  const $ = (id) => document.getElementById("ps-" + id);

  // ---- yordamchi egri chiziqlar
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const prog = (t, a, b) => clamp((t - a) / (b - a));
  const easeOut = (x) => 1 - Math.pow(1 - x, 3);
  const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const spring = (x) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 - Math.exp(-6 * x) * Math.cos(9 * x));
  const lerp = (a, b, x) => a + (b - a) * x;
  const show = (el, x, dy = 24, s = 0.96) => {
    el.style.opacity = clamp(x * 1.4);
    el.style.transform = `translateY(${lerp(dy, 0, spring(x))}px) scale(${lerp(s, 1, spring(x))})`;
  };

  const D = 12, SCENE = 4, FADE = 0.35;
  const W = 1280, H = 800;

  // ---- statik bezaklar
  const bars = (id, n, css) => { for (let i = 0; i < n; i++) { const b = document.createElement("i"); b.style.cssText = css; $(id).append(b); } };
  bars("A-chart", 7, "flex:1;border-radius:6px;background:#adb9cb");
  bars("B-bars", 6, "width:6px;border-radius:3px;background:#495c77");
  bars("C-spark", 18, "flex:1;border-radius:5px;background:#adb9cb");
  $("C-typing").querySelectorAll("i").forEach((d) => (d.style.cssText = "width:9px;height:9px;border-radius:50%;background:#889bb5;display:block"));
  const hA = [0.42, 0.58, 0.5, 0.74, 0.66, 0.88, 1];
  const hB = [0.3, 0.5, 0.42, 0.7, 0.62, 1];
  const hC = [0.2, 0.32, 0.28, 0.4, 0.36, 0.5, 0.46, 0.58, 0.52, 0.66, 0.6, 0.7, 0.64, 0.78, 0.74, 0.86, 0.82, 1];

  // Sahnalar chegarada qisqa kesishadi — aylantirish to'xtagan joyda ekran bo'sh qolmaydi.
  const sceneAlpha = (t, start) => {
    const local = t - start;
    const first = start === 0, last = start === 2 * SCENE;
    const fadeIn = first ? 1 : prog(local, -FADE / 2, FADE / 2);
    const fadeOut = last ? 1 : 1 - prog(local, SCENE - FADE / 2, SCENE + FADE / 2);
    return easeInOut(Math.min(fadeIn, fadeOut));
  };

  // Kamera markazi (sahna koordinatalarida): tor ekranda harakat bo'layotgan joyga suriladi.
  const focusX = (t) => {
    const stops = [
      [0, 330], [2.6, 330], [3.2, 930],            // sayt: sarlavha → statistika
      [4.0, 250], [5.1, 250], [6.4, 660], [6.8, 1050], // CRM: ustun → ko'chirilgan karta → xabar
      [8.0, 340], [10.6, 340], [11.1, 970], [12, 970],  // bot: suhbat → buyurtma
    ];
    for (let i = 1; i < stops.length; i++) {
      const [t1, x1] = stops[i], [t0, x0] = stops[i - 1];
      if (t <= t1) return lerp(x0, x1, easeInOut(prog(t, t0, t1)));
    }
    return stops[stops.length - 1][1];
  };

  let fit = { scale: 1, viewW: W, viewH: H };
  const measure = () => {
    const w = screen.clientWidth, h = screen.clientHeight;
    const scale = Math.max(w / W, h / H);
    fit = { scale, viewW: w / scale, viewH: h / scale };
  };

  function render(t) {
    const a = sceneAlpha(t, 0), b = sceneAlpha(t, SCENE), c = sceneAlpha(t, 2 * SCENE);
    $("A").style.opacity = a; $("B").style.opacity = b; $("C").style.opacity = c;
    for (const [id, s] of [["A", 0], ["B", SCENE], ["C", 2 * SCENE]]) {
      const local = t - s;
      const inn = s === 0 ? 1 : prog(local, -FADE / 2, FADE + 0.2);
      const out = s === 2 * SCENE ? 0 : prog(local, SCENE - FADE / 2, SCENE + FADE / 2);
      $(id).style.transform = `perspective(1400px) translateZ(${lerp(-90, 0, easeOut(inn)) + lerp(0, 70, easeInOut(out))}px)`;
    }

    // A: sayt yig'iladi
    const lA = t;
    show($("A-nav"), prog(lA, 0.05, 0.6), -20, 1);
    show($("A-h1"), prog(lA, 0.25, 1.0), 30);
    show($("A-p"), prog(lA, 0.45, 1.15), 24);
    show($("A-btn"), prog(lA, 0.6, 1.3), 20, 0.9);
    show($("A-img"), prog(lA, 0.4, 1.3), 40, 0.9);
    [...$("A-cards").children].forEach((el, i) => show(el, prog(lA, 0.9 + i * 0.14, 1.7 + i * 0.14), 40, 0.94));
    [...$("A-chart").children].forEach((el, i) => (el.style.height = `${hA[i] * 100 * easeOut(prog(lA, 1.1 + i * 0.07, 1.9 + i * 0.07))}%`));
    $("A-count").textContent = Math.round(48 * easeOut(prog(lA, 1.2, 2.9)));
    $("A-btn").style.transform += ` scale(${1 - 0.06 * Math.sin(Math.PI * prog(lA, 2.55, 2.75))})`;

    // B: vazifa ustunga ko'chadi
    const lB = t - SCENE;
    const drag = easeInOut(prog(lB, 1.2, 2.4));
    const lift = Math.sin(Math.PI * prog(lB, 1.05, 2.55));
    const mv = $("B-move");
    mv.style.transform = `translate(${lerp(0, 416, drag)}px, ${lerp(0, -120, drag)}px) rotate(${lift * 3}deg) scale(${1 + lift * 0.04})`;
    mv.style.boxShadow = `0 ${18 + lift * 26}px ${40 + lift * 30}px -28px rgb(16 43 37 / ${0.45 + lift * 0.25})`;
    $("B-n2").textContent = drag > 0.98 ? 2 : 1;
    $("B-count").textContent = Math.round(lerp(96, 128, easeOut(prog(lB, 0.2, 3.4))));
    [...$("B-bars").children].forEach((el, i) => (el.style.height = `${hB[i] * 100 * easeOut(prog(lB, 0.2 + i * 0.08, 0.9 + i * 0.08))}%`));
    show($("B-toast"), prog(lB, 2.5, 3.2), 50, 0.92);

    // C: bot suhbati
    const lC = t - 2 * SCENE;
    show($("C-m1"), prog(lC, 0.15, 0.6), 18, 0.9);
    $("C-status").textContent = (lC > 0.6 && lC < 1.05) || (lC > 2.05 && lC < 2.6) ? "yozmoqda…" : "bot";
    show($("C-m2"), prog(lC, 1.05, 1.5), 18, 0.9);
    show($("C-kb"), prog(lC, 1.2, 1.7), 18, 0.94);
    show($("C-m3"), prog(lC, 1.85, 2.25), 18, 0.9);
    $("C-typing").style.opacity = lC > 2.25 && lC < 2.7 ? 1 : 0;
    [...$("C-typing").children].forEach((d, i) => (d.style.transform = `translateY(${-4 * Math.max(0, Math.sin(lC * 9 - i))}px)`));
    show($("C-m4"), prog(lC, 2.7, 3.1), 18, 0.9);
    $("C-count").textContent = Math.round(lerp(186, 214, easeOut(prog(lC, 0.1, 3.0))));
    [...$("C-spark").children].forEach((el, i) => (el.style.height = `${hC[i] * 100 * easeOut(prog(lC, 0.1 + i * 0.04, 0.8 + i * 0.04))}%`));
    show($("C-new"), prog(lC, 2.85, 3.4), 30, 0.94);
    $("C-prog").style.width = `${66 * easeInOut(prog(lC, 3.0, 3.9))}%`;

    // Kursor
    let cx = 1300, cy = 900, click = -1;
    if (t < SCENE) { const k = easeInOut(prog(lA, 1.7, 2.5)); cx = lerp(980, 140, k); cy = lerp(720, 470, k); click = lA - 2.6; }
    else if (t < 2 * SCENE) { const k = easeInOut(prog(lB, 0.4, 1.1)); cx = lerp(1100, 250, k) + lerp(0, 416, drag); cy = lerp(760, 460, k) + lerp(0, -120, drag); click = lB - 1.1; }
    else { const k = easeInOut(prog(lC, 1.4, 1.8)); cx = lerp(560, 150, k); cy = lerp(700, 360, k); click = lC - 1.8; }
    $("cursor").style.transform = `translate(${cx}px, ${cy}px)`;
    const r = clamp(click / 0.45);
    $("ripple").style.opacity = click > 0 && click < 0.45 ? 1 - r : 0;
    $("ripple").style.transform = `translate(${cx - 30}px, ${cy - 30}px) scale(${0.3 + r})`;

    // Kamera: sahnani ekranga joylash, tor ekranda harakat tomon surish
    const half = fit.viewW / 2;
    const camX = clamp(focusX(t), half, W - half) - half;
    const camY = (H - fit.viewH) / 2;
    scene.style.transform = `scale(${fit.scale}) translate(${-camX}px, ${-camY}px)`;

    // Bo'limlar
    const idx = Math.min(chapters.length - 1, Math.floor(t / SCENE));
    chapters.forEach((ch, i) => {
      ch.classList.toggle("is-active", i === idx);
      ch.setAttribute("aria-pressed", String(i === idx));
      ch.style.setProperty("--cp", i < idx ? 1 : i === idx ? ((t - i * SCENE) / SCENE).toFixed(3) : 0);
    });
  }

  // A compact timed showcase: choosing a product never moves the page.
  let shown = reduce ? 3.5 : .4, near = false, paused = reduce, frame = 0, last = 0;
  const playButton = reel.querySelector('.product-play');
  function updatePlay(){playButton.textContent=paused?'Davom ettirish':'To‘xtatish';playButton.setAttribute('aria-pressed',String(paused));}
  function tick(now){
    frame=0;if(!near||paused||document.hidden)return;
    const dt=Math.min(.06,(now-last)/1000);last=now;shown=(shown+dt*.72)%(D-.001);render(shown);
    frame=requestAnimationFrame(tick);
  }
  function play(){if(!frame&&near&&!paused&&!document.hidden){last=performance.now();frame=requestAnimationFrame(tick);}}
  function stop(){cancelAnimationFrame(frame);frame=0;}
  chapters.forEach((chapter,i)=>chapter.addEventListener('click',()=>{
    shown=i*SCENE+(reduce?3.5:.65);render(shown);play();
    if(!reduce)device.animate([{opacity:.5,transform:'translateY(8px) scale(.985)'},{opacity:1,transform:'none'}],{duration:380,easing:'cubic-bezier(.2,.7,.2,1)'});
  }));
  playButton.addEventListener('click',()=>{paused=!paused;updatePlay();paused?stop():play();});
  new IntersectionObserver(([entry])=>{near=entry.isIntersecting;near?play():stop();},{threshold:.1}).observe(reel);
  document.addEventListener('visibilitychange',()=>document.hidden?stop():play());
  new ResizeObserver(()=>{measure();render(shown);}).observe(screen);
  device.style.setProperty('--rx','0deg');device.style.setProperty('--sc','1');device.style.setProperty('--ty','0px');
  measure();render(shown);updatePlay();
})();
