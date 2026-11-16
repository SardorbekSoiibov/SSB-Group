const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const input=JSON.parse(fs.readFileSync(0,'utf8'));let child,socket,next=0;const pending=new Map();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(ok,label){if(!ok)throw Error(label);}
async function until(fn,label){const end=Date.now()+25000;while(Date.now()<end){try{if(await fn())return;}catch{}await pause(100);}throw Error('Timeout: '+label);}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result?.value;}
async function navigate(query=''){await command('Page.navigate',{url:input.server+'/management/enterprise/reports/'+query});await until(()=>evaluate("!!document.querySelector('#financial-report-filters')"),'report ready');}
async function run(){
 check(new URL(input.server).hostname==='127.0.0.1','Temporary local server only');
 child=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless','--disable-gpu','--no-first-run',
  '--disable-background-timer-throttling','--remote-debugging-port='+input.port,'--user-data-dir='+path.join(input.root,'profile'),input.server+'/management/hisob/kirish/'],{windowsHide:true,stdio:'ignore'});
 let target;await until(async()=>{target=(await(await fetch(`http://127.0.0.1:${input.port}/json/list`)).json()).find(t=>t.type==='page'&&t.url.startsWith(input.server));return target;},'browser');
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise(resolve=>socket.onopen=resolve);
 socket.onmessage=event=>{const data=JSON.parse(event.data),call=pending.get(data.id);if(call){pending.delete(data.id);clearTimeout(call.timer);data.error?call.reject(Error(data.error.message)):call.resolve(data.result);}};
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await until(()=>evaluate("!!document.querySelector('[name=username]')"),'login');
 await evaluate(`(()=>{document.querySelector('[name=username]').value=${JSON.stringify(input.username)};document.querySelector('[name=password]').value=${JSON.stringify(input.password)};document.querySelector('[name=username]').closest('form').requestSubmit();})()`);
 await until(()=>evaluate("location.pathname==='/management/enterprise/'"),'signed in');
 await navigate();
 check(await evaluate("document.querySelector('.data-table').textContent.replace(/\\s/g,'').includes('10000000.00')"),'receipt sum from ledger');
 check(await evaluate("document.querySelector('details.panel a')?.href.includes('/ledger/')"),'actual ledger source links');
 await evaluate("document.querySelector('[name=report]').value='profit';document.querySelector('#financial-report-filters').requestSubmit()");
 await until(()=>evaluate("location.search.includes('report=profit')&&document.querySelector('.data-table').textContent.replace(/\\s/g,'').includes('3000000.00')"),'profit calculation');
 await evaluate(`(()=>{document.querySelector('[name=report]').value='earnings';document.querySelector('[name=employee]').value=${JSON.stringify(String(input.employee))};document.querySelector('[name=project]').value=${JSON.stringify(String(input.project))};document.querySelector('#financial-report-filters').requestSubmit();})()`);
 await until(()=>evaluate("location.search.includes('report=earnings')&&document.querySelector('.data-table').textContent.replace(/\\s/g,'').includes('7000000.00')"),'combined filters');
 await command('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:input.root});
 for(const kind of ['xlsx','pdf','csv']){
  await evaluate(`document.querySelector('button[name=export][value=${kind}]').click()`);
  await until(()=>fs.existsSync(path.join(input.root,'ssb-earnings-UZS.'+kind)),'download '+kind);
 }
 await command('Page.captureScreenshot',{format:'png'}).then(result=>fs.writeFileSync(path.join(input.root,'financial-desktop.png'),Buffer.from(result.data,'base64')));
 await evaluate("document.querySelector('[name=report]').value='outstanding';document.querySelector('[name=report]').dispatchEvent(new Event('change'))");
 check(await evaluate("document.querySelector('[name=dan]').disabled&&!document.querySelector('#report-date-hint').hidden"),'as-of dates explicit');
 await evaluate("document.querySelector('[name=report]').value='monthly';document.querySelector('[name=report]').dispatchEvent(new Event('change'));document.querySelector('[name=dan]').value='';document.querySelector('#financial-report-filters').requestSubmit()");
 await until(()=>evaluate("!!document.querySelector('.field-error[role=alert]')"),'invalid date is visible');
 await navigate('?report=earnings');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(250);
 check(await evaluate("document.documentElement.scrollWidth<=innerWidth+1"),'mobile no overflow');
 await command('Page.captureScreenshot',{format:'png'}).then(result=>fs.writeFileSync(path.join(input.root,'financial-mobile.png'),Buffer.from(result.data,'base64')));
 console.log(JSON.stringify({ok:true,receipt:true,profit:true,filters:true,sources:true,xlsx:true,pdf:true,csv:true,invalidDates:true,asOfDates:true,mobile:true,screenshots:input.root}));
}
const killTree=proc=>{if(!proc?.pid)return;try{require('node:child_process').execFileSync('taskkill',['/PID',String(proc.pid),'/T','/F'],{stdio:'ignore'});}catch{proc.kill();}};
// Edge's launcher exits after handing off, so ask the browser itself to quit; kill the tree only as a fallback.
async function closeBrowser(port,proc){try{const {webSocketDebuggerUrl}=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();await new Promise(resolve=>{const ws=new WebSocket(webSocketDebuggerUrl);const done=()=>{try{ws.close();}catch{}resolve();};ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Browser.close'}));ws.onmessage=done;ws.onerror=done;ws.onclose=done;setTimeout(done,3000);});}catch{}await new Promise(resolve=>setTimeout(resolve,500));killTree(proc);}
run().catch(error=>{console.error(String(error));process.exitCode=1;}).finally(async()=>{socket?.close();await closeBrowser(input.port,child);setTimeout(()=>process.exit(process.exitCode||0),400);});
