const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const script=fs.readFileSync(path.join(__dirname,'../static/js/loading.js'),'utf8');

class Element{
  constructor(html=''){
    this.children=[];this.attributes={};this.dataset={};this.disabled=false;this._html=html;this.className='';
    const classes=new Set();this.classList={add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name)};
  }
  get innerHTML(){return this.children.length?this.children.map(child=>child.innerHTML).join(''):this._html;}
  set innerHTML(value){this._html=value;this.children=[];}
  get textContent(){return this.innerHTML;}
  set textContent(value){this.innerHTML=value;}
  setAttribute(key,value){this.attributes[key]=String(value);}
  getAttribute(key){return this.attributes[key]??null;}
  hasAttribute(key){return key in this.attributes;}
  removeAttribute(key){delete this.attributes[key];}
  replaceChildren(){this.children=[];this._html='';}
  append(...children){this.children.push(...children);}
  querySelector(selector){
    if(selector==='b')return this.label;
    for(const child of this.children){
      if(selector.startsWith('.')&&child.className.split(' ').includes(selector.slice(1)))return child;
      const nested=child.querySelector(selector);if(nested)return nested;
    }
    return null;
  }
}
class Form extends Element{
  constructor(button){super();this.button=button;this.method='post';this.action='/orders/new/';}
  querySelector(){return this.button;}
}

function setup(fetch=async()=>({ok:true})){
  const documentEvents=new Map(),windowEvents=new Map(),navigationEvents=new Map(),timers=new Map();
  const body=new Element(),status=new Element();status.label=new Element();status.setAttribute('aria-hidden','true');
  let now=0,id=0;
  const document={body,querySelector:selector=>selector==='.route-status'?status:null,
    createElement:()=>new Element(),addEventListener:(type,handler)=>documentEvents.set(type,handler)};
  const window={addEventListener:(type,handler)=>windowEvents.set(type,handler),navigation:{addEventListener:(type,handler)=>navigationEvents.set(type,handler)}};
  const context={document,window,location:new URL('https://app.example/orders/1/'),URL,HTMLFormElement:Form,AbortController,queueMicrotask,fetch,
    setTimeout:(callback,delay)=>{const key=++id;timers.set(key,{callback,at:now+delay});return key;},
    clearTimeout:key=>timers.delete(key)};
  vm.runInNewContext(script+'\nglobalThis.loading={setButtonBusy,beginRouteTransition,endRouteTransition,fetchWithTimeout};',context);
  const advance=ms=>{
    const until=now+ms;
    while(true){const next=[...timers].filter(([,entry])=>entry.at<=until).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;now=next[1].at;timers.delete(next[0]);next[1].callback();}
    now=until;
  };
  const click=async(link,extra={})=>{
    const event={target:{closest:()=>link},button:0,defaultPrevented:false,...extra};
    documentEvents.get('click')(event);await Promise.resolve();return event;
  };
  const submit=async(form,submitter)=>{
    const event={target:form,submitter,defaultPrevented:false};documentEvents.get('submit')(event);await Promise.resolve();return event;
  };
  return {body,status,timers,advance,click,submit,documentEvents,windowEvents,navigationEvents,...context.loading};
}
const link=(href='/orders/2/',attributes={})=>{const node=new Element();node.href=href;Object.assign(node.attributes,attributes);return node;};

test('navigation indicator ends when the destination page is shown',async()=>{
  const ui=setup();await ui.click(link());ui.advance(180);
  assert.equal(ui.status.getAttribute('aria-hidden'),'false');
  ui.windowEvents.get('pageshow')({persisted:false});
  assert.equal(ui.body.classList.contains('is-navigating'),false);
  assert.equal(ui.status.getAttribute('aria-hidden'),'true');
  assert.equal(ui.timers.size,0);
});

test('downloads never start a page navigation spinner',async()=>{
  const ui=setup();await ui.click(link('/api/v1/pipeline-runs/id/download-exports/',{download:''}));
  ui.advance(20000);assert.equal(ui.body.classList.contains('is-navigating'),false);assert.equal(ui.timers.size,0);
});

test('explicit in-page actions and named/new windows do not show the loader',async()=>{
  for(const target of ['_blank','preview']){const ui=setup();await ui.click(link('/preview/',{target}));assert.equal(ui.timers.size,0);}
  const ui=setup(),action=link();action.dataset.noTransition='';await ui.click(action);assert.equal(ui.timers.size,0);
});

test('hash links, same-document links and external protocols do not show the loader',async()=>{
  for(const url of ['#section:1','/orders/1/','mailto:hello@example.com','https://other.example']){
    const ui=setup();await ui.click(link(url));assert.equal(ui.timers.size,0);
  }
});

test('modified clicks preserve the browser action without showing the loader',async()=>{
  for(const extra of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{button:1}]){
    const ui=setup();await ui.click(link(),extra);assert.equal(ui.timers.size,0);
  }
});

test('later click handlers can prevent navigation before loading starts',async()=>{
  const ui=setup(),event={target:{closest:()=>link()},button:0,defaultPrevented:false};
  ui.documentEvents.get('click')(event);event.defaultPrevented=true;await Promise.resolve();assert.equal(ui.timers.size,0);
});

test('forms mark the actual submitter busy and restore it after returning',async()=>{
  const ui=setup(),first=new Element('Suggest with AI'),submitter=new Element('Create project'),form=new Form(first);
  await ui.submit(form,submitter);
  assert.equal(submitter.disabled,true);assert.equal(first.disabled,false);
  ui.windowEvents.get('pageshow')({persisted:false});
  assert.equal(submitter.innerHTML,'Create project');assert.equal(submitter.disabled,false);
});

test('async forms cancelled by their handlers never start the route loader',async()=>{
  const ui=setup(),button=new Element('Save'),event={target:new Form(button),submitter:button,defaultPrevented:false};
  ui.documentEvents.get('submit')(event);event.defaultPrevented=true;await Promise.resolve();
  assert.equal(button.disabled,false);assert.equal(ui.timers.size,0);
});

test('forms targeting another window do not get stuck busy',async()=>{
  const ui=setup(),button=new Element('Preview'),form=new Form(button);form.setAttribute('target','preview');
  await ui.submit(form,button);assert.equal(button.disabled,false);assert.equal(ui.timers.size,0);
});

test('cancelled navigation, offline transitions and browser errors release loading state',async()=>{
  for(const trigger of [ui=>ui.documentEvents.get('keydown')({key:'Escape'}),ui=>ui.windowEvents.get('offline')(),ui=>ui.navigationEvents.get('navigateerror')()]){
    const ui=setup(),button=new Element('Save');await ui.submit(new Form(button),button);trigger(ui);
    assert.equal(button.disabled,false);assert.equal(ui.status.getAttribute('aria-hidden'),'true');assert.equal(ui.timers.size,0);
  }
});

test('fallback hides a stranded route toast without enabling a pending POST twice',async()=>{
  const ui=setup(),button=new Element('Pay');await ui.submit(new Form(button),button);ui.advance(15000);
  assert.equal(ui.status.getAttribute('aria-hidden'),'true');assert.equal(ui.body.classList.contains('is-navigating'),false);
  assert.equal(button.disabled,true);
  ui.windowEvents.get('pageshow')({persisted:false});assert.equal(button.disabled,false);
});

test('button completion restores markup and its previous disabled state',()=>{
  for(const disabled of [false,true]){
    const ui=setup(),button=new Element('<b>Save</b>');button.disabled=disabled;
    ui.setButtonBusy(button,true);ui.setButtonBusy(button,false);
    assert.equal(button.innerHTML,'<b>Save</b>');assert.equal(button.disabled,disabled);assert.equal(button.hasAttribute('aria-busy'),false);
  }
});

test('success and selection labels are preserved when busy state ends',()=>{
  const ui=setup(),button=new Element('Select clip');ui.setButtonBusy(button,true);button.textContent='Selected';ui.setButtonBusy(button,false);
  assert.equal(button.textContent,'Selected');assert.equal(button.classList.contains('is-loading'),false);
});

test('repeated busy updates restore the original label once',()=>{
  const ui=setup(),button=new Element('Save');ui.setButtonBusy(button,true,'Starting');ui.setButtonBusy(button,true,'Finishing');ui.setButtonBusy(button,false);
  assert.equal(button.textContent,'Save');assert.equal(button.disabled,false);
});

test('browser back/forward cache restores unfinished button indicators',()=>{
  const ui=setup(),button=new Element('Suggest');ui.setButtonBusy(button,true);ui.windowEvents.get('pageshow')({persisted:true});
  assert.equal(button.disabled,false);assert.equal(button.textContent,'Suggest');
});

test('network failures always release request timeout timers',async()=>{
  const ui=setup(async()=>{throw new Error('Offline');});
  await assert.rejects(ui.fetchWithTimeout('/api/'),/Offline/);assert.equal(ui.timers.size,0);
});

test('timed-out actions abort and can restore their button in finally',async()=>{
  const ui=setup((url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('Aborted')))));
  const button=new Element('Suggest');ui.setButtonBusy(button,true);
  const request=ui.fetchWithTimeout('/api/',{},20).finally(()=>ui.setButtonBusy(button,false));
  ui.advance(20);await assert.rejects(request,/took too long/);
  assert.equal(button.disabled,false);assert.equal(button.textContent,'Suggest');assert.equal(ui.timers.size,0);
});

test('attachment export links declare download behavior and shared loading code loads first',()=>{
  const order=fs.readFileSync(path.join(__dirname,'../templates/orders/detail.html'),'utf8');
  const exports=[...order.matchAll(/<a\b[^>]*download-exports\/[^>]*>/g)];
  assert.equal(exports.length,2);for(const [tag] of exports)assert.match(tag,/\sdownload(?:\s|>)/);
  const music=fs.readFileSync(path.join(__dirname,'../templates/music/detail.html'),'utf8');
  assert.equal([...music.matchAll(/download data-no-transition>Download/g)].length,2);
  const base=fs.readFileSync(path.join(__dirname,'../templates/base.html'),'utf8');
  assert.ok(base.indexOf('js/loading.js')<base.indexOf('js/app.js'));
});
