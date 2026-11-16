(()=>{'use strict';
 // Choosing a photo opens a preview; nothing is uploaded until the person presses save.
 const input=document.querySelector('#photo-input'),dialog=document.querySelector('#photo-dialog');if(!input||!dialog?.showModal)return;
 const preview=dialog.querySelector('#photo-preview'),save=dialog.querySelector('#photo-save');
 const limit=8*1024*1024,types=['image/jpeg','image/png','image/webp'];let url=null;
 const toast=text=>document.dispatchEvent(new CustomEvent('ssb:toast',{detail:{text,level:'error'}}));
 const release=()=>{if(url)URL.revokeObjectURL(url);url=null;preview.removeAttribute('src');};
 const cancel=()=>{input.value='';release();if(dialog.open)dialog.close();};
 document.querySelectorAll('[data-photo-pick]').forEach(button=>button.addEventListener('click',()=>input.click()));
 dialog.querySelector('[data-photo-cancel]').addEventListener('click',cancel);
 dialog.addEventListener('cancel',event=>{event.preventDefault();cancel();});
 preview.addEventListener('error',()=>{if(!url)return;cancel();toast('Bu faylni rasm sifatida ochib bo‘lmadi.');});
 input.addEventListener('change',()=>{
  const file=input.files[0];if(!file)return;
  if(!types.includes(file.type)){cancel();toast('Faqat JPG, PNG yoki WEBP rasm tanlang.');return;}
  if(file.size>limit){cancel();toast('Rasm hajmi 8 MB dan oshmasligi kerak.');return;}
  release();url=URL.createObjectURL(file);preview.src=url;if(!dialog.open)dialog.showModal();
 });
 save.addEventListener('click',()=>{save.disabled=true;input.form.requestSubmit();});
})();
