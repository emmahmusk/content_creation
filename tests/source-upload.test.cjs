const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../static/js/source-upload.js'),'utf8');

function setup({failure=false,cancelled=false,valid=true,existingToken=''}={}){
  const file=new Blob([new Uint8Array(7_000_000)]);file.name='recording.mp4';
  const input={files:[file],disabled:false,addEventListener(name,handler){this[name]=handler;}};
  const token={value:existingToken};
  const status={textContent:''};const progress={hidden:true,value:0};
  const cancel={hidden:true,addEventListener(name,handler){this[name]=handler;}};
  const button={disabled:false};
  const fields={'[name="file"]':input,'[name="cloudinary_upload_token"]':token,
    '[data-source-upload-status]':status,'[data-source-upload-progress]':progress,
    '[data-source-upload-cancel]':cancel,'[name="rights_confirmed"]':{checked:true},
    '[name="external_url"]':{value:''},'[name="csrfmiddlewaretoken"]':{value:'csrf'},'[type="submit"]':button};
  const state={requests:[],fetches:0,submissions:0,valid};
  const form={dataset:{directUploadUrl:'/orders/source-upload/',uploadMaxBytes:'10000000'},
    querySelector(selector){return fields[selector];},
    addEventListener(name,handler){this[name]=handler;},
    checkValidity(){return state.valid;},
    requestSubmit(){if(state.valid){state.submissions++;this.submit(event());}}
  };
  function event(){return {submitter:button,preventDefault(){},stopPropagation(){}};}
  class Body{constructor(){this.entries=new Map();}append(key,value){this.entries.set(key,value);}}
  class Xhr{
    constructor(){this.headers={};this.upload={};state.requests.push(this);}
    open(method,url){this.method=method;this.url=url;}
    setRequestHeader(key,value){this.headers[key]=value;}
    send(body){
      this.body=body;
      queueMicrotask(()=>{
        if(cancelled){cancel.click();return;}
        this.upload.onprogress({lengthComputable:true,loaded:1,total:1});
        this.status=failure?500:200;
        this.responseText=JSON.stringify({public_id:'recast/source/incoming/1/id',done:state.requests.length===2});
        this.onload();
      });
    }
    abort(){this.onabort();}
  }
  vm.runInNewContext(script,{document:{querySelectorAll:()=>[form]},Blob,FormData:Body,XMLHttpRequest:Xhr,
    fetchWithTimeout:async()=>{state.fetches++;return {ok:true,json:async()=>({params:{public_id:'recast/source/incoming/1/id',timestamp:1,overwrite:'false'},
      signature:'signed',api_key:'public',upload_url:'https://api.cloudinary.com/test/video/upload',chunk_bytes:6_000_000,token:'verified-ticket'})};},
    setButtonBusy:(target,busy)=>{target.disabled=busy;}});
  return {form,input,token,status,progress,cancel,button,state,submit:()=>form.submit(event())};
}

test('chunks finish before the native project submission and exclude the original file',async()=>{
  const context=setup();await context.submit();
  assert.equal(context.state.submissions,1);
  assert.equal(context.state.requests.length,2);
  assert.equal(context.state.requests[0].headers['Content-Range'],'bytes 0-5999999/7000000');
  assert.equal(context.state.requests[1].headers['Content-Range'],'bytes 6000000-6999999/7000000');
  assert.equal(context.state.requests[0].headers['X-Unique-Upload-Id'],context.state.requests[1].headers['X-Unique-Upload-Id']);
  assert.equal(context.token.value,'verified-ticket');
  assert.equal(context.input.disabled,true);
  assert.equal(context.progress.value,100);
});

test('storage failure never submits the project and allows retry',async()=>{
  const context=setup({failure:true});await context.submit();
  assert.equal(context.state.submissions,0);
  assert.equal(context.token.value,'');
  assert.equal(context.input.disabled,false);
  assert.equal(context.button.disabled,false);
});

test('cancellation aborts the upload and never submits',async()=>{
  const context=setup({cancelled:true});await context.submit();
  assert.equal(context.state.submissions,0);
  assert.match(context.status.textContent,/cancelled/);
  assert.equal(context.input.disabled,false);
});

test('field validation after upload preserves the ticket without uploading twice',async()=>{
  const context=setup({valid:false});await context.submit();
  assert.equal(context.state.submissions,0);
  assert.equal(context.token.value,'verified-ticket');
  context.state.valid=true;
  await context.submit();
  assert.equal(context.state.submissions,1);
  assert.equal(context.state.fetches,1);
  assert.equal(context.state.requests.length,2);
});

test('rights confirmation is required before issuing an upload request',async()=>{
  const context=setup();context.form.querySelector('[name="rights_confirmed"]').checked=false;
  await context.submit();
  assert.equal(context.state.fetches,0);
  assert.equal(context.state.submissions,0);
});
