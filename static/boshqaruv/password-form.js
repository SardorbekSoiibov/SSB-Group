(()=>{'use strict';
 // Show/hide buttons and live hints for password forms. The server stays the final judge of every rule.
 const eye='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
 const eyeOff='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4l16 16M10 5.2A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3 3.8M6.5 7A16 16 0 0 0 2 12s3.6 7 10 7a10 10 0 0 0 4.5-1"/></svg>';
 const labels=['','Kuchsiz','O‘rtacha','Yaxshi','Kuchli'];
 const make=(tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;if(text)node.textContent=text;return node;};
 function score(value){
  if(!value)return 0;if(value.length<10||/^[0-9]+$/.test(value))return 1;
  return 2+(value.length>=14?1:0)+(/[a-zA-Z]/.test(value)&&/[0-9]/.test(value)&&/[^a-zA-Z0-9]/.test(value)?1:0);
 }
 function toggle(input){
  const box=make('span','password-box'),button=make('button','password-eye');input.replaceWith(box);box.append(input,button);
  button.type='button';button.innerHTML=eye;button.setAttribute('aria-label','Parolni ko‘rsatish');button.setAttribute('aria-pressed','false');
  button.addEventListener('click',()=>{const show=input.type==='password';input.type=show?'text':'password';button.innerHTML=show?eyeOff:eye;button.setAttribute('aria-pressed',String(show));button.setAttribute('aria-label',show?'Parolni yashirish':'Parolni ko‘rsatish');});
 }
 function rule(text){const item=make('li','',text);return item;}
 function enhance(root){
  root.querySelectorAll('form.password-form').forEach(form=>{
   if(form.dataset.passwordReady)return;form.dataset.passwordReady='true';
   form.querySelectorAll('input[type=password]').forEach(toggle);
   const first=form.querySelector('[name=new_password1]'),second=form.querySelector('[name=new_password2]');if(!first||!second)return;
   const meter=make('div','password-meter'),word=make('small','password-word'),rules=make('ul','password-rules');
   meter.setAttribute('aria-hidden','true');for(let i=0;i<4;i++)meter.append(make('i'));
   const length=rule('Kamida 10 ta belgi'),letters=rule('Faqat raqamlardan iborat emas'),match=rule('Ikkala yangi parol bir xil');
   rules.append(length,letters,match);first.closest('.field').append(meter,word);second.closest('.field').append(rules);
   const refresh=()=>{
    const value=first.value,level=score(value);meter.dataset.level=level;word.textContent=labels[level];
    length.classList.toggle('is-met',value.length>=10);letters.classList.toggle('is-met',!!value&&!/^[0-9]+$/.test(value));match.classList.toggle('is-met',!!value&&value===second.value);
   };
   first.addEventListener('input',refresh);second.addEventListener('input',refresh);refresh();
  });
 }
 enhance(document);document.addEventListener('ssb:formready',event=>enhance(event.detail.root));
})();
