(()=>{'use strict';
 const ready=new WeakSet();
 const MAX_MB=8,TYPES=['image/jpeg','image/png','image/webp'];
 const toast=(text,level)=>document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text,level}}));

 /* ---------- Yozish formasi (sahifada ham, modal oynada ham ishlaydi) */
 function enhance(form){
  if(ready.has(form)||form.hidden)return;ready.add(form);
  // Klonlangan formadagi eski hisoblagichlar/oldindan ko'rishlarni tozalash
  form.querySelectorAll('.announcement-count').forEach(n=>n.remove());
  [['title',160],['body',null]].forEach(([name,max])=>{
   const input=form.elements[name],field=input?.closest('.field');if(!input||!field)return;
   const count=document.createElement('small');count.className='announcement-count';count.setAttribute('aria-live','polite');field.append(count);
   const update=()=>{const n=input.value.length;count.textContent=max?`${n} / ${max}`:`${n} belgi`;};
   input.addEventListener('input',update);update();
  });

  const input=form.querySelector('[data-ann-input]'),list=form.querySelector('[data-ann-previews]'),drop=form.querySelector('[data-ann-drop]');
  if(input&&list){
   let files=[];const urls=new Map();
   const sync=()=>{
    try{const dt=new DataTransfer();files.forEach(f=>dt.items.add(f));input.files=dt.files;}catch{}
    urls.forEach((url,file)=>{if(!files.includes(file)){URL.revokeObjectURL(url);urls.delete(file);}});
    list.replaceChildren(...files.map((file,i)=>{
     if(!urls.has(file))urls.set(file,URL.createObjectURL(file));
     const li=document.createElement('li');li.className='ann-preview';
     const img=document.createElement('img');img.src=urls.get(file);img.alt='';
     const rm=document.createElement('button');rm.type='button';rm.className='ann-preview-remove';rm.setAttribute('aria-label',`${file.name} rasmini olib tashlash`);rm.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="m7 7 10 10M17 7 7 17"/></svg>';
     rm.addEventListener('click',()=>{files.splice(i,1);sync();});
     const n=document.createElement('span');n.className='ann-preview-n';n.textContent=i+1;
     li.append(img,n,rm);return li;
    }));
    list.dataset.count=files.length;
    drop.querySelector('strong').textContent=files.length?`${files.length} ta rasm tanlandi · yana qo‘shish`:'Rasm qo‘shish';
   };
   const add=incoming=>{
    let skipped=0;
    [...incoming].forEach(f=>{
     if(!TYPES.includes(f.type)||f.size>MAX_MB*1024*1024){skipped++;return;}
     if(!files.some(x=>x.name===f.name&&x.size===f.size&&x.lastModified===f.lastModified))files.push(f);
    });
    if(skipped)toast(`${skipped} ta fayl qo‘shilmadi: faqat JPG, PNG yoki WebP, har biri ${MAX_MB} MB gacha.`,'error');
    sync();
   };
   input.addEventListener('change',()=>{const picked=[...input.files];add(picked);});
   ['dragenter','dragover'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.add('is-over');}));
   ['dragleave','drop'].forEach(t=>drop.addEventListener(t,e=>{e.preventDefault();drop.classList.remove('is-over');}));
   drop.addEventListener('drop',e=>{if(e.dataTransfer?.files?.length)add(e.dataTransfer.files);});
   sync();
  }

  const label=form.elements['link_label'],url=form.elements['link_url'],preview=form.querySelector('[data-ann-link-preview]');
  if(label&&url&&preview){
   const text=preview.querySelector('[data-ann-link-text]');
   const update=()=>{const has=url.value.trim()||label.value.trim();preview.hidden=!has;text.textContent=label.value.trim()||'Havolani ochish';};
   label.addEventListener('input',update);url.addEventListener('input',update);update();
  }
 }
 const scan=root=>root.querySelectorAll('form[data-announcement-form]').forEach(enhance);
 document.addEventListener('ssb:formready',e=>scan(e.detail?.root||document));
 // forms.js asl formani modalga ko'chirib yashiradi; ko'rinib qolgan formalarni (JS'siz holat) keyin yoqamiz.
 document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>scan(document),0));

 /* ---------- Rasmni kattalashtirib ko'rish */
 const viewer=document.querySelector('[data-ann-viewer]');
 if(viewer&&viewer.showModal){
  const full=viewer.querySelector('[data-ann-full]'),count=viewer.querySelector('[data-ann-count]');
  let set=[],index=0;
  const show=i=>{index=(i+set.length)%set.length;full.src=set[index];count.textContent=set.length>1?`${index+1} / ${set.length}`:'';viewer.classList.toggle('is-single',set.length<2);};
  document.addEventListener('click',e=>{
   const photo=e.target.closest('[data-ann-photo]');if(!photo)return;
   const gallery=photo.closest('[data-ann-gallery]');
   set=[...gallery.querySelectorAll('[data-ann-photo]')].map(b=>b.dataset.src);
   show(set.indexOf(photo.dataset.src));viewer.showModal();
  });
  viewer.querySelector('[data-ann-close]').addEventListener('click',()=>viewer.close());
  viewer.querySelector('[data-ann-prev]').addEventListener('click',()=>show(index-1));
  viewer.querySelector('[data-ann-next]').addEventListener('click',()=>show(index+1));
  viewer.addEventListener('click',e=>{if(e.target===viewer)viewer.close();});
  viewer.addEventListener('keydown',e=>{if(e.key==='ArrowLeft')show(index-1);if(e.key==='ArrowRight')show(index+1);});
  viewer.addEventListener('close',()=>{full.removeAttribute('src');});
 }
})();
