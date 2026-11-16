const fs = require('node:fs'), path = require('node:path'), {spawn} = require('node:child_process');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let child, socket, sequence = 0;
const pending = new Map(), pause = ms => new Promise(r => setTimeout(r, ms));
function check(value, label) { if (!value) throw Error(label); }
async function until(fn, label) { const end = Date.now() + 20000; while (Date.now() < end) { try { if (await fn()) return; } catch {} await pause(100); } throw Error('Timeout: ' + label); }
function command(method, params = {}) { return new Promise((resolve, reject) => { const id = ++sequence, timer = setTimeout(() => {pending.delete(id); reject(Error(method));}, 15000); pending.set(id, {resolve,reject,timer}); socket.send(JSON.stringify({id,method,params})); }); }
async function evaluate(expression) { const r = await command('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true}); if(r.exceptionDetails) throw Error(r.exceptionDetails.text); return r.result?.value; }
async function goto(route, selector) { await command('Page.navigate', {url: input.server + route}); await until(() => evaluate(`!!document.querySelector(${JSON.stringify(selector)})`), selector); }
async function screenshot(name) { await evaluate('document.fonts.ready.then(()=>true)'); await pause(1000); const shot = await command('Page.captureScreenshot', {format:'png',captureBeyondViewport:false}); fs.writeFileSync(path.join(input.root,name), Buffer.from(shot.data,'base64')); }
async function run() {
 check(new URL(input.server).hostname === '127.0.0.1', 'Local test server only');
 child = spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', ['--headless','--disable-gpu','--no-first-run','--remote-debugging-port='+input.port,'--user-data-dir='+path.join(input.root,'profile'), 'about:blank'], {windowsHide:true,stdio:'ignore'});
 let target; await until(async () => {target=(await (await fetch(`http://127.0.0.1:${input.port}/json/list`)).json()).find(t=>t.type==='page'); return target;}, 'browser');
 socket = new WebSocket(target.webSocketDebuggerUrl); await new Promise(r=>socket.onopen=r);
 socket.onmessage = e => {const data=JSON.parse(e.data), call=pending.get(data.id); if(call){pending.delete(data.id);clearTimeout(call.timer);data.error?call.reject(Error(data.error.message)):call.resolve(data.result);}};
 await command('Network.enable');
 await command('Network.setCookie', {name:'sessionid',value:input.session,url:input.server,httpOnly:true});
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await goto('/management/enterprise/performance/', '.eval-prepare');
 await screenshot('evaluation-list-desktop.png');
 for(const id of input.evaluations) {
  await goto('/management/enterprise/performance/evaluation/'+id+'/', '[name=manager]');
  await evaluate(`(()=>{document.querySelector('[name=manager]').value='85';document.querySelector('[name=feedback]').value='Dalillar brauzer orqali tekshirildi.';document.querySelector('[name=reason]').value='Rahbar bahosi tasdiqlangan vazifalar asosida.';document.querySelector('button[value=approve]').click();})()`);
  await until(()=>evaluate(`!document.querySelector('[name=manager]') && document.querySelector('.eval-summary')`),'approval');
 }
 await goto('/management/enterprise/performance/', '.eval-publish');
 await evaluate("document.querySelector('.eval-publish button').click()");
 await until(()=>evaluate("!!document.querySelector('.weekly-podium') || document.querySelector('#confirm-dialog')?.open"),'publication confirmation');
 if(await evaluate("!!document.querySelector('#confirm-dialog')?.open")) await evaluate("document.querySelector('#confirm-accept').click()");
 await until(()=>evaluate("!!document.querySelector('.weekly-podium')"),'published podium');
 check(await evaluate("document.querySelectorAll('.podium-person').length===3"),'three podium places');
 check(await evaluate("document.querySelector('.podium-place-1 h2').textContent.includes('Dev')"),'real work wins');
 await screenshot('ranking-desktop.png');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(250);
 check(await evaluate('document.documentElement.scrollWidth <= innerWidth+1'),'mobile overflow');
 check(await evaluate("getComputedStyle(document.querySelector('.weekly-podium')).flexDirection==='column'"),'mobile podium');
 await screenshot('ranking-mobile.png');
 console.log(JSON.stringify({approved:input.evaluations.length,podium:3,mobileOverflow:false}));
}
run().then(()=>{socket?.close();child?.kill();}).catch(e=>{console.error(e.stack);socket?.close();child?.kill();process.exitCode=1;});
