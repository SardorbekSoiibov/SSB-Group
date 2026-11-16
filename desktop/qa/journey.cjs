// QA only: excluded from packaged files. Credentials arrive through stdin for a temporary test database.
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let processHandle,socket,next=1;const pending=new Map();
function assert(ok,label){if(!ok)throw Error(label);}
async function until(fn,label){const deadline=Date.now()+30000;while(Date.now()<deadline){try{const value=await fn();if(value)return value;}catch{}await pause(180);}throw Error('Timeout: '+label);}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=next++,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value)},reject});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const response=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(response.exceptionDetails)throw Error(response.exceptionDetails.exception?.description||response.exceptionDetails.text);return response.result?.value;}
async function web(url,options={}){const response=await fetch(input.server+url,{...options,headers:{Cookie:input.webCookie,'X-CSRFToken':input.webCSRF,...(options.headers||{})}});assert(response.ok,'Web request '+url+' '+response.status);return response;}
async function run(){
 assert(new URL(input.server).hostname==='127.0.0.1','QA only supports a temporary local server');
 fs.mkdirSync(input.profile,{recursive:true});fs.writeFileSync(path.join(input.profile,'window.json'),JSON.stringify({server:input.server}));
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;delete env.NODE_OPTIONS;
 processHandle=spawn(input.exe,['--qa-hidden','--smoke-root='+input.profile,'--remote-debugging-address=127.0.0.1','--remote-debugging-port='+input.port],{env,windowsHide:true,stdio:'ignore'});
 const target=await until(async()=>{const response=await fetch('http://127.0.0.1:'+input.port+'/json/list');return(await response.json()).find(t=>t.url.startsWith(input.server));},'desktop renderer');
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
 socket.onmessage=event=>{const data=JSON.parse(event.data);const item=pending.get(data.id);if(item){pending.delete(data.id);data.error?item.reject(Error(data.error.message)):item.resolve(data.result);}};
 await until(()=>evaluate("!!document.querySelector('[name=username]') && !!document.querySelector('[name=password]')"),'login form ready');
 await evaluate(`(()=>{document.querySelector('[name=username]').value=${JSON.stringify(input.username)};document.querySelector('[name=password]').value=${JSON.stringify(input.password)};document.querySelector('[name=username]').closest('form').requestSubmit();})()`);
 await until(()=>evaluate("location.pathname==='/management/enterprise/' && !!document.querySelector('#dashboard-widgets') && document.body.dataset.app==='boshqaruv-v2'"),'new dashboard after login');
 const sandbox=await evaluate("typeof window.require==='undefined' && typeof window.ssbDesktop==='undefined'");assert(sandbox,'Remote page has no Node or IPC');
 // QA keeps the native window hidden. Emulate a visible document for the web poller.
 await evaluate("Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'))");
 await until(()=>evaluate("!!document.querySelector('.notification-button[aria-label*=\"0\"]')"),'initial notification poll');
 await web('/management/elonlar/',{method:'POST',body:new URLSearchParams({title:'Windows delivery notification',body:'Cross-session delivery verified'})});
 await evaluate("window.dispatchEvent(new Event('online'))");
 await until(()=>evaluate("document.querySelector('.notification-button b')?.textContent==='1'"),'live notification badge');
 const notice=await evaluate("fetch('/management/enterprise/api/notifications/').then(r=>r.json()).then(d=>d.items.find(i=>i.title==='Windows delivery notification'))");
 assert(notice,'New announcement delivered to desktop recipient');
 await evaluate(`fetch('/management/enterprise/api/notifications/${notice.id}/read/',{method:'POST',headers:{'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value}}).then(r=>{if(!r.ok)throw Error('Read failed')})`);
 await evaluate("window.dispatchEvent(new Event('online'))");
 await until(()=>evaluate("document.querySelector('.notification-button b')?.hidden===true"),'read notification clears badge');
 const chatBody={body:'Web to Windows chat',client_id:crypto.randomUUID()};
 await web(`/management/chat/api/${input.desktopUser}/messages/`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(chatBody)});
 await command('Page.navigate',{url:input.server+'/management/chat/'+input.webUser+'/'});
 await until(()=>evaluate("!!document.querySelector('#chat-form')"),'desktop chat ready');
 await evaluate("Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'))");
 await until(()=>evaluate("document.querySelector('#chat-messages').textContent.includes('Web to Windows chat')"),'web message visible in desktop chat');
 await evaluate("document.querySelector('#chat-body').value='Windows to web chat';document.querySelector('#chat-form').requestSubmit()");
 await until(()=>evaluate("document.querySelector('#chat-body').value===''"),'desktop chat message sent');
 const chatRows=await(await web(`/management/chat/api/${input.desktopUser}/messages/`)).json();
 assert(chatRows.items.some(item=>item.body==='Windows to web chat'&&!item.mine),'Desktop chat reply visible in web');
 const body=new URLSearchParams({title:'Web session update',project:String(input.project),assignee:String(input.employee),priority:'medium',description:'Updated through independent web session'});
 await web(input.editURL,{method:'POST',body});
 assert(await evaluate(`fetch('/management/enterprise/api/tasks/').then(r=>r.json()).then(rows=>rows.some(t=>t.id===${input.task}&&t.title==='Web session update'))`),'Web change visible in desktop');
 const desktopChange=await evaluate(`(async()=>{const html=await fetch(${JSON.stringify(input.editURL)}).then(r=>r.text());const doc=new DOMParser().parseFromString(html,'text/html'),token=doc.querySelector('[name=csrfmiddlewaretoken]').value;const body=new URLSearchParams(${JSON.stringify({title:'Desktop session update',project:String(input.project),assignee:String(input.employee),priority:'medium',description:'Updated through installed desktop'})});const response=await fetch(${JSON.stringify(input.editURL)},{method:'POST',headers:{'X-CSRFToken':token},body});return response.ok&&!((await response.text()).includes('errorlist'));})()`);
 assert(desktopChange,'Desktop task edit accepted');
 const tasks=await(await web('/management/enterprise/api/tasks/')).json();assert(tasks.some(t=>t.id===input.task&&t.title==='Desktop session update'),'Desktop change visible in web');
 await command('Page.navigate',{url:input.server+'/management/enterprise/archives/'});
 await until(()=>evaluate("!!document.querySelector('#archive-unlock-form')"),'archive locked until company code');
 await evaluate(`(()=>{const form=document.querySelector('#archive-unlock-form');form.querySelector('[name=code]').value=${JSON.stringify(input.archiveCode)};form.requestSubmit();})()`);
 await until(()=>evaluate("!!document.querySelector('input[type=file][name=file]')"),'archive upload form');
 const documentNode=await command('DOM.getDocument');
 const fileNode=await command('DOM.querySelector',{nodeId:documentNode.root.nodeId,selector:'input[type=file][name=file]'});
 await command('DOM.setFileInputFiles',{nodeId:fileNode.nodeId,files:[input.uploadFile]});
 await evaluate(`(()=>{const input=document.querySelector('input[type=file][name=file]'),form=input.closest('form');form.querySelector('[name=project_name]').value=${JSON.stringify(input.projectName)};form.requestSubmit();})()`);
 await until(()=>evaluate("document.body.textContent.includes('desktop-delivery.zip')"),'desktop file upload saved');
 await web('/management/enterprise/archives/unlock/',{method:'POST',body:new URLSearchParams({code:input.archiveCode})});
 const uploadedHTML=await(await web('/management/enterprise/archives/')).text();assert(uploadedHTML.includes('desktop-delivery.zip'),'Desktop upload visible in web');
 const download=await evaluate(`(async()=>{const html=await fetch(${JSON.stringify(input.archiveURL)}).then(r=>r.text());const doc=new DOMParser().parseFromString(html,'text/html');const m=doc.querySelector('#archive-question').textContent.match(/([0-9]+) *([-+×]) *([0-9]+)/);const x=Number(m[1]),y=Number(m[3]);const answer=m[2]==='+'?x+y:m[2]==='-'?x-y:x*y;const body=new URLSearchParams({answer:String(answer),csrfmiddlewaretoken:doc.querySelector('[name=csrfmiddlewaretoken]').value});const r=await fetch(${JSON.stringify(input.archiveURL)},{method:'POST',body});return {status:r.status,disposition:r.headers.get('content-disposition')||'',size:(await r.arrayBuffer()).byteLength};})()`);assert(download.status===200&&download.disposition.includes('qa-delivery.zip')&&download.size>0,'Protected file available in desktop after math step');
 const logout=await evaluate(`fetch('/management/hisob/chiqish/',{method:'POST',headers:{'X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value}}).then(r=>r.ok)`);assert(logout,'Desktop logout');
 assert(await evaluate("fetch('/management/enterprise/api/session/').then(r=>r.status===403||r.status===401)"),'Desktop session revoked after logout');
 console.log(JSON.stringify({ok:true,packaged:true,roleLogin:true,webToDesktop:true,desktopToWeb:true,chat:true,notifications:true,privateUpload:true,privateDownload:true,sandbox:true,logout:true}));
}
run().catch(error=>{console.error(String(error));process.exitCode=1;}).finally(()=>{if(socket)socket.close();if(processHandle)processHandle.kill();setTimeout(()=>process.exit(process.exitCode||0),400);});
