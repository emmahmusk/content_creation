/* Shared loading state. Downloads and in-page actions do not navigate away. */
const routeStatus=document.querySelector('.route-status');
const busyButtonStates=new Map();
let routeStatusTimer,routeFallbackTimer,routeSubmitter=null;

const setButtonBusy=(button,busy,label='Working…')=>{
  if(!button)return;
  if(busy){
    if(!busyButtonStates.has(button))busyButtonStates.set(button,{content:button.innerHTML,disabled:button.disabled});
    button.classList.add('is-loading');
    button.replaceChildren();
    const state=document.createElement('span');state.className='button-busy-state';
    const copy=document.createElement('span');copy.className='button-busy-label';copy.textContent=label;
    const spinner=document.createElement('span');spinner.className='button-busy-spinner';spinner.setAttribute('aria-hidden','true');
    state.append(copy,spinner);button.append(state);
    button.disabled=true;button.setAttribute('aria-busy','true');
  }else{
    const previous=busyButtonStates.get(button);
    button.classList.remove('is-loading');
    if(previous){
      // Preserve a success/selection label already written by the action handler.
      if(button.querySelector('.button-busy-state'))button.innerHTML=previous.content;
      button.disabled=previous.disabled;
      busyButtonStates.delete(button);
    }
    button.removeAttribute('aria-busy');
  }
};

const hideRouteIndicator=()=>{
  clearTimeout(routeStatusTimer);clearTimeout(routeFallbackTimer);
  document.body.classList.remove('is-navigating');
  routeStatus?.setAttribute('aria-hidden','true');
};
const endRouteTransition=()=>{
  hideRouteIndicator();
  if(routeSubmitter){setButtonBusy(routeSubmitter,false);routeSubmitter=null;}
};
const beginRouteTransition=(label='Opening next view…',submitter=null)=>{
  endRouteTransition();
  routeSubmitter=submitter;
  if(submitter)setButtonBusy(submitter,true,label);
  document.body.classList.add('is-navigating');
  if(routeStatus){
    routeStatus.querySelector('b').textContent=label;
    routeStatus.setAttribute('aria-hidden','true');
    routeStatusTimer=setTimeout(()=>{
      if(document.body.classList.contains('is-navigating'))routeStatus.setAttribute('aria-hidden','false');
    },180);
  }
  // A browser-cancelled navigation/attachment can leave the same document open.
  // Hide the global toast without enabling a potentially still-pending POST.
  routeFallbackTimer=setTimeout(hideRouteIndicator,15000);
};

const fetchWithTimeout=async(url,options={},timeout=120000)=>{
  const controller=new AbortController();
  let timedOut=false;
  const abort=()=>controller.abort();
  if(options.signal?.aborted)controller.abort();
  else options.signal?.addEventListener('abort',abort,{once:true});
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},timeout);
  try{return await fetch(url,{...options,signal:controller.signal});}
  catch(error){
    if(timedOut)throw new Error('This request took too long. Check the current status before trying again.');
    throw error;
  }finally{
    clearTimeout(timer);
    options.signal?.removeEventListener('abort',abort);
  }
};

const usesCurrentWindow=target=>!target||target.toLowerCase()==='_self';
window.addEventListener('pageshow',event=>{
  endRouteTransition();
  if(event.persisted)for(const button of busyButtonStates.keys())setButtonBusy(button,false);
});
window.addEventListener('pagehide',endRouteTransition);
window.addEventListener('popstate',endRouteTransition);
window.addEventListener('hashchange',endRouteTransition);
window.addEventListener('offline',endRouteTransition);
window.navigation?.addEventListener('navigateerror',endRouteTransition);
window.navigation?.addEventListener('navigatesuccess',endRouteTransition);
document.addEventListener('keydown',event=>{if(event.key==='Escape')endRouteTransition();});

document.addEventListener('click',event=>{
  const link=event.target.closest?.('a[href]');
  if(!link||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  // Wait until every handler has had a chance to cancel native navigation.
  queueMicrotask(()=>{
    if(event.defaultPrevented)return;
    const targetWindow=link.getAttribute('target')||document.querySelector('base[target]')?.getAttribute('target');
    if(!usesCurrentWindow(targetWindow)||link.hasAttribute('download')||link.dataset.noTransition!==undefined)return;
    let target;try{target=new URL(link.href,location.href);}catch(error){return;}
    if(!['http:','https:'].includes(target.protocol)||target.origin!==location.origin)return;
    if(target.pathname===location.pathname&&target.search===location.search){endRouteTransition();return;}
    beginRouteTransition(link.dataset.loadingText||'Opening next view…');
  });
});

document.addEventListener('submit',event=>{
  const form=event.target;
  if(!(form instanceof HTMLFormElement))return;
  queueMicrotask(()=>{
    if(event.defaultPrevented||form.dataset.noTransition!==undefined)return;
    const submitter=event.submitter;
    const target=submitter?.getAttribute('formtarget')||form.getAttribute('target')||document.querySelector('base[target]')?.getAttribute('target');
    const method=submitter?.getAttribute('formmethod')||form.method;
    if(!usesCurrentWindow(target)||method.toLowerCase()==='dialog')return;
    const action=submitter?.getAttribute('formaction')||form.action;
    let destination;try{destination=new URL(action,location.href);}catch(error){return;}
    if(destination.origin!==location.origin)return;
    const button=submitter||form.querySelector('button[type="submit"],button:not([type]),input[type="submit"]');
    beginRouteTransition(button?.dataset.loadingText||'Saving and opening the next step…',button);
  });
});
