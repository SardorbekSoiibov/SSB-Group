(()=>{'use strict';
 // Place pickers: a place belongs to one person, and the summary always says what will be saved.
 const form=document.querySelector('#rate-form');if(!form)return;
 const rows=[...form.querySelectorAll('.rate-row')],summary=form.querySelector('#rate-summary');
 const select=row=>row.querySelector('select'),name=row=>row.querySelector('.rate-person strong').textContent;
 function refresh(){
  const chosen=rows.filter(row=>select(row).value).sort((a,b)=>select(a).value-select(b).value);
  rows.forEach(row=>row.classList.toggle('is-first',select(row).value==='1'));
  const first=chosen.find(row=>select(row).value==='1');
  summary.textContent=!chosen.length?'Hali o‘rin tanlanmagan':first?`1-o‘rin: ${name(first)} · jami ${chosen.length} ta o‘rin`:`1-o‘rin hali tanlanmagan · ${chosen.length} ta o‘rin`;
 }
 rows.forEach(row=>select(row).addEventListener('change',()=>{const value=select(row).value;if(value)rows.forEach(other=>{if(other!==row&&select(other).value===value)select(other).value='';});refresh();}));
 form.querySelector('#rate-suggest').addEventListener('click',()=>{rows.forEach(row=>{select(row).value=row.dataset.suggested==='0'?'':row.dataset.suggested;});refresh();if(!rows.some(row=>select(row).value))document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text:'Bu hafta qabul qilingan ish yo‘q. O‘rinlarni o‘zingiz tanlang.',level:'error'}}));});
 form.addEventListener('submit',event=>{const numbers=rows.map(row=>Number(select(row).value)).filter(Boolean).sort((a,b)=>a-b);if(numbers.some((value,index)=>value!==index+1)){event.preventDefault();event.stopImmediatePropagation();document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text:'O‘rinlar 1 dan boshlab ketma-ket bo‘lsin.',level:'error'}}));}},true);
 refresh();
})();
