(()=>{'use strict';
 const dialog=document.querySelector('#record-dialog');if(!dialog||!dialog.showModal)return;
 const body=dialog.querySelector('[data-record-body]'),title=dialog.querySelector('#record-title'),close=dialog.querySelector('[data-record-close]');
 let busy=false,opener=null;const notices='ssb-modal-notices',projectRequests=new WeakMap();
 const errors=form=>!!form.querySelector('.invalid,.field-error,.form-alert,.errorlist');
 const primary=doc=>doc.querySelector('form[data-modal-source]:not([data-confirm])');
 const formRoute=url=>/\/(yangi|tahrirlash)\/$/.test(url.pathname)||/\/rollar\/\d+\/$/.test(url.pathname)||/\/hisob\/parol\/$/.test(url.pathname);
 function message(text){let node=body.querySelector('[data-record-error]');if(!node){node=document.createElement('p');node.className='form-alert';node.dataset.recordError='';node.setAttribute('role','alert');body.prepend(node);}node.textContent=text;}
 function mount(source,label,url){
  const form=source.cloneNode(true);form.hidden=false;form.removeAttribute('id');form.action=url;form.dataset.recordActive='';form.removeAttribute('data-record-template-source');
  const ids=new Map();form.querySelectorAll('[id]').forEach(element=>{const old=element.id;const next='record-'+old;ids.set(old,next);element.id=next;});
  form.querySelectorAll('label[for]').forEach(label=>{if(ids.has(label.htmlFor))label.htmlFor=ids.get(label.htmlFor);});
  form.querySelectorAll('[aria-describedby],[aria-labelledby],[aria-controls]').forEach(element=>{for(const name of ['aria-describedby','aria-labelledby','aria-controls'])if(element.hasAttribute(name))element.setAttribute(name,element.getAttribute(name).split(/\s+/).map(id=>ids.get(id)||id).join(' '));});

  form.querySelectorAll('.form-footer a.button').forEach(link=>{if(!/Bekor/.test(link.textContent))return;const cancel=document.createElement('button');cancel.type='button';cancel.className='button';cancel.dataset.recordClose='';cancel.textContent=link.textContent;link.replaceWith(cancel);});
  body.replaceChildren(form);title.textContent=label;document.dispatchEvent(new CustomEvent('ssb:formready',{detail:{root:body}}));
  if(!dialog.open)dialog.showModal();
  requestAnimationFrame(()=>{const field=form.querySelector('.invalid input,.invalid select,.invalid textarea,[aria-invalid=true],input:not([type=hidden]),select,textarea');field?.focus({preventScroll:true});});
 }
 function closeDialog(){if(busy)return;dialog.close();body.replaceChildren();opener?.focus({preventScroll:true});}
 close.addEventListener('click',closeDialog);dialog.addEventListener('cancel',event=>{event.preventDefault();closeDialog();});
 dialog.addEventListener('click',event=>{if(event.target.closest('[data-record-close]'))closeDialog();});
 document.addEventListener('click',async event=>{
  const local=event.target.closest('[data-record-template]');
  if(local){event.preventDefault();opener=local;const source=document.getElementById(local.dataset.recordTemplate)?.querySelector('form');if(source)mount(source,local.dataset.recordTitle||'Profilni tahrirlash',source.action||location.href);return;}
  const link=event.target.closest('a[href]');if(!link||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||link.target==='_blank'||link.closest('.app-rail'))return;
  const url=new URL(link.href,location.href);if(url.origin!==location.origin||(!link.hasAttribute('data-form-modal')&&!formRoute(url)))return;
  event.preventDefault();opener=link;link.setAttribute('aria-busy','true');
  try{const response=await fetch(url,{credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}});if(!response.ok)throw Error();const doc=new DOMParser().parseFromString(await response.text(),'text/html'),form=primary(doc);if(!form)throw Error();mount(form,link.dataset.recordTitle||doc.querySelector('#content h1')?.textContent||link.textContent.trim(),response.url);}catch{location.assign(url.href);}finally{link.removeAttribute('aria-busy');}
 });
 dialog.addEventListener('submit',async event=>{
  const form=event.target.closest('form[data-record-active]');if(!form)return;event.preventDefault();if(busy)return;
  if(!form.reportValidity())return;busy=true;close.disabled=true;form.setAttribute('aria-busy','true');const data=new FormData(form);if(event.submitter?.name)data.append(event.submitter.name,event.submitter.value);
  const buttons=[...form.querySelectorAll('button[type=submit],button:not([type])')];buttons.forEach(button=>button.disabled=true);
  try{
   const response=await fetch(form.action,{method:'POST',body:data,credentials:'same-origin',headers:{'X-Requested-With':'XMLHttpRequest'}});
   if(!response.ok)throw Error(response.status===403?'Bu amal uchun ruxsat yo‘q yoki sessiya tugagan. Sahifani yangilang.':'Saqlash yakunlanmadi. Qayta urinib ko‘ring.');
   const doc=new DOMParser().parseFromString(await response.text(),'text/html'),next=primary(doc);
   if(!response.redirected&&next){mount(next,title.textContent,form.action);if(!errors(next))message('Ma’lumotlarni tekshirib, qayta saqlang.');}
   else{
    try{const messages=JSON.parse(doc.querySelector('#app-messages')?.textContent||'[]');sessionStorage.setItem(notices,JSON.stringify(messages));}catch{}
    location.assign(response.url);
   }
  }catch(error){message(error.message||'Aloqa uzildi. Kiritilgan qiymatlar oynada qoladi, qayta urinishingiz mumkin.');}
  finally{busy=false;close.disabled=false;form.removeAttribute('aria-busy');buttons.forEach(button=>button.disabled=false);}
 });
 // Inline editors become sheets, with normal forms available when JavaScript is absent.
 document.querySelectorAll('#content form[data-modal-source]').forEach(form=>{
  if(form.closest('[data-record-template-source]')||formRoute(new URL(location.href))||form.hasAttribute('data-confirm'))return;
  const box=form.closest('.panel,.preferences');if(!box)return;
  const label=box.querySelector('h2,summary')?.textContent.trim()||'Ma’lumotlarni tahrirlash';
  const button=document.createElement('button');button.type='button';button.className='button primary record-open-action';button.textContent=label;button.addEventListener('click',()=>{opener=button;mount(form,label,form.action||location.href);});if(box.matches('details.preferences')){box.before(button);box.hidden=true;}else form.before(button);form.hidden=true;if(errors(form))button.click();
 });
 const profile=document.querySelector('#profile-form form');if(profile&&errors(profile))document.querySelector('[data-record-template=profile-form]')?.click();
 try{const stored=sessionStorage.getItem(notices);if(stored){sessionStorage.removeItem(notices);JSON.parse(stored).forEach(detail=>document.dispatchEvent(new CustomEvent('ssb:toast',{detail})));}}catch{}
 // Changing a new task's project refreshes only its dependent choices, preserving other input.
 document.addEventListener('change',async event=>{
  const project=event.target;if(project.name!=='project'||project.disabled||!project.closest('form[data-modal-source]'))return;
  const form=project.form;if(!form.querySelector('[name=parent]'))return;
  projectRequests.get(form)?.abort();const controller=new AbortController();projectRequests.set(form,controller);
  const fields=['parent','milestone','depends_on'].map(name=>form.querySelector(`select[name=${name}]`)).filter(Boolean);fields.forEach(field=>field.disabled=true);
  try{const url=new URL(form.action||location.href);url.searchParams.set('project',project.value);const response=await fetch(url,{credentials:'same-origin',signal:controller.signal});if(!response.ok)throw Error();const doc=new DOMParser().parseFromString(await response.text(),'text/html'),source=primary(doc);if(!source)throw Error();if(projectRequests.get(form)!==controller)return;form.querySelectorAll('[data-people-picker]').forEach(picker=>{const next=source.querySelector(`[data-people-picker="${picker.dataset.peoplePicker}"]`);if(!next)return;const chosen=new Set([...picker.querySelectorAll('input:checked')].map(input=>input.value));const fresh=next.cloneNode(true);fresh.querySelectorAll('input[type=radio],input[type=checkbox]').forEach(input=>{input.checked=chosen.has(input.value);});picker.replaceWith(fresh);});document.dispatchEvent(new CustomEvent('ssb:formready',{detail:{root:form}}));fields.forEach(field=>{const next=source.querySelector(`[name=${field.name}]`);if(next){const value=field.value;field.replaceChildren(...[...next.options].map(option=>option.cloneNode(true)));if([...field.options].some(option=>option.value===value))field.value=value;}});}catch(error){if(error.name==='AbortError')return;document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text:'Loyiha maydonlarini yuklab bo‘lmadi. Sahifani yangilang.',level:'error'}}));}finally{if(projectRequests.get(form)===controller){fields.forEach(field=>field.disabled=false);projectRequests.delete(form);}}
 });
})();
