// QA only: drives every messenger control in headless Edge against a temporary local test server.
const fs=require('node:fs'),path=require('node:path'),{spawn,execFileSync}=require('node:child_process');
const input=JSON.parse(fs.readFileSync(0,'utf8'));let child,socket,next=0;const pending=new Map(),errors=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(ok,label){if(!ok)throw Error(label);}
async function until(fn,label){const end=Date.now()+20000;while(Date.now()<end){try{if(await fn())return;}catch{}await pause(100);}throw Error('Timeout: '+label);}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result?.value;}
async function shot(name){const result=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(input.root,name),Buffer.from(result.data,'base64'));}
const lastMine="[...document.querySelectorAll('.chat-message.mine')].pop()";
async function type(text){await evaluate(`(()=>{const i=document.querySelector('#chat-body');i.value=${JSON.stringify(text)};i.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#chat-form').requestSubmit();})()`);}
async function menu(row,label){
 await evaluate(`${row}.querySelector('.chat-more').click()`);
 await until(()=>evaluate("!document.querySelector('#chat-menu').hidden"),'menu open');
 await evaluate(`[...document.querySelectorAll('#chat-menu [data-action]')].find(b=>b.dataset.action===${JSON.stringify(label)}||b.dataset.emoji===${JSON.stringify(label)}).click()`);
}
async function run(){
 check(new URL(input.server).hostname==='127.0.0.1','Temporary local server only');
 child=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless','--disable-gpu','--no-first-run','--remote-debugging-port='+input.port,'--user-data-dir='+path.join(input.root,'profile'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 let target;await until(async()=>{target=(await(await fetch(`http://127.0.0.1:${input.port}/json/list`)).json()).find(t=>t.type==='page');return target;},'browser');
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.onopen=resolve);
 socket.onmessage=event=>{const data=JSON.parse(event.data),call=pending.get(data.id);if(call){pending.delete(data.id);clearTimeout(call.timer);data.error?call.reject(Error(data.error.message)):call.resolve(data.result);}
  if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails?.exception?.description||data.params.exceptionDetails?.text);};
 await command('Runtime.enable');
 await command('Emulation.setTimezoneOverride',{timezoneId:'America/New_York'});
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await command('Page.navigate',{url:input.server+'/management/hisob/kirish/'});
 await until(()=>evaluate("!!document.querySelector('[name=username]')"),'login');
 await evaluate(`(()=>{document.querySelector('[name=username]').value=${JSON.stringify(input.username)};document.querySelector('[name=password]').value=${JSON.stringify(input.password)};document.querySelector('[name=username]').closest('form').requestSubmit();})()`);
 await until(()=>evaluate("location.pathname==='/management/enterprise/'"),'signed in');
 await command('Page.navigate',{url:input.server+'/management/chat/'+input.peer+'/'});
 await until(()=>evaluate("document.querySelectorAll('.chat-message').length>=2"),'history painted');
 // Seeded history: separators, unread divider, online status.
 // This browser is set to New York on purpose: the chat must still show company time.
 check(await evaluate(`new Date().getTimezoneOffset()>=240`),'browser zone override active');
 check(await evaluate(`document.querySelector('[data-message="${input.expectedId}"] .chat-meta').textContent.startsWith(${JSON.stringify(input.expectedTime)})`),'message time is company time');
 await until(()=>evaluate(`document.querySelector('.chat-contact time')?.textContent===${JSON.stringify(input.expectedTime)}`),'contact time is company time');
 check(await evaluate("getComputedStyle(document.querySelector('.chat-meta')).fontVariantNumeric==='normal'"),'time digits are not spaced apart');
 check(await evaluate("[...document.querySelectorAll('.chat-day span')].some(n=>/^[0-9]+-/.test(n.textContent))&&[...document.querySelectorAll('.chat-day span')].pop().textContent==='Bugun'"),'date labels');
 check(await evaluate("!!document.querySelector('.chat-day')"),'date separator');
 check(await evaluate("!!document.querySelector('#peer-name .chat-verified')&&!!document.querySelector('.chat-contact .chat-verified')"),'verified badge in header and list');
 check(await evaluate("[...document.querySelectorAll('#peer-name,.chat-contact strong')].filter(n=>n.querySelector('.chat-verified')).every(n=>n.lastElementChild.matches('.chat-verified')&&n.firstElementChild.matches('.chat-name-text')&&n.firstElementChild.getBoundingClientRect().right<=n.lastElementChild.getBoundingClientRect().left)"),'verified badge sits after the name');
 await evaluate("(()=>{const i=document.querySelector('#chat-search');i.value='jasur tursunov';i.dispatchEvent(new Event('input',{bubbles:true}));})()");
 await until(()=>evaluate("document.querySelectorAll('.chat-contact').length===1&&document.querySelector('.chat-contact').textContent.includes('Bosh muhandis')"),'full name search shows the job title');
 await evaluate("(()=>{const i=document.querySelector('#chat-search');i.value='';i.dispatchEvent(new Event('input',{bubbles:true}));})()");
 await until(()=>evaluate("document.querySelectorAll('.chat-contact').length>=2"),'list restored');
 check(await evaluate("!!document.querySelector('.chat-unread-divider')"),'unread divider');
 await until(()=>evaluate("document.querySelector('#peer-status').textContent==='onlayn'"),'peer online');
 check(await evaluate("!!document.querySelector('#peer-initials .chat-online')"),'online dot');
 // Send, link is safe and clickable, ticks.
 await type('Salom https://example.com/doc');
 await until(()=>evaluate(`${lastMine}?.textContent.includes('example.com')`),'sent');
 check(await evaluate(`${lastMine}.querySelector('.chat-text a').rel.includes('noopener')`),'link');
 check(await evaluate(`${lastMine}.querySelector('.chat-ticks').textContent==='✓'`),'single tick');
 // Reply through the menu.
 await menu(lastMine,'reply');
 await until(()=>evaluate("!document.querySelector('#chat-context').hidden"),'reply bar');
 await type('Bu javob');
 await until(()=>evaluate(`${lastMine}?.querySelector('.chat-quote')?.textContent.includes('Salom')`),'reply quote');
 check(await evaluate("document.querySelector('#chat-context').hidden"),'reply bar cleared');
 // Edit with the Up arrow shortcut.
 await evaluate("document.querySelector('#chat-body').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}))");
 await until(()=>evaluate("document.querySelector('#chat-body').value==='Bu javob'"),'edit loaded');
 await type('Bu tahrirlangan javob');
 await until(()=>evaluate(`${lastMine}?.textContent.includes('tahrirlangan')&&!!${lastMine}.querySelector('.chat-edited')`),'edited');
 // Reaction, pin.
 await menu(lastMine,'🔥');
 await until(()=>evaluate(`!!${lastMine}.querySelector('.chat-reaction.mine')`),'reaction');
 await menu(lastMine,'pin');
 await until(()=>evaluate("!document.querySelector('#chat-pinned').hidden&&document.querySelector('#chat-pinned-text').textContent.includes('tahrirlangan')"),'pinned bar');
 // Image upload with preview; the viewer opens and the picture really loads.
 const doc=await command('DOM.getDocument',{depth:-1});
 const node=await command('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#chat-file'});
 await command('DOM.setFileInputFiles',{nodeId:node.nodeId,files:[input.image]});
 await until(()=>evaluate("!document.querySelector('#chat-attachment').hidden&&!!document.querySelector('#chat-attachment-thumb img')"),'attachment preview');
 await type('');
 await until(()=>evaluate(`${lastMine}?.querySelector('.chat-media img')?.naturalWidth>0`),'image rendered');
 await evaluate(`${lastMine}.querySelector('.chat-media').click()`);
 await until(()=>evaluate("document.querySelector('#chat-viewer').open&&document.querySelector('#chat-viewer-image').naturalWidth>0"),'viewer');
 await evaluate("document.querySelector('#chat-viewer').close()");
 // Emoji picker inserts at the cursor.
 await evaluate("document.querySelector('#chat-emoji').click()");
 await until(()=>evaluate("!document.querySelector('#chat-emoji-panel').hidden"),'emoji panel');
 await evaluate("document.querySelector('#chat-emoji-panel [data-emoji]').click()");
 check((await evaluate("document.querySelector('#chat-body').value")).length>0,'emoji inserted');
 await shot('messenger-dark-emoji.png');
 await evaluate("(()=>{const i=document.querySelector('#chat-body');i.value='';i.dispatchEvent(new Event('input',{bubbles:true}));document.body.click();})()");
 // Search and jump to an old message outside the loaded window.
 await evaluate("document.querySelector('#chat-find-toggle').click()");
 await evaluate("(()=>{const i=document.querySelector('#chat-find');i.value='Qadimgi';i.dispatchEvent(new Event('input',{bubbles:true}));})()");
 await until(()=>evaluate("document.querySelectorAll('.chat-find-result').length===1"),'search result');
 await evaluate("document.querySelector('.chat-find-result').click()");
 await until(()=>evaluate("!!document.querySelector('.chat-message.flash')"),'jump to message');
 await evaluate("document.querySelector('#chat-find-toggle').click()");
 // Delete for both.
 await until(()=>evaluate(`!!${lastMine}?.querySelector('.chat-media')`),'latest messages reloaded after jump');
 await menu(lastMine,'delete');
 await until(()=>evaluate("document.querySelector('#confirm-dialog').matches(':modal')&&document.querySelector('#confirm-dialog').classList.contains('is-danger')"),'styled delete confirmation');
 await pause(250);await shot('messenger-delete-confirm.png');
 await evaluate("document.querySelector('#confirm-dialog [data-close-dialog]').click()");await pause(250);
 check(await evaluate(`!${lastMine}.classList.contains('deleted')`),'cancel keeps the message');
 await menu(lastMine,'delete');
 await until(()=>evaluate("document.querySelector('#confirm-dialog').open"),'confirmation reopens');
 await evaluate("document.querySelector('#confirm-accept').click()");
 await until(()=>evaluate(`${lastMine}.classList.contains('deleted')`),'deleted');
 // Light theme and mobile.
 await evaluate("document.querySelector('#chat-timeline').scrollTop=1e9");
 await evaluate("document.documentElement.dataset.theme='light'");await pause(250);await shot('messenger-light.png');
 await evaluate("document.documentElement.dataset.theme='dark'");await pause(250);await shot('messenger-dark.png');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(400);
 check(await evaluate("document.documentElement.scrollWidth<=innerWidth+1"),'mobile no overflow');
 await shot('messenger-mobile.png');
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await pause(200);
 await command('Emulation.setTimezoneOverride',{timezoneId:'Asia/Tashkent'});
 // Forward last: it navigates to the target conversation.
 await evaluate("[...document.querySelectorAll('.chat-message:not(.deleted)')].pop().querySelector('.chat-more').click()");
 await until(()=>evaluate("!document.querySelector('#chat-menu').hidden"),'menu for forward');
 await evaluate("document.querySelector('#chat-menu [data-action=forward]').click()");
 await until(()=>evaluate("document.querySelector('#chat-forward').open&&!!document.querySelector('[data-forward]')"),'forward dialog');
 await evaluate(`document.querySelector('[data-forward="${input.other}"]').click()`);
 await until(()=>evaluate(`location.pathname==='/management/chat/${input.other}/'&&!!document.querySelector('.chat-forwarded')`),'forwarded');
 await until(()=>evaluate("/^oxirgi marta bugun [0-9][0-9]:[0-9][0-9]$/.test(document.querySelector('#peer-status').textContent)"),'last seen shown');
 await pause(250);await shot('messenger-final.png');
 check(errors.length===0,'JS exceptions: '+errors.join(' | '));
 console.log(JSON.stringify({ok:true,separators:true,presence:true,send:true,reply:true,edit:true,reaction:true,pin:true,image:true,viewer:true,emoji:true,search:true,deleted:true,mobile:true,forward:true,jsErrors:0,screenshots:input.root}));
}
async function closeBrowser(){try{const {webSocketDebuggerUrl}=await(await fetch(`http://127.0.0.1:${input.port}/json/version`)).json();await new Promise(resolve=>{const ws=new WebSocket(webSocketDebuggerUrl);const done=()=>{try{ws.close();}catch{}resolve();};ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Browser.close'}));ws.onmessage=done;ws.onerror=done;ws.onclose=done;setTimeout(done,3000);});}catch{}await pause(500);try{execFileSync('taskkill',['/PID',String(child.pid),'/T','/F'],{stdio:'ignore'});}catch{}}
run().catch(async error=>{console.error(String(error));process.exitCode=1;try{await shot('failure.png');}catch{}}).finally(async()=>{socket?.close();await closeBrowser();setTimeout(()=>process.exit(process.exitCode||0),300);});
