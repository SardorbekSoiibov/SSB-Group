// QA only: drives headless Edge against a temporary local test server (credentials arrive on stdin).
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const input=JSON.parse(fs.readFileSync(0,'utf8'));let child,socket,next=0;const pending=new Map();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(ok,label){if(!ok)throw Error(label);}
async function until(fn,label){const end=Date.now()+25000;while(Date.now()<end){try{if(await fn())return;}catch{}await pause(100);}throw Error('Timeout: '+label);}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result?.value;}
const errors=[];
async function shot(name){const result=await command('Page.captureScreenshot',{format:'png'});fs.writeFileSync(path.join(input.root,name),Buffer.from(result.data,'base64'));}
async function archives(){await command('Page.navigate',{url:input.server+'/management/enterprise/archives/'});await until(()=>evaluate("document.readyState==='complete'&&!!document.querySelector('.page-heading')"),'archive page');}
async function signIn(username,password){
 await command('Network.clearBrowserCookies');
 await command('Page.navigate',{url:input.server+'/management/hisob/kirish/'});
 await until(()=>evaluate("!!document.querySelector('[name=username]')"),'login form');
 await evaluate(`(()=>{document.querySelector('[name=username]').value=${JSON.stringify(username)};document.querySelector('[name=password]').value=${JSON.stringify(password)};document.querySelector('[name=username]').closest('form').requestSubmit();})()`);
 await until(()=>evaluate("location.pathname==='/management/enterprise/'"),'signed in as '+username);
}
async function run(){
 check(new URL(input.server).hostname==='127.0.0.1','Temporary local server only');
 child=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless','--disable-gpu','--no-first-run',
  '--remote-debugging-port='+input.port,'--user-data-dir='+path.join(input.root,'profile'),'about:blank'],{windowsHide:true,stdio:'ignore'});
 let target;await until(async()=>{target=(await(await fetch(`http://127.0.0.1:${input.port}/json/list`)).json()).find(t=>t.type==='page');return target;},'browser');
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.onopen=resolve);
 socket.onmessage=event=>{const data=JSON.parse(event.data),call=pending.get(data.id);if(call){pending.delete(data.id);clearTimeout(call.timer);data.error?call.reject(Error(data.error.message)):call.resolve(data.result);}
  if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails?.exception?.description||data.params.exceptionDetails?.text);};
 await command('Runtime.enable');await command('Network.enable');
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});

 // 1. Founder: no code yet -> sets the company code through the real form, which unlocks the section.
 await signIn(input.founder,input.password);
 await archives();
 check(await evaluate("!document.querySelector('#archive-unlock-form')&&!!document.querySelector('#archive-code-form')"),'founder sees code settings, no unlock form before a code exists');
 check(await evaluate("document.querySelector('#archive-gate').matches(':modal')"),'gate is a true modal');
 await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await pause(150);
 check(await evaluate("document.querySelector('#archive-gate').open"),'Escape does not dismiss the gate');
 await shot('archive-modal-founder.png');
 await evaluate(`(()=>{const f=document.querySelector('#archive-code-form');f.querySelector('[name=code]').value=${JSON.stringify(input.code)};f.querySelector('[name=confirm_code]').value=${JSON.stringify(input.code)};f.requestSubmit();})()`);
 await until(()=>evaluate("!!document.querySelector('[data-record-template=archive-upload]')"),'founder unlocked after setting code');

 // Founder rotates the code from its own modal while the section is open.
 await evaluate("document.querySelector('[data-archive-open=archive-code-dialog]').click()");
 await until(()=>evaluate("document.querySelector('#archive-code-dialog').matches(':modal')"),'code dialog open');
 await shot('archive-modal-rotate.png');
 await evaluate("document.querySelector('#archive-code-dialog [data-archive-close]').click()");
 check(await evaluate("!document.querySelector('#archive-code-dialog').open"),'code dialog closes');
 // 2. Founder uploads a file with a free-text project name through the upload sheet.
 check(await evaluate("!!document.querySelector('.archive-empty')"),'empty state');
 await shot('archive-empty.png');
 await evaluate("document.querySelector('.archive-empty [data-record-template=archive-upload]').click()");
 await until(()=>evaluate("!!document.querySelector('#record-dialog[open] input[type=file][name=file]')"),'upload sheet open');
 const doc=await command('DOM.getDocument',{depth:-1});
 const node=await command('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#record-dialog[open] input[type=file][name=file]'});
 await command('DOM.setFileInputFiles',{nodeId:node.nodeId,files:[input.uploadFile]});
 await until(()=>evaluate("document.querySelector('#record-dialog .archive-drop')?.textContent.includes('archive-qa.zip')&&document.querySelector('#record-dialog [name=project_name]').value==='archive qa'"),'dropzone shows file and suggests a name');
 await pause(300);await shot('archive-upload-modal.png');
 await evaluate(`(()=>{const f=document.querySelector('#record-dialog[open] form');f.querySelector('[name=project_name]').value=${JSON.stringify(input.projectName)};f.requestSubmit();})()`);
 await until(()=>evaluate(`document.querySelector('#archive-list')?.textContent.includes(${JSON.stringify(input.projectName)})`),'uploaded file listed');
 check(await evaluate("document.querySelector('#archive-list').textContent.includes('archive-qa.zip')&&document.querySelector('.archive-stat dd').textContent.trim()==='1'"),'filename and stats listed');
 await shot('archive-founder-desktop.png');

 // 3. A different employee: locked view, wrong code error, correct code unlocks, download works.
 await signIn(input.employee,input.password);
 await archives();
 check(await evaluate("!!document.querySelector('#archive-unlock-form')&&!document.querySelector('#archive-list')&&!document.querySelector('#archive-code-form')"),'employee sees locked section, no file list, no code settings');
 check(await evaluate("!document.body.textContent.includes('archive-qa.zip')"),'filenames hidden while locked');
 await evaluate("(()=>{const f=document.querySelector('#archive-unlock-form');f.querySelector('[name=code]').value='definitely-wrong-code';f.requestSubmit();})()");
 await until(()=>evaluate("document.body.textContent.includes('Arxiv kodi noto‘g‘ri')"),'wrong code error shown');
 check(await evaluate("document.querySelector('.breadcrumbs')?.textContent.includes('Xavfsiz arxiv')"),'breadcrumb keeps archive section after failed unlock');
 check(await evaluate("document.querySelector('#archive-gate').matches(':modal')&&document.activeElement===document.querySelector('#archive-unlock-form [name=code]')"),'modal reopens focused after a wrong code');
 await shot('archive-wrong-code.png');
 await evaluate(`(()=>{const f=document.querySelector('#archive-unlock-form');f.querySelector('[name=code]').value=${JSON.stringify(input.code)};f.requestSubmit();})()`);
 await until(()=>evaluate("document.querySelector('#archive-list')?.textContent.includes('archive-qa.zip')"),'employee sees shared file after unlock');
 // Step 2: each download asks a math question; a wrong answer gives no file, the right one downloads it.
 await evaluate("[...document.querySelectorAll('a[href*=\"/download/\"]')][0].click()");
 await until(()=>evaluate("document.querySelector('#archive-challenge')?.matches(':modal')"),'math question modal');
 await pause(350);await shot('archive-math-modal.png');
 check(await evaluate("document.querySelector('#archive-question').textContent.trim().endsWith('= ?')"),'question shown');
 const solve="(()=>{const m=document.querySelector('#archive-question').textContent.match(/([0-9]+) *([-+×]) *([0-9]+)/);const x=Number(m[1]),y=Number(m[3]);return m[2]==='+'?x+y:m[2]==='-'?x-y:x*y;})()";
 const right=await evaluate(solve);
 await evaluate(`(()=>{const f=document.querySelector('#archive-challenge-form');f.querySelector('[name=answer]').value=String(${right}+1);f.requestSubmit();})()`);
 await until(()=>evaluate("document.body.textContent.includes('Javob noto‘g‘ri')"),'wrong answer rejected');
 check(!fs.existsSync(path.join(input.root,'downloads','archive-qa.zip')),'no file after wrong answer');
 await shot('archive-math-wrong.png');
 fs.mkdirSync(path.join(input.root,'downloads'),{recursive:true});
 await command('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:path.join(input.root,'downloads')});
 await evaluate(`(()=>{const f=document.querySelector('#archive-challenge-form');f.querySelector('[name=answer]').value=String(${solve});f.requestSubmit();})()`);
 await until(()=>fs.existsSync(path.join(input.root,'downloads','archive-qa.zip')),'file downloaded after correct answer');
 await until(()=>evaluate("!document.querySelector('[data-challenge-view=done]').hidden"),'success state after download');
 await pause(300);await shot('archive-math-done.png');
 await command('Page.navigate',{url:input.server+'/management/enterprise/archives/'});
 await until(()=>evaluate("!!document.querySelector('#archive-list')"),'archive still open after downloading');
 const search=await evaluate("(async()=>{const r=await fetch('/management/enterprise/archives/?q=nomavjud-qidiruv');return (await r.text()).includes('Qidiruvga mos fayl topilmadi');})()");
 check(search,'search empty state');

 // Leaving for another section relocks the archive; coming back asks for the code again.
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await command('Page.navigate',{url:input.server+'/management/enterprise/'});
 await until(()=>evaluate("location.pathname==='/management/enterprise/'"),'left archive');
 await archives();
 check(await evaluate("!!document.querySelector('#archive-unlock-form')&&!document.querySelector('#archive-list')"),'code asked again after leaving');
 await pause(450);
 check(await evaluate("document.documentElement.scrollWidth<=innerWidth+1"),'modal fits mobile');
 check(await evaluate("(()=>{const r=document.querySelector('#archive-unlock-form button[type=submit]').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;})()"),'submit button visible on mobile');
 await shot('archive-modal-mobile.png');
 await evaluate(`(()=>{const f=document.querySelector('#archive-unlock-form');f.querySelector('[name=code]').value=${JSON.stringify(input.code)};f.requestSubmit();})()`);
 await until(()=>evaluate("!!document.querySelector('#archive-list')"),'unlocked again');
 // 4. Mobile layout of the unlocked section, then lock again.
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await archives();await pause(300);
 check(await evaluate("document.documentElement.scrollWidth<=innerWidth+1"),'mobile no horizontal overflow');
 await shot('archive-employee-mobile.png');
 await evaluate("[...document.querySelectorAll('form[action$=\"/archives/lock/\"] button')][0].click()");
 await until(()=>evaluate("!!document.querySelector('#archive-unlock-form')"),'lock returns to code prompt');
 // Only the author or Founder sees the delete control; the Founder removes the project through its modal.
 check(await evaluate("!document.querySelector('[data-secure-delete]')"),'employee has no delete control on another author project');
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await signIn(input.founder,input.password);
 await archives();
 await evaluate(`(()=>{const f=document.querySelector('#archive-unlock-form');f.querySelector('[name=code]').value=${JSON.stringify(input.code)};f.requestSubmit();})()`);
 await until(()=>evaluate("!!document.querySelector('form[data-secure-delete]')"),'founder sees delete control');
 const secure=`document.querySelector('#secure-delete-dialog')`;
 await evaluate("document.querySelector('form[data-secure-delete] button').click()");
 await until(()=>evaluate(`${secure}.matches(':modal')&&document.querySelector('#secure-items').textContent.includes('archive-qa.zip')`),'step one lists the project');
 await pause(300);await shot('secure-step1.png');
 await evaluate(`${secure}.querySelector('[data-close-dialog]').click()`);await pause(200);
 check(await evaluate(`!${secure}.open&&!!document.querySelector('.archive-card')`),'cancel keeps the project');
 await evaluate("document.querySelector('form[data-secure-delete] button').click()");
 await until(()=>evaluate(`${secure}.open`),'dialog reopens');
 await evaluate("document.querySelector('#secure-next').click()");
 check(await evaluate("document.querySelector('#secure-accept').disabled&&document.activeElement===document.querySelector('#secure-password')"),'step two needs a password');
 await pause(250);await shot('secure-step2.png');
 const type=async value=>{await evaluate(`(()=>{const i=document.querySelector('#secure-password');i.value=${JSON.stringify(value)};i.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#secure-accept').click();})()`);};
 await type('definitely-wrong');
 await until(()=>evaluate("document.body.textContent.includes('Parol noto‘g‘ri')&&!!document.querySelector('.archive-card')"),'wrong password keeps the project');
 await evaluate("document.querySelector('form[data-secure-delete] button').click()");
 await until(()=>evaluate(`${secure}.open`),'dialog opens again');
 await evaluate("document.querySelector('#secure-next').click()");
 await type(input.password);
 await until(()=>evaluate("!!document.querySelector('.archive-empty')&&document.querySelector('.archive-stat dd').textContent.trim()==='0'"),'project removed');
 check(errors.length===0,'no JavaScript exceptions: '+errors.join(' | '));
 console.log(JSON.stringify({ok:true,founderSetsCode:true,founderUpload:true,lockedForEmployee:true,wrongCodeError:true,unlock:true,mathWrongRejected:true,mathDownload:true,relockAfterLeaving:true,removal:true,search:true,mobile:true,lock:true,twoStepDelete:true,jsErrors:errors.length,screenshots:input.root}));
}
const killTree=proc=>{if(!proc?.pid)return;try{require('node:child_process').execFileSync('taskkill',['/PID',String(proc.pid),'/T','/F'],{stdio:'ignore'});}catch{proc.kill();}};
// Edge's launcher exits after handing off, so ask the browser itself to quit; kill the tree only as a fallback.
async function closeBrowser(port,proc){try{const {webSocketDebuggerUrl}=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();await new Promise(resolve=>{const ws=new WebSocket(webSocketDebuggerUrl);const done=()=>{try{ws.close();}catch{}resolve();};ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Browser.close'}));ws.onmessage=done;ws.onerror=done;ws.onclose=done;setTimeout(done,3000);});}catch{}await new Promise(resolve=>setTimeout(resolve,500));killTree(proc);}
run().catch(async error=>{console.error(String(error));process.exitCode=1;try{await shot('failure.png');console.error('URL '+await evaluate('location.href')+' TEXT '+await evaluate("(document.querySelector('#content')||document.body).innerText.slice(0,700)"));}catch{}}).finally(async()=>{socket?.close();await closeBrowser(input.port,child);setTimeout(()=>process.exit(process.exitCode||0),400);});
