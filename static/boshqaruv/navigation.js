(()=>{'use strict';
 // Thin progress line for any real page change. It starts after a short delay, so fast pages show nothing.
 const progress=document.createElement('div');progress.className='nav-progress';progress.setAttribute('aria-hidden','true');document.body.append(progress);let progressTimer;
 const stopProgress=()=>{clearTimeout(progressTimer);progress.classList.remove('is-active');};
 window.addEventListener('beforeunload',()=>{progress.classList.add('is-active');clearTimeout(progressTimer);progressTimer=setTimeout(stopProgress,6000);});
 window.addEventListener('pageshow',stopProgress);
 const nav=document.querySelector('#sidebar-navigation');if(!nav)return;
 const search=document.querySelector('#sidebar-search'),empty=nav.querySelector('[data-nav-empty]'),status=document.querySelector('[data-nav-status]');
 const groups=[...nav.querySelectorAll('.nav-group')],links=[...nav.querySelectorAll('.nav-group>a')];
 const key='ssb-sidebar-scroll';let timer;
 const normalize=text=>text.toLocaleLowerCase().replace(/[\u2018\u2019\u02bb\u02bc'`]/g,'').trim();
 function savePosition(){try{sessionStorage.setItem(key,String(nav.scrollTop));}catch{}}
 function resetPending(){clearTimeout(timer);document.querySelectorAll('.app-rail a.is-pending').forEach(link=>{link.classList.remove('is-pending');link.removeAttribute('aria-busy');});if(status)status.textContent='';}
 function restore(){resetPending();if(search.value)return;try{const value=Number(sessionStorage.getItem(key));if(Number.isFinite(value))nav.scrollTop=value;}catch{}}
 search.addEventListener('input',()=>{
  const words=normalize(search.value).split(/\s+/).filter(Boolean);let count=0;
  groups.forEach(group=>{
   let visible=0;const heading=group.querySelector('p')?.textContent||'';
   group.querySelectorAll('a').forEach(link=>{const haystack=normalize(heading+' '+link.textContent);link.hidden=!words.every(word=>haystack.includes(word));if(!link.hidden){visible++;count++;}});
   group.hidden=visible===0;
  });
  if(empty)empty.hidden=count!==0;
  nav.scrollTop=0;
 });
 search.addEventListener('keydown',event=>{if(event.key==='Escape'&&search.value){event.preventDefault();search.value='';search.dispatchEvent(new Event('input'));search.focus();}if(event.key==='ArrowDown'){event.preventDefault();links.find(link=>!link.hidden&&!link.closest('[hidden]'))?.focus();}});
 document.querySelector('.app-rail').addEventListener('click',event=>{
  const link=event.target.closest('a[href]');if(!link||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank'||link.hasAttribute('download'))return;
  const url=new URL(link.href,location.href);if(url.origin!==location.origin)return;
  savePosition();resetPending();link.classList.add('is-pending');link.setAttribute('aria-busy','true');
  if(status)status.textContent=link.textContent.trim()+' sahifasi ochilmoqda.';
  document.body.classList.remove('nav-open');const scrim=document.querySelector('.scrim');if(scrim)scrim.hidden=true;
  // Native link navigation starts immediately; no request interception or delay.
  timer=setTimeout(resetPending,10000);
 });
 window.addEventListener('pagehide',savePosition);window.addEventListener('pageshow',restore);restore();
})();
