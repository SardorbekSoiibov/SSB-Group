(() => {
  const normalize = value => value.replace(/[‘’ʻʼ`]/g,"'").replace(/\s+/g,' ').trim();
  const entries = new Map(), states = new WeakMap(), attributes = new WeakMap();
  const supported = ['uz','ru','en'];
  let language = 'uz', scheduled = false, ready = false;
  try { const stored = localStorage.getItem('ssb-language'); if (supported.includes(stored)) language = stored; } catch {}
  const picker = document.querySelector('.language-picker');
  const trigger = picker.querySelector('.language-trigger');
  const panel = picker.querySelector('.language-options');
  const current = picker.querySelector('.language-current');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function translate(source) {
    if (language === 'uz') return source;
    const row = entries.get(normalize(source));
    if (row) return row[language];
    let match = normalize(source).match(/^(\d+) \/ 8 ta kubik yig'ildi\. Qolgan bo'laklarni bosing\.$/);
    if (match) return language === 'ru' ? `${match[1]} / 8 деталей собрано. Нажмите на оставшиеся.` : `${match[1]} / 8 pieces assembled. Click the remaining pieces.`;
    match = normalize(source).match(/^yana (\d+) belgi$/);
    if (match) return language === 'ru' ? `ещё ${match[1]} симв.` : `${match[1]} more characters`;
    match = normalize(source).match(/^(.+) uchun$/);
    if (match && source.length < 80 && !entries.has(normalize(source))) return language === 'ru' ? `Для: ${match[1]}` : `For ${match[1]}`;
    match = normalize(source).match(/^8 \/ 8 — (\d+) soniyada uddaladingiz!$/);
    if (match) return language === 'ru' ? `8 / 8 — вы справились за ${match[1]} сек.!` : `8 / 8 — completed in ${match[1]} seconds!`;
    // Page titles share the same translated labels as their navigation links.
    if (source.endsWith(' — SSB Group')) return translate(source.slice(0,-12)) + ' — SSB Group';
    return source;
  }
  function updateText(node) {
    let state = states.get(node);
    if (!state || node.nodeValue !== state.output) state = {source:node.nodeValue, output:node.nodeValue};
    const source = state.source, leading = source.match(/^\s*/)[0], trailing = source.match(/\s*$/)[0];
    const output = leading + translate(source.trim()) + trailing;
    if (output !== node.nodeValue) node.nodeValue = output;
    state.output = output; states.set(node,state);
  }
  function apply() {
    observer.disconnect();
    const walker = document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode:node => node.nodeValue.trim() && !node.parentElement.closest('script,style,textarea,[data-no-translate],[contenteditable="true"]') ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT});
    let node;while ((node=walker.nextNode())) updateText(node);
    document.querySelectorAll('[placeholder],[aria-label],[title],meta[name="description"],meta[property="og:description"]').forEach(element => {
      if (element.closest('[data-no-translate]')) return;
      let saved = attributes.get(element);if (!saved) saved = {};
      for (const name of ['placeholder','aria-label','title','content']) {
        if (!element.hasAttribute(name) || (name==='content' && element.tagName!=='META')) continue;
        const value=element.getAttribute(name);
        let state=saved[name];if (!state || value!==state.output) state={source:value};
        const output=translate(state.source);if (value!==output) element.setAttribute(name,output);
        state.output=output;saved[name]=state;
      }
      attributes.set(element,saved);
    });
    const title=document.querySelector('title');if(title.firstChild)updateText(title.firstChild);
    document.documentElement.lang=language;
    current.textContent=language.toUpperCase();
    picker.querySelectorAll('[data-language]').forEach(button => {const active=button.dataset.language===language;button.setAttribute('aria-checked',String(active));button.classList.toggle('is-selected',active);});
    trigger.setAttribute('aria-label',{uz:'Tilni tanlash',ru:'Выбрать язык',en:'Choose language'}[language]);
    observer.observe(document.body,{subtree:true,childList:true,characterData:true});
  }
  const observer = new MutationObserver(() => {
    if (!ready || scheduled) return;
    scheduled=true;requestAnimationFrame(()=>{scheduled=false;apply();});
  });
  function close(){panel.hidden=true;trigger.setAttribute('aria-expanded','false');}
  trigger.addEventListener('click',()=>{const opening=panel.hidden;panel.hidden=!opening;trigger.setAttribute('aria-expanded',String(opening));if(opening)panel.querySelector(`[data-language="${language}"]`).focus();});
  picker.querySelectorAll('[data-language]').forEach(button=>button.addEventListener('click',()=>{
    language=button.dataset.language;try{localStorage.setItem('ssb-language',language);}catch{}
    close();trigger.focus();apply();dispatchEvent(new Event('resize'));
    if(!reduced)document.querySelectorAll('main,body>footer').forEach(element=>element.animate([{opacity:.3,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:360,easing:'cubic-bezier(.2,.7,.2,1)'}));
  }));
  document.addEventListener('click',event=>{if(!picker.contains(event.target))close();});
  picker.addEventListener('keydown',event=>{
    if(event.key==='Escape'){close();trigger.focus();}
    if(['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();panel.hidden=false;trigger.setAttribute('aria-expanded','true');
      const options=[...panel.querySelectorAll('button')];let index=options.indexOf(document.activeElement);index=(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length;options[index].focus();
    }
  });
  const dictionary = fetch('/static/js/languages.tsv').then(response=>{if(!response.ok)throw Error('Translation file unavailable');return response.text();}).then(text=>{
    text.split(/\r?\n/).filter(Boolean).forEach(line=>{const [uz,ru,en]=line.split('|');if(uz&&ru&&en)entries.set(normalize(uz),{uz,ru,en});});ready=true;apply();dispatchEvent(new Event('resize'));
  }).catch(()=>{ready=true;language='uz';apply();});
  const brandReveal = new Promise(resolve=>{
    const logo=document.querySelector('.loader-logo');
    if(!logo){resolve();return;}
    logo.setAttribute('aria-label','SSB Group');
    const words=[logo.querySelector('b'),logo.querySelector(':scope > span')].filter(Boolean);
    let count=0;
    words.forEach(word=>{
      const text=word.textContent;word.textContent='';
      [...text].forEach(character=>{
        const letter=document.createElement('i');
        letter.className='loader-letter';letter.textContent=character;letter.setAttribute('aria-hidden','true');
        letter.style.setProperty('--i',count++);word.append(letter);
      });
    });
    logo.style.setProperty('--n',count);
    const step=95,lead=250;
    const start=()=>{
      logo.classList.add('is-typing');words.forEach(word=>{word.style.visibility='visible';});
      setTimeout(()=>{logo.classList.add('is-complete');setTimeout(resolve,750);},reduced?0:lead+count*step+350);
    };
    const fontsReady=document.fonts?.ready||Promise.resolve();
    Promise.race([fontsReady,new Promise(r=>setTimeout(r,700))]).then(()=>requestAnimationFrame(start));
  });
  const delay = new Promise(resolve=>setTimeout(resolve,850));
  const fontReady = document.fonts?.ready || Promise.resolve();
  Promise.race([Promise.allSettled([dictionary,fontReady,delay,brandReveal]),new Promise(resolve=>setTimeout(resolve,5200))]).then(()=>{
    const loader=document.querySelector('.brand-loader');
    let finished=false;
    const finish=()=>{
      if(finished)return;finished=true;loader?.remove();
      document.documentElement.classList.remove('ssb-loading');dispatchEvent(new Event('ssb:loaded'));
    };
    if(loader&&!reduced&&typeof loader.animate==='function'){
      const exit=loader.animate([
        {opacity:1,transform:'scale(1)'},
        {opacity:0,transform:'scale(1.03)'}
      ],{duration:600,easing:'cubic-bezier(.4,0,.2,1)',fill:'forwards'});
      exit.finished.then(finish,finish);setTimeout(finish,850);
    }else finish();
  });
})();
