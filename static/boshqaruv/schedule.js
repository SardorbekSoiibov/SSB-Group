(()=>{'use strict';
 // Fills the chosen day into the shared record dialog and adds one-tap work places.
 const places=['Ofis','Masofaviy','Navbatchilik'];let day=null;
 document.addEventListener('click',event=>{const button=event.target.closest('[data-shift-day]');if(button)day=button.dataset.shiftDay;},true);
 document.addEventListener('ssb:formready',event=>{
  const form=event.detail.root.querySelector('form.shift-form');if(!form)return;
  if(day){form.querySelector('[name=starts_at]').value=day+'T09:00';form.querySelector('[name=ends_at]').value=day+'T18:00';day=null;}
  const location=form.querySelector('[name=location]'),chips=document.createElement('div');chips.className='shift-chips';
  const refresh=()=>chips.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.textContent===location.value)));
  places.forEach(place=>{const button=document.createElement('button');button.type='button';button.textContent=place;button.addEventListener('click',()=>{location.value=place;refresh();});chips.append(button);});
  location.after(chips);location.addEventListener('input',refresh);refresh();
 });
 // Opening an edit link directly, or in a new tab, still lands in the dialog.
 const add=document.querySelector('[data-shift-add]');
 if(add&&document.querySelector('#shift-form form[data-editing]')){add.dataset.recordTitle='Smenani tahrirlash';delete add.dataset.shiftDay;add.click();add.dataset.recordTitle='Yangi smena';}
})();
