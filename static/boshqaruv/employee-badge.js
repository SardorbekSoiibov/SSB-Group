(()=>{'use strict';
 const card=document.querySelector('[data-badge-card]');if(!card)return;
 const stage=card.closest('[data-badge-stage]');
 const buttons=[...document.querySelectorAll('[data-badge-side]')];
 const calm=matchMedia('(prefers-reduced-motion: reduce)');
 let back=false,drag=null,moved=false;
 function side(isBack){
  back=isBack;card.classList.toggle('is-back',back);
  card.style.setProperty('--ry','0deg');card.style.setProperty('--rx','0deg');
  buttons.forEach(b=>b.setAttribute('aria-pressed',String((b.dataset.badgeSide==='back')===back)));
 }
 buttons.forEach(b=>b.addEventListener('click',()=>side(b.dataset.badgeSide==='back')));
 card.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();side(!back);}if(e.key==='ArrowLeft'||e.key==='ArrowRight')side(!back);});

 // Sudrab aylantirish: yarmidan ko'p burilsa — boshqa tomon
 card.addEventListener('pointerdown',e=>{
  if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,id:e.pointerId};moved=false;
  card.setPointerCapture(e.pointerId);
 });
 card.addEventListener('pointermove',e=>{
  if(drag&&e.pointerId===drag.id){
   const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
   if(!moved&&Math.hypot(dx,dy)>6){moved=true;card.classList.add('is-dragging');}
   if(!moved)return;
   card.style.setProperty('--ry',`${Math.max(-170,Math.min(170,dx*0.9))}deg`);
   card.style.setProperty('--rx',`${Math.max(-20,Math.min(20,-dy*0.25))}deg`);
   return;
  }
  if(calm.matches||e.pointerType!=='mouse')return;
  const r=card.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
  card.style.setProperty('--ry',`${(x*16).toFixed(2)}deg`);card.style.setProperty('--rx',`${(-y*12).toFixed(2)}deg`);
  card.style.setProperty('--gx',`${(120-(x+.5)*140).toFixed(1)}%`);
 });
 const end=e=>{
  if(!drag||e.pointerId!==drag.id)return;
  const turned=parseFloat(card.style.getPropertyValue('--ry'))||0;
  card.classList.remove('is-dragging');drag=null;
  if(!moved){side(!back);return;}
  if(Math.abs(turned)>70)side(!back);else{card.style.setProperty('--ry','0deg');card.style.setProperty('--rx','0deg');}
 };
 card.addEventListener('pointerup',end);card.addEventListener('pointercancel',end);
 card.addEventListener('pointerleave',()=>{if(drag)return;card.style.setProperty('--ry','0deg');card.style.setProperty('--rx','0deg');});

 // "Bedjik" tezkor tugmasi — kartaga silliq aylantirish
 document.querySelector('[data-badge-jump]')?.addEventListener('click',e=>{
  e.preventDefault();document.getElementById('bedjik')?.scrollIntoView({behavior:calm.matches?'auto':'smooth',block:'start'});
  setTimeout(()=>card.focus({preventScroll:true}),calm.matches?0:500);
 });
 stage?.addEventListener('dragstart',e=>e.preventDefault());
})();
