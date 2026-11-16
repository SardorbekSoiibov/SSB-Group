(()=>{'use strict';
 document.querySelectorAll('.connections-layout form[method=post]').forEach(form=>{
  form.addEventListener('submit',event=>{
   if(form.dataset.submitting){event.preventDefault();return;}
   form.dataset.submitting='true';
   const clicked=event.submitter;
   if(clicked?.name){const hidden=document.createElement('input');hidden.type='hidden';hidden.name=clicked.name;hidden.value=clicked.value;hidden.dataset.submitAction='true';form.append(hidden);}
   form.querySelectorAll('button[type=submit],button:not([type])').forEach(button=>{
    button.dataset.originalText=button.textContent;button.disabled=true;
    if(button===clicked)button.textContent=button.value==='save_telegram'?'Token tekshirilmoqda…':'Bajarilmoqda…';
   });
  });
 });
 window.addEventListener('pageshow',()=>{
  document.querySelectorAll('form[data-submitting]').forEach(form=>{
   delete form.dataset.submitting;form.querySelectorAll('[data-submit-action]').forEach(node=>node.remove());
   form.querySelectorAll('button[data-original-text]').forEach(button=>{button.textContent=button.dataset.originalText;delete button.dataset.originalText;button.disabled=false;});
  });
 });
})();
