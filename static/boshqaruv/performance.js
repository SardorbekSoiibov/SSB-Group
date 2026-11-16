(()=>{'use strict';
 // One-tap review periods and an end date that cannot fall before the start.
 const iso=day=>`${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;
 const monday=day=>{const copy=new Date(day);copy.setDate(copy.getDate()-(copy.getDay()+6)%7);return copy;};
 const plus=(day,count)=>{const copy=new Date(day);copy.setDate(copy.getDate()+count);return copy;};
 function periods(){
  const today=new Date(),week=monday(today);
  return [['Shu hafta',week,plus(week,6)],['O‘tgan hafta',plus(week,-7),plus(week,-1)],
   ['Shu oy',new Date(today.getFullYear(),today.getMonth(),1),new Date(today.getFullYear(),today.getMonth()+1,0)],
   ['O‘tgan oy',new Date(today.getFullYear(),today.getMonth()-1,1),new Date(today.getFullYear(),today.getMonth(),0)]];
 }
 document.addEventListener('ssb:formready',event=>{
  const form=event.detail.root.querySelector('form.review-form');if(!form)return;
  const start=form.querySelector('[name=period_start]'),end=form.querySelector('[name=period_end]'),row=document.createElement('div');row.className='review-presets';
  const clearError=()=>{const field=end.closest('.field');field.classList.remove('invalid');field.querySelectorAll('.field-error').forEach(node=>node.remove());};
  const refresh=()=>{end.min=start.value;row.querySelectorAll('button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.start===start.value&&button.dataset.end===end.value)));};
  periods().forEach(([label,from,to])=>{const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.start=iso(from);button.dataset.end=iso(to);button.addEventListener('click',()=>{start.value=button.dataset.start;end.value=button.dataset.end;clearError();refresh();});row.append(button);});
  start.closest('.field').before(row);
  start.addEventListener('change',()=>{if(end.value&&end.value<start.value)end.value=start.value;clearError();refresh();});end.addEventListener('change',()=>{clearError();refresh();});refresh();
 });
})();
