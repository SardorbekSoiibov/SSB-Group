// QA only: signs in to the packaged app and reads the capture protection state the window reports.
const fs=require('node:fs'),path=require('node:path'),{spawn,execFileSync}=require('node:child_process');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let app,socket,next=1;const pending=new Map();
async function until(fn,label){const end=Date.now()+30000;while(Date.now()<end){try{const v=await fn();if(v)return v;}catch{}await pause(180);}throw Error('Timeout: '+label);}
function command(method,params={}){return new Promise((resolve,reject)=>{const id=next++,t=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);pending.set(id,{resolve:v=>{clearTimeout(t);resolve(v);},reject});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result?.value;}
async function session(username,profile,port){
 fs.mkdirSync(profile,{recursive:true});fs.writeFileSync(path.join(profile,'window.json'),JSON.stringify({server:input.server}));
 const env={...process.env};delete env.ELECTRON_RUN_AS_NODE;delete env.NODE_OPTIONS;
 app=spawn(input.exe,['--qa-hidden','--smoke-root='+profile,'--remote-debugging-address=127.0.0.1','--remote-debugging-port='+port],{env,windowsHide:true,stdio:'ignore'});
 const target=await until(async()=>(await(await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t=>t.url.startsWith(input.server)),'renderer');
 socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
 socket.onmessage=event=>{const d=JSON.parse(event.data),c=pending.get(d.id);if(c){pending.delete(d.id);d.error?c.reject(Error(d.error.message)):c.resolve(d.result);}};
 await until(()=>evaluate("!!document.querySelector('[name=username]')"),'login form');
 await evaluate(`(()=>{document.querySelector('[name=username]').value=${JSON.stringify(username)};document.querySelector('[name=password]').value=${JSON.stringify(input.password)};document.querySelector('[name=username]').closest('form').requestSubmit();})()`);
 await until(()=>evaluate("location.pathname==='/management/enterprise/'&&document.readyState==='complete'"),'signed in');
 await pause(900);
 const result=JSON.parse(fs.readFileSync(path.join(profile,'capture-state.json'),'utf8'));
 socket.close();try{execFileSync('taskkill',['/PID',String(app.pid),'/T','/F'],{stdio:'ignore'});}catch{}
 await pause(800);
 return result;
}
(async()=>{
 const blocked=await session(input.blockedUser,path.join(input.root,'blocked'),input.port);
 const allowed=await session(input.allowedUser,path.join(input.root,'allowed'),input.port+1);
 console.log(JSON.stringify({blocked,allowed}));
})().catch(e=>{console.error(String(e));try{app&&execFileSync('taskkill',['/PID',String(app.pid),'/T','/F'],{stdio:'ignore'});}catch{}process.exit(1);}).finally(()=>setTimeout(()=>process.exit(process.exitCode||0),200));
