(()=>{'use strict';
 // Panel rangi butun kompaniya uchun bitta va serverda saqlanadi (sahifa uni <html style="--accent-custom">
 // orqali oladi). Tanlagich faqat direktorga (Asoschi) chiqariladi; server ham faqat unga ruxsat beradi.
 const root=document.documentElement;
 const isHex=v=>/^#[0-9a-f]{6}$/i.test(v||'');
 const current=()=>(root.style.getPropertyValue('--accent-custom')||'#007aff').trim().toLowerCase();
 let saved=current();
 // Eski versiyada har bir foydalanuvchi o'z brauzerida rang saqlar edi — endi kerak emas.
 try{Object.keys(localStorage).filter(k=>k.startsWith('ssb-accent')).forEach(k=>localStorage.removeItem(k));}catch{}
 // Hosila ranglar hex ko'rinishida (grafiklar canvas'i color-mix() ni har doim tushunmaydi).
 const mix=(hex,to,t)=>{const a=parseInt(hex.slice(1),16),b=parseInt(to.slice(1),16),c=s=>Math.round(((a>>s)&255)*(1-t)+((b>>s)&255)*t);return'#'+((1<<24)|(c(16)<<16)|(c(8)<<8)|c(0)).toString(16).slice(1);};
 function paint(hex){
  root.dataset.accent='custom';root.style.setProperty('--accent-custom',hex);
  root.style.setProperty('--accent-hover',mix(hex,'#000000',.14));
  root.style.setProperty('--accent-bright',mix(hex,'#ffffff',.12));
  root.style.setProperty('--accent-soft',mix(hex,'#ffffff',.88));
  root.style.setProperty('--accent-soft-dark',mix(hex,'#1c1c1e',.78));
  document.querySelectorAll('[data-accent-choice]:not(.accent-reset)').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.accentChoice.toLowerCase()===hex)));
  const input=document.querySelector('[data-accent-input]');if(input)input.value=hex;
  if(window.Chart)Object.values(Chart.instances).forEach(chart=>{chart.data.datasets.forEach(d=>{if(d.type!=='line'){d.backgroundColor=hex;d.hoverBackgroundColor=mix(hex,'#000000',.14);}else d.borderColor=hex;});chart.update('none');});
  document.dispatchEvent(new CustomEvent('ssb:accentchange',{detail:{accent:hex}}));
 }
 if(isHex(saved))paint(saved);else{saved='#007aff';paint(saved);}
 function csrf(){const m=document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);return m?decodeURIComponent(m[1]):(document.querySelector('[name=csrfmiddlewaretoken]')?.value||'');}
 let pending=null;
 async function save(hex){
  const picker=document.querySelector('[data-accent-url]');if(!picker||!isHex(hex))return;
  hex=hex.toLowerCase();if(hex===saved){paint(hex);return;}
  paint(hex);pending?.abort();pending=new AbortController();
  try{
   const body=new FormData();body.append('accent',hex);
   const response=await fetch(picker.dataset.accentUrl,{method:'POST',body,credentials:'same-origin',signal:pending.signal,headers:{'X-CSRFToken':csrf(),'Accept':'application/json'}});
   if(!response.ok)throw new Error(String(response.status));
   saved=(await response.json()).accent||hex;
   document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text:'Panel rangi butun kompaniya uchun saqlandi.'}}));
  }catch(error){
   if(error.name==='AbortError')return;
   paint(saved);
   document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text:'Rang saqlanmadi. Qayta urinib ko‘ring.',level:'error'}}));
  }
 }
 document.addEventListener('DOMContentLoaded',()=>paint(saved),{once:true});
 document.addEventListener('click',event=>{const b=event.target.closest('[data-accent-choice]');if(!b)return;event.preventDefault();save(b.dataset.accentChoice);});
 document.addEventListener('input',event=>{const i=event.target.closest('[data-accent-input]');if(i&&isHex(i.value))paint(i.value.toLowerCase());});
 document.addEventListener('change',event=>{const i=event.target.closest('[data-accent-input]');if(i&&isHex(i.value))save(i.value);});
 const key='ssb-boshqaruv-theme',media=matchMedia('(prefers-color-scheme: dark)');
 const valid=value=>['light','dark','system'].includes(value)?value:'system';
 let preference='system';try{preference=valid(localStorage.getItem(key));}catch{}
 function apply(){
  const resolved=preference==='system'?(media.matches?'dark':'light'):preference;
  root.dataset.theme=resolved;root.dataset.themePreference=preference;root.style.colorScheme=resolved;
  document.querySelectorAll('[data-theme-choice]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.themeChoice===preference)));
  document.querySelectorAll('[data-theme-label]').forEach(label=>label.textContent=preference==='system'?'Avto':resolved==='dark'?'Dark':'Light');
  document.dispatchEvent(new CustomEvent('ssb:themechange',{detail:{theme:resolved,preference}}));
 }
 apply();document.addEventListener('DOMContentLoaded',apply,{once:true});
 media.addEventListener('change',()=>{if(preference==='system')apply();});
 window.addEventListener('storage',event=>{if(event.key===key||event.key===null){preference=valid(event.newValue);apply();}});
 document.addEventListener('click',event=>{
  const choice=event.target.closest('[data-theme-choice]');
  if(choice){preference=valid(choice.dataset.themeChoice);try{localStorage.setItem(key,preference);}catch{}apply();const menu=choice.closest('details');if(menu){menu.open=false;menu.querySelector('summary')?.focus();}return;}
  document.querySelectorAll('.appearance-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;});
 });
 document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.appearance-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary')?.focus();});});
})();
document.addEventListener('DOMContentLoaded',()=>{const script=document.createElement('script');script.src='/static/boshqaruv/ios-management.js?v=4';script.defer=true;document.head.append(script);},{once:true});
// Employee form: function checkboxes (page and modal). Delegated, so it also works after the form is moved into a dialog.
(()=>{'use strict';
 const boxes=root=>[...root.querySelectorAll('[data-perm-group] input[type=checkbox]')];
 const update=root=>{const count=root.querySelector('[data-perm-count]');if(!count)return;const n=boxes(root).filter(b=>b.checked).length;count.textContent=n?`${n} ta funksiya ochiq`:'Hech narsa ochilmagan';};
 const scope=el=>el.closest('form')||document;
 document.addEventListener('click',e=>{
  const all=e.target.closest('[data-perm-all]'),none=e.target.closest('[data-perm-none]'),group=e.target.closest('[data-perm-toggle]');
  if(!all&&!none&&!group)return;e.preventDefault();
  if(group){const g=[...group.closest('[data-perm-group]').querySelectorAll('input[type=checkbox]')];const on=!g.every(b=>b.checked);g.forEach(b=>b.checked=on);}
  else{const root=scope(e.target);boxes(root).forEach(b=>b.checked=!!all);}
  update(scope(e.target));
 });
 document.addEventListener('change',e=>{if(e.target.closest('[data-perm-group]'))update(scope(e.target));});
 const init=root=>root.querySelectorAll('form').forEach(update);
 document.addEventListener('DOMContentLoaded',()=>init(document));
 document.addEventListener('ssb:formready',e=>init(e.detail?.root||document));
})();

// Sidebar: collapse to an icon rail (remembered per user), Ctrl+/ focuses the menu search, labels as tooltips while collapsed.
(()=>{'use strict';
 const root=document.documentElement,key='ssb-rail:'+(root.dataset.user||'anon'),wide=matchMedia('(min-width:1024px)');
 let collapsed=false;try{collapsed=localStorage.getItem(key)==='collapsed';}catch{}
 const isRail=()=>collapsed&&wide.matches;
 function apply(){root.dataset.rail=collapsed?'collapsed':'open';document.querySelectorAll('[data-rail-toggle]').forEach(b=>b.setAttribute('aria-expanded',String(!collapsed)));}
 function set(value){collapsed=value;try{localStorage.setItem(key,collapsed?'collapsed':'open');}catch{}apply();hide();}
 function focusSearch(){const input=document.getElementById('sidebar-search');if(!input)return;if(collapsed)set(false);setTimeout(()=>{input.focus();input.select();},collapsed?0:30);}
 apply();document.addEventListener('DOMContentLoaded',apply,{once:true});
 window.addEventListener('storage',e=>{if(e.key===key){collapsed=e.newValue==='collapsed';apply();}});
 document.addEventListener('click',e=>{
  if(e.target.closest('[data-rail-toggle]')){e.preventDefault();set(!collapsed);return;}
  if(isRail()&&e.target.closest('.app-rail .app-brand')){e.preventDefault();e.stopImmediatePropagation();set(false);return;}
  if(isRail()&&e.target.closest('.app-rail .rail-search')){e.preventDefault();set(false);setTimeout(()=>document.getElementById('sidebar-search')?.focus(),60);}
 },true);
 document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!e.altKey&&(e.key==='/'||e.code==='Slash')){if(!document.getElementById('sidebar-search'))return;e.preventDefault();e.stopImmediatePropagation();focusSearch();}},true);
 let tip=null,owner=null;
 function hide(){if(tip)tip.classList.remove('is-on');owner=null;}
 function show(el){
  const text=(el.dataset.railTip||el.querySelector(':scope > span:not(.avatar)')?.firstChild?.textContent||el.getAttribute('aria-label')||'').trim();if(!text)return;
  if(!tip){tip=document.createElement('div');tip.className='rail-tip';tip.setAttribute('role','tooltip');document.body.append(tip);}
  const r=el.getBoundingClientRect(),rail=el.closest('.app-rail').getBoundingClientRect();
  tip.textContent=text;tip.style.left=Math.round(rail.right+10)+'px';tip.style.top=Math.round(r.top+r.height/2)+'px';tip.classList.add('is-on');owner=el;
 }
 const target=node=>node.closest?.('.app-rail a, .app-rail [data-rail-tip]');
 document.addEventListener('mouseover',e=>{if(!isRail())return;const el=target(e.target);if(el&&el!==owner)show(el);});
 document.addEventListener('mouseout',e=>{if(!owner)return;const to=e.relatedTarget&&target(e.relatedTarget);if(to!==owner)hide();});
 document.addEventListener('focusin',e=>{if(!isRail())return;const el=target(e.target);if(el)show(el);});
 document.addEventListener('focusout',hide);
 document.addEventListener('scroll',hide,true);
})();
