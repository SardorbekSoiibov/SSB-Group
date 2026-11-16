// Real Edge sessions against a temporary PostgreSQL test database. No credentials are written to disk.
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const input=JSON.parse(fs.readFileSync(0,'utf8')),children=[],sockets=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(ok,label){if(!ok)throw Error(label);}
async function until(fn,label){const end=Date.now()+30000;while(Date.now()<end){try{if(await fn())return;}catch{}await pause(120);}throw Error('Timeout: '+label);}
async function browser(index){
 const port=input.ports[index],url=input.server+'/management/hisob/kirish/';
 const child=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
  '--headless','--disable-gpu','--no-first-run','--disable-background-timer-throttling',
  '--remote-debugging-port='+port,'--user-data-dir='+path.join(input.root,String(index)),url],{windowsHide:true,stdio:'ignore'});
 children.push(child);let target;
 await until(async()=>{target=(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.startsWith(input.server));return !!target;},'browser ready');
 const socket=new WebSocket(target.webSocketDebuggerUrl);sockets.push(socket);await new Promise(resolve=>socket.onopen=resolve);
 let next=0;const pending=new Map();socket.onmessage=event=>{const data=JSON.parse(event.data),call=pending.get(data.id);if(call){pending.delete(data.id);clearTimeout(call.timer);data.error?call.reject(Error(data.error.message)):call.resolve(data.result);}};
 const command=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=async expression=>{const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result?.value;};
 await until(()=>evaluate("!!document.querySelector('[name=username]')"),'login ready');
 await evaluate(`(()=>{document.querySelector('[name=username]').value=${JSON.stringify(input.users[index].username)};document.querySelector('[name=password]').value=${JSON.stringify(input.password)};document.querySelector('[name=username]').closest('form').requestSubmit();})()`);
 await until(()=>evaluate("location.pathname==='/management/enterprise/'"),'login accepted');
 const chat=input.server+'/management/chat/'+input.users[1-index].id+'/';
 await command('Page.navigate',{url:chat});
 await until(()=>evaluate("!!document.querySelector('#chat-form')"),'chat ready');
 await evaluate("Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'))");
 await until(()=>evaluate("document.querySelectorAll('.chat-message').length===50"),'history loaded');
 return {command,evaluate,chat};
}
async function send(client,text){
 await client.evaluate(`(()=>{const field=document.querySelector('#chat-body');field.value=${JSON.stringify(text)};field.dispatchEvent(new Event('input'));field.closest('form').requestSubmit();})()`);
 await until(()=>client.evaluate("document.querySelector('#chat-body').value===''"),'message sent');
}
async function run(){
 check(new URL(input.server).hostname==='127.0.0.1','Temporary localhost server required');
 const a=await browser(0),b=await browser(1);
 await a.evaluate("document.querySelector('#chat-older').click()");
 await until(()=>a.evaluate("document.querySelectorAll('.chat-message').length===65"),'older history without duplicates');
 const unsafe='<img src=x onerror="window.chatXss=true"> & literal message';
 await send(a,unsafe);
 await until(()=>b.evaluate(`Array.from(document.querySelectorAll('.chat-message p')).some(n=>n.textContent===${JSON.stringify(unsafe)})`),'cross-session message delivery');
 check(await b.evaluate("!window.chatXss&&!document.querySelector('#chat-messages img')"),'XSS text is not executed');
 await until(()=>a.evaluate("document.querySelector('.chat-message:last-child small').textContent.includes('O‘qildi')"),'read receipt');
 await send(b,'Browser reply');
 await until(()=>a.evaluate("document.querySelector('#chat-messages').textContent.includes('Browser reply')"),'reply delivered');
 await a.command('Network.enable');
 await a.command('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
 await a.evaluate("document.querySelector('#chat-body').value='Retry after offline';document.querySelector('#chat-form').requestSubmit()");
 await until(()=>a.evaluate("!document.querySelector('#chat-error').hidden"),'offline send feedback');
 check(await a.evaluate("document.querySelector('#chat-body').value==='Retry after offline'"),'failed message remains in composer');
 await send(b,'After reconnect');
 await a.command('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
 await a.evaluate("window.dispatchEvent(new Event('online'))");
 await until(()=>a.evaluate("document.querySelector('#chat-messages').textContent.includes('After reconnect')"),'missed message recovered');
 await a.evaluate("document.querySelector('#chat-form').requestSubmit()");
 await until(()=>a.evaluate("document.querySelector('#chat-body').value===''"),'retry succeeds');
 await a.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await pause(300);
 check(await a.evaluate("document.documentElement.scrollWidth<=innerWidth+1&&document.querySelector('#chat-body').getBoundingClientRect().width>100"),'mobile layout fits');
 await a.command('Page.navigate',{url:a.chat});
 await until(()=>a.evaluate("document.querySelector('#chat-messages')?.textContent.includes('Retry after offline')"),'message persists after reload');
 await a.command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await pause(250);
 await a.command('Page.captureScreenshot',{format:'png'}).then(result=>fs.writeFileSync(path.join(input.root,'chat-desktop.png'),Buffer.from(result.data,'base64')));
 await a.command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(150);
 await a.command('Page.captureScreenshot',{format:'png'}).then(result=>fs.writeFileSync(path.join(input.root,'chat-mobile.png'),Buffer.from(result.data,'base64')));
 console.log(JSON.stringify({ok:true,twoSessions:true,history:true,delivery:true,reply:true,readReceipts:true,xssSafe:true,offlineDraft:true,reconnect:true,retry:true,mobile:true,persistence:true,screenshots:input.root}));
}
const killTree=proc=>{if(!proc?.pid)return;try{require('node:child_process').execFileSync('taskkill',['/PID',String(proc.pid),'/T','/F'],{stdio:'ignore'});}catch{proc.kill();}};
// Edge's launcher exits after handing off, so ask the browser itself to quit; kill the tree only as a fallback.
async function closeBrowser(port,proc){try{const {webSocketDebuggerUrl}=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();await new Promise(resolve=>{const ws=new WebSocket(webSocketDebuggerUrl);const done=()=>{try{ws.close();}catch{}resolve();};ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Browser.close'}));ws.onmessage=done;ws.onerror=done;ws.onclose=done;setTimeout(done,3000);});}catch{}await new Promise(resolve=>setTimeout(resolve,500));killTree(proc);}
run().catch(error=>{console.error(String(error));process.exitCode=1;}).finally(async()=>{sockets.forEach(s=>s.close());await Promise.all(children.map((child,index)=>closeBrowser(input.ports[index],child)));setTimeout(()=>process.exit(process.exitCode||0),400);});
