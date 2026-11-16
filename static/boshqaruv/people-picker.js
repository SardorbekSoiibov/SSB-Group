// Assignment picker: search, position filter, responsibility inputs and the assignee/co-worker rule.
(()=>{'use strict';
 const fold=text=>(text||'').toLocaleLowerCase('uz').replace(/[‘’ʻʼ`]/g,"'");
 function refresh(picker){
  const query=fold(picker.querySelector('[data-people-search]')?.value),position=picker.querySelector('[data-people-position]')?.value||'';
  let shown=0;
  picker.querySelectorAll('[data-people-row]').forEach(row=>{
   const input=row.querySelector('input[type=radio],input[type=checkbox]'),match=fold(row.dataset.name).includes(query)&&(!position||row.dataset.position===position);
   row.hidden=!match&&!input.checked;if(!row.hidden)shown++;
   row.classList.toggle('is-chosen',input.checked);
   const text=row.querySelector('[data-people-responsibility]');if(text)text.hidden=!input.checked;
  });
  const count=picker.querySelector('[data-people-count]');if(count){const chosen=[...picker.querySelectorAll('[data-people-row] input:checked')].filter(input=>input.value).length;count.textContent=chosen?`${chosen} nafar tanlandi`:'';}
  const empty=picker.querySelector('[data-people-empty]');if(empty)empty.hidden=shown>0;
 }
 // The responsible person cannot also be their own co-worker.
 function linkAssignee(form){
  const assignee=form?.querySelector('[data-people-picker=assignee] input:checked')?.value,others=form?.querySelector('[data-people-picker=collaborators]');if(!others)return;
  others.querySelectorAll('[data-people-row]').forEach(row=>{const box=row.querySelector('input[type=checkbox]'),same=box.value===assignee;if(same)box.checked=false;box.disabled=same;row.classList.toggle('is-locked',same);});
  refresh(others);
 }
 function start(root=document){root.querySelectorAll('[data-people-picker]').forEach(refresh);root.querySelectorAll('form').forEach(linkAssignee);if(root.matches?.('form'))linkAssignee(root);}
 document.addEventListener('input',event=>{const picker=event.target.closest('[data-people-picker]');if(picker&&event.target.matches('[data-people-search]'))refresh(picker);});
 document.addEventListener('change',event=>{const picker=event.target.closest('[data-people-picker]');if(!picker)return;refresh(picker);linkAssignee(event.target.form);});
 document.addEventListener('keydown',event=>{if(event.key==='Enter'&&event.target.matches?.('[data-people-search]'))event.preventDefault();});
 document.addEventListener('ssb:formready',event=>start(event.detail.root));
 start();
})();
