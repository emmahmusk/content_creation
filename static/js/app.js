const routeStatus=document.querySelector('.route-status');
let routeStatusTimer;
const beginRouteTransition=(label='Opening next view…')=>{clearTimeout(routeStatusTimer);document.body.classList.add('is-navigating');if(routeStatus){routeStatus.querySelector('b').textContent=label;routeStatus.setAttribute('aria-hidden','true');routeStatusTimer=setTimeout(()=>{if(document.body.classList.contains('is-navigating'))routeStatus.setAttribute('aria-hidden','false');},180);}};
const endRouteTransition=()=>{clearTimeout(routeStatusTimer);document.body.classList.remove('is-navigating');routeStatus?.setAttribute('aria-hidden','true');};
const setButtonBusy=(button,busy,label='Working…')=>{
  if(!button)return;
  if(busy){
    if(!button.hasAttribute('data-original-content'))button.dataset.originalContent=button.innerHTML;
    button.classList.add('is-loading');
    button.replaceChildren();
    const state=document.createElement('span');state.className='button-busy-state';
    const copy=document.createElement('span');copy.className='button-busy-label';copy.textContent=label;
    const spinner=document.createElement('span');spinner.className='button-busy-spinner';spinner.setAttribute('aria-hidden','true');
    state.append(copy,spinner);button.append(state);
    button.disabled=true;button.setAttribute('aria-busy','true');
  }else{
    button.classList.remove('is-loading');
    if(button.hasAttribute('data-original-content')){button.innerHTML=button.dataset.originalContent;delete button.dataset.originalContent;}
    button.removeAttribute('aria-busy');
  }
};

document.querySelectorAll('[data-brief-suggest]').forEach(toolbar=>{
  const button=toolbar.querySelector('[data-brief-suggest-button]');
  const status=toolbar.querySelector('[data-brief-suggest-status]');
  const replaceExisting=toolbar.querySelector('[data-brief-replace]');
  const form=toolbar.closest('form');
  if(!button||!status||!form)return;
  button.addEventListener('click',async()=>{
    status.textContent='';
    const field=name=>form.querySelector(`[name="${name}"]`);
    const values={
      title:field('title')?.value.trim()||'',
      content_brief:field('content_brief')?.value.trim()||'',
      importance_definition:field('importance_definition')?.value.trim()||'',
      moments_to_avoid:field('moments_to_avoid')?.value.trim()||'',
      brand_voice:field('brand_voice')?.value.trim()||'',
      external_url:field('external_url')?.value.trim()||'',
      rights_confirmed:field('rights_confirmed')?.checked===true,
      source_name:form.querySelector('[name="file"]')?.files?.[0]?.name||''
    };
    const fields=['title','content_brief','importance_definition','moments_to_avoid','brand_voice'].map(field);
    if(!replaceExisting?.checked&&fields.every(target=>target?.value.trim())){
      status.textContent='All fields already have text. Clear a field or choose “Replace text already entered” to get a fresh draft.';
      return;
    }
    setButtonBusy(button,true,values.external_url?'Reading video details…':'Drafting your brief…');
    try{
      const csrf=form.querySelector('[name="csrfmiddlewaretoken"]')?.value||'';
      const response=await fetch(toolbar.dataset.suggestUrl,{
        method:'POST',
        headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRFToken':csrf},
        body:JSON.stringify(values)
      });
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||'Suggestions are unavailable right now.');
      let filled=0,kept=0;
      Object.entries(data.suggestions||{}).forEach(([name,value])=>{
        if(!['title','content_brief','importance_definition','moments_to_avoid','brand_voice'].includes(name))return;
        const target=field(name);
        if(!target||!String(value||'').trim())return;
        if(target.value.trim()&&!replaceExisting?.checked){kept++;return;}
        target.value=String(value).trim();
        target.dispatchEvent(new Event('input',{bubbles:true}));
        filled++;
      });
      if(filled&&replaceExisting?.checked){
        status.textContent='Fresh suggestions added. Edit any field to make the brief yours.';
      }else if(filled){
        const keptNote=kept?` ${kept} field${kept===1?' was':'s were'} left unchanged.`:'';
        status.textContent=`Draft added to ${filled} empty field${filled===1?'':'s'}. Edit any suggestion to make it yours.${keptNote}`;
      }else status.textContent='Your fields already have text, so nothing was replaced. Clear a field to add a fresh suggestion there.';
      if(filled&&data.based_on==='youtube_metadata')status.textContent+=' Based on video details; full analysis starts after you create the project.';
    }catch(error){status.textContent=error.message||'We could not create suggestions. Please try again.';}
    finally{setButtonBusy(button,false);button.disabled=false;}
  });
});

window.addEventListener('pageshow',endRouteTransition);
document.addEventListener('click',event=>{const link=event.target.closest('a[href]');if(!link||event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey||link.target==='_blank'||link.hasAttribute('download')||link.dataset.noTransition!==undefined)return;let target;try{target=new URL(link.href,location.href);}catch(error){return;}if(target.origin!==location.origin)return;const sameDocument=target.pathname===location.pathname&&target.search===location.search;if(sameDocument&&(!target.hash||target.hash===location.hash||document.querySelector(target.hash)))return;beginRouteTransition(link.dataset.loadingText||'Opening next view…');});
document.addEventListener('submit',event=>{if(event.defaultPrevented)return;const form=event.target;if(!(form instanceof HTMLFormElement)||form.dataset.noTransition!==undefined)return;const button=form.querySelector('button:not([type]),button[type="submit"],input[type="submit"]');const label=button?.dataset.loadingText||'Saving and opening the next step…';setButtonBusy(button,true,label);beginRouteTransition(label);});

(()=>{
  const values=[...document.querySelectorAll('[data-credit-value]')];
  const buttons=[...document.querySelectorAll('[data-credit-visibility]')];
  if(!values.length)return;
  let hidden=localStorage.getItem('kraftaa-credit-balance-hidden')==='true';
  const draw=()=>{
    values.forEach(value=>{
      const amount=Number(value.dataset.balance||0);
      value.textContent=hidden?'••••':new Intl.NumberFormat('en-US').format(amount);
    });
    buttons.forEach(button=>{
      button.setAttribute('aria-pressed',String(hidden));
      button.setAttribute('aria-label',hidden?'Show clip balance':'Hide clip balance');
      button.title=hidden?'Show balance':'Hide balance';
      const label=button.querySelector('[data-credit-toggle-label]');
      if(label)label.textContent=hidden?'Show balance':'Hide balance';
    });
  };
  draw();
  buttons.forEach(button=>button.addEventListener('click',()=>{
    hidden=!hidden;
    localStorage.setItem('kraftaa-credit-balance-hidden',String(hidden));
    draw();
  }));
})();

document.querySelectorAll('.copy-button').forEach(button=>button.addEventListener('click',async()=>{await navigator.clipboard.writeText(button.dataset.copy);const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1600)}));
const navToggle=document.querySelector('.nav-toggle');navToggle?.addEventListener('click',()=>{const open=document.body.classList.toggle('nav-open');navToggle.setAttribute('aria-expanded',String(open));navToggle.setAttribute('aria-label',open?'Close menu':'Open menu');});
document.querySelectorAll('.nav-links a').forEach(link=>link.addEventListener('click',()=>{document.body.classList.remove('nav-open');navToggle?.setAttribute('aria-expanded','false');}));
const siteHeader=document.querySelector('.site-header');
const updatePremiumChrome=()=>{siteHeader?.classList.toggle('is-scrolled',window.scrollY>12);const height=Math.max(1,document.documentElement.scrollHeight-window.innerHeight);document.body.style.setProperty('--page-progress',Math.min(1,window.scrollY/height));};
updatePremiumChrome();window.addEventListener('scroll',updatePremiumChrome,{passive:true});
const activeProductPath=location.pathname.startsWith('/orders/')||location.pathname.startsWith('/intelligence/')?'/orders/':location.pathname.startsWith('/music/')?'/music/':location.pathname.startsWith('/accounts/profile/')?'/accounts/profile/':location.pathname;
document.querySelectorAll('.nav-links>a[href]').forEach(link=>{try{if(new URL(link.href,location.href).pathname===activeProductPath)link.setAttribute('aria-current','page');}catch(error){}});

const premiumRevealTargets=document.querySelectorAll('.workspace-stats,.workspace-section-head,.order-row,.creation-step,.studio-pipeline,.studio-summary,.clip-card,.connections-masthead,.connection-compose,.destinations-head,.destination-list>*,.music-hero,.music-workspace,.intel-header,.intel-source,.editorial-section,.platform-section .section-intro,.feature-bento>*,.workflow-section .section-intro,.workflow-line>*,.outcome-quote,.outcome-grid>*');
if(premiumRevealTargets.length&&'IntersectionObserver' in window&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
  document.body.classList.add('premium-motion');premiumRevealTargets.forEach(target=>target.setAttribute('data-premium-reveal',''));
  const premiumObserver=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('is-visible');premiumObserver.unobserve(entry.target);}}),{threshold:.08,rootMargin:'0px 0px -4%'});
  premiumRevealTargets.forEach(target=>premiumObserver.observe(target));
}

document.querySelectorAll('.upload-zone input[type="file"]').forEach(input=>{
  const zone=input.closest('.upload-zone'),label=zone?.querySelector(`label[for="${input.id}"]`);
  const syncUploadLabel=()=>{const file=input.files?.[0];if(label)label.textContent=file?.name||'Choose a recording';zone?.classList.toggle('is-selected',Boolean(file));};
  input.addEventListener('change',syncUploadLabel);syncUploadLabel();
});
document.querySelectorAll('[data-source-recovery-form]').forEach(form=>{
  const input=form.querySelector('[data-source-recovery-file]');
  const name=form.querySelector('[data-source-recovery-name]');
  const button=form.querySelector('button[type="submit"]');
  input?.addEventListener('change',()=>{
    const file=input.files?.[0];
    if(name)name.textContent=file?.name||'MP4, MOV, WebM, MP3, WAV or M4A';
    if(button)button.disabled=!file;
    form.classList.toggle('has-file',Boolean(file));
  });
});
const themeControl=document.querySelector('.theme-control'),themeTrigger=document.querySelector('.theme-trigger'),themeChoices=[...document.querySelectorAll('[data-theme-choice]')],colorQuery=window.matchMedia('(prefers-color-scheme: dark)');
const paletteChoices=[...document.querySelectorAll('[data-palette-choice]')],paletteName=document.querySelector('.palette-name');
const applyTheme=(theme,persist=true)=>{const selected=['system','light','dark'].includes(theme)?theme:'system',dark=selected==='dark'||(selected==='system'&&colorQuery.matches);document.documentElement.dataset.theme=selected;document.documentElement.dataset.colorMode=dark?'dark':'light';document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#0b0d0c':'#fbfcf8');themeChoices.forEach(choice=>choice.setAttribute('aria-checked',String(choice.dataset.themeChoice===selected)));if(persist)localStorage.setItem('recast-theme',selected)};
applyTheme(localStorage.getItem('recast-theme')||'light',false);
const applyPalette=(palette,persist=true)=>{const selected=['cobalt','copper','teal','mono'].includes(palette)?palette:'teal';document.documentElement.dataset.palette=selected;paletteChoices.forEach(choice=>choice.setAttribute('aria-checked',String(choice.dataset.paletteChoice===selected)));if(paletteName)paletteName.textContent=selected[0].toUpperCase()+selected.slice(1);if(persist)localStorage.setItem('recast-palette',selected)};applyPalette(localStorage.getItem('recast-palette')||'teal',false);
themeTrigger?.addEventListener('click',event=>{event.stopPropagation();const open=themeControl.classList.toggle('is-open');themeTrigger.setAttribute('aria-expanded',String(open));if(open)themeChoices.find(item=>item.getAttribute('aria-checked')==='true')?.focus()});
themeChoices.forEach(choice=>choice.addEventListener('click',()=>{applyTheme(choice.dataset.themeChoice);themeControl.classList.remove('is-open');themeTrigger?.setAttribute('aria-expanded','false');themeTrigger?.focus()}));
paletteChoices.forEach(choice=>choice.addEventListener('click',event=>{event.stopPropagation();applyPalette(choice.dataset.paletteChoice)}));
document.addEventListener('click',event=>{if(!themeControl?.contains(event.target)){themeControl?.classList.remove('is-open');themeTrigger?.setAttribute('aria-expanded','false')}});document.addEventListener('keydown',event=>{if(event.key==='Escape'&&themeControl?.classList.contains('is-open')){themeControl.classList.remove('is-open');themeTrigger?.setAttribute('aria-expanded','false');themeTrigger?.focus()}});colorQuery.addEventListener?.('change',()=>{if((localStorage.getItem('recast-theme')||'light')==='system')applyTheme('system',false)});
const message=document.querySelector('.message');if(message)setTimeout(()=>message.remove(),4500);

document.querySelectorAll('input[type="password"]').forEach(input=>{
  if(input.closest('.password-input'))return;
  const wrapper=document.createElement('div');wrapper.className='password-input';
  input.parentNode.insertBefore(wrapper,input);wrapper.appendChild(input);
  const toggle=document.createElement('button');toggle.type='button';toggle.className='password-toggle';toggle.setAttribute('aria-label','Show password');toggle.setAttribute('aria-pressed','false');toggle.title='Show password';
  toggle.innerHTML='<svg class="password-eye password-eye-open" viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.75"/></svg><svg class="password-eye password-eye-closed" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 4.2A10.8 10.8 0 0 1 12 4c6 0 9.5 6 9.5 6a17 17 0 0 1-2.1 2.8M6.2 6.2C3.8 7.8 2.5 10 2.5 10s3.5 6 9.5 6a10.7 10.7 0 0 0 3-.4"/></svg>';
  wrapper.appendChild(toggle);
  toggle.addEventListener('click',()=>{
    const visible=input.type==='text';input.type=visible?'password':'text';
    const label=visible?'Show password':'Hide password';toggle.setAttribute('aria-pressed',String(!visible));toggle.setAttribute('aria-label',label);toggle.title=label;input.focus({preventScroll:true});
  });
});

const socialRegistration=document.querySelector('[data-social-registration]');
if(socialRegistration){
  const prefix=socialRegistration.dataset.prefix||'social';
  const list=socialRegistration.querySelector('[data-social-list]');
  const template=socialRegistration.querySelector('[data-social-template]');
  const addButton=socialRegistration.querySelector('[data-social-add]');
  const countLabel=socialRegistration.querySelector('[data-social-count]');
  const totalInput=socialRegistration.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
  const maxProfiles=Number(socialRegistration.dataset.maxProfiles||7);
  const activeRows=()=>[...list.querySelectorAll('[data-social-row]')].filter(row=>!row.classList.contains('is-deleted'));
  const updateRows=()=>{
    const rows=activeRows();
    const selected=rows.map(row=>row.querySelector('select')?.value).filter(Boolean);
    rows.forEach((row,index)=>{
      const select=row.querySelector('select');
      select?.querySelectorAll('option').forEach(option=>{option.disabled=Boolean(option.value&&option.value!==select.value&&selected.includes(option.value));});
      const remove=row.querySelector('[data-social-remove]');
      if(remove){remove.hidden=rows.length===1;remove.setAttribute('aria-label',`Remove social profile ${index+1}`);}
    });
    countLabel.textContent=`${rows.length} of ${maxProfiles}`;
    addButton.disabled=rows.length>=maxProfiles;
  };
  const bindRow=row=>{
    row.querySelector('select')?.addEventListener('change',updateRows);
    row.querySelector('[data-social-remove]')?.addEventListener('click',()=>{
      const rows=activeRows();
      if(rows.length===1){
        row.querySelector('select').value='';row.querySelector('input[type="text"]').value='';updateRows();return;
      }
      const deletion=row.querySelector(`input[name$="-DELETE"]`);if(deletion)deletion.value='on';
      row.classList.add('is-deleted');row.hidden=true;updateRows();
    });
  };
  activeRows().forEach(bindRow);
  addButton.addEventListener('click',()=>{
    if(activeRows().length>=maxProfiles)return;
    const index=Number(totalInput.value);
    const container=document.createElement('div');container.innerHTML=template.innerHTML.replaceAll('__prefix__',String(index)).trim();
    const row=container.firstElementChild;list.appendChild(row);totalInput.value=String(index+1);bindRow(row);updateRows();row.querySelector('select')?.focus();
  });
  updateRows();
}

const pipeline=document.querySelector('.pipeline-card');
if(pipeline){
  const analyzeButton=pipeline.querySelector('.pipeline-start');
  const renderButton=pipeline.querySelector('.pipeline-render');
  const errorBox=pipeline.querySelector('.pipeline-error');
  const connectionBox=pipeline.querySelector('.pipeline-connection');
  const companion=pipeline.querySelector('[data-pipeline-companion]');
  const youtubeAuthPrompt=pipeline.querySelector('[data-youtube-auth-prompt]');
  const companionKicker=companion?.querySelector('[data-companion-kicker]');
  const companionMessage=companion?.querySelector('[data-pipeline-message]');
  const companionDetail=companion?.querySelector('[data-pipeline-detail]');
  const pipelineHelp=pipeline.querySelector('.pipeline-help');
  const pipelineErrorText=errorBox?.querySelector('[data-pipeline-error-text]');
  const pipelineCreditLink=errorBox?.querySelector('[data-pipeline-credit-link]');
  pipelineCreditLink?.classList.toggle('hidden',!(/available balance|clipping credit/i.test(pipelineErrorText?.textContent||'')));
  let progressFailures=0;
  let companionIndex=0;
  let companionStage='';
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const humanize=value=>(value||'processing').replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
  const companionStories={
    ingest:[
      ['YOUR SOURCE IS CHECKING IN','Bringing every frame into the kitchen.','You can leave this page while we prepare the recording. Your progress is saved.'],
      ['BACKGROUND MODE: ON','Go make coffee. We’ve got the timeline.','Closing this tab won’t stop the work. Kraftaa will keep moving behind the scenes.']
    ],
    transcribe:[
      ['LISTENING BETWEEN THE LINES','Turning every word into a useful map.','Take a call, answer a message, or get back to your day. We’ll keep listening.'],
      ['SAFE TO STEP AWAY','Your recording is talking. We’re taking notes.','You can close this tab and return whenever you’re ready. Nothing here loses its place.']
    ],
    strategy:[
      ['MOMENT RADAR: ACTIVE','Finding the parts people will replay.','Your brief is directing the search while Kraftaa ranks hooks, clarity, and audience fit.'],
      ['YOUR BRIEF IS DIRECTING','Ideas are becoming an approval queue.','Go chase another idea. We’ll keep sorting signal from filler in the background.'],
      ['NO NEED TO BABYSIT THIS','We’re shaping ten small sparks from one big conversation.','Close the tab or head back to your workspace. Your analysis will keep cooking.']
    ],
    render:[
      ['THE EDIT SUITE IS MOVING','Your exports are cooking.','Frames, captions, audio, and thumbnails are being prepared for your approved moments.'],
      ['BACKGROUND MODE: ON','Go stretch, take a call, or chase another idea.','You can close this tab. Kraftaa will keep rendering, and your progress is safely saved.'],
      ['POLISH IN PROGRESS','Everything is lining up for publish.','Come back whenever you like. We’re handling the repetitive bits behind the scenes.']
    ],
    broll:[
      ['VISUAL STORYBOARD: ACTIVE','Building cutaways for the clips you approved.','The AI is matching each spoken beat with useful visual context. Nothing unapproved is being generated.'],
      ['B-ROLL IS COOKING','Your approved clips are getting visual rhythm.','You can close this tab. Kraftaa will keep sourcing and generating in the background.']
    ],
    package:[
      ['PACKAGING THE GOOD STUFF','Your content system is almost ready.','We’re gathering every finished asset into one calm, downloadable workspace.'],
      ['LAST DETAILS, THEN LIFTOFF','The heavy lifting is nearly done.','Feel free to step away. We’ll keep the lights on until every export is in place.']
    ]
  };
  const companionKey=stage=>({audio:'ingest',starting:'ingest',transcribe:'transcribe',strategy:'strategy',recommendations_ready:'strategy',awaiting_approval:'strategy',broll:'broll',rendering_exports:'render',render:'render',quality_review:'package',package:'package'}[stage]||'strategy');
  const updateCompanion=(status,stage,rotate=false)=>{
    if(!companion)return;
    const active=status==='running';
    companion.classList.toggle('hidden',!active);
    if(!active)return;
    const key=companionKey(stage);
    if(companionStage!==key){companionStage=key;companionIndex=0;}else if(rotate){companionIndex=(companionIndex+1)%companionStories[key].length;}
    const [kicker,message,detail]=companionStories[key][companionIndex];
    companion.classList.remove('is-changing');
    void companion.offsetWidth;
    companion.classList.add('is-changing');
    companionKicker.textContent=kicker;
    companionMessage.textContent=message;
    companionDetail.textContent=detail;
    if(pipelineHelp&&key==='broll')pipelineHelp.textContent='Your choices are locked in. AI B-roll is being created only for the approved clips.';
    if(pipelineHelp&&key==='render')pipelineHelp.textContent='Your choices are locked in. We’re applying captions, hooks, reframing and export polish now.';
  };
  const updateStages=data=>{
    const stages=[...pipeline.querySelectorAll('.stage-track li')];
    if(!stages.length)return;
    const stageIndex={starting:0,ingest:0,audio:0,transcribe:1,strategy:1,recommendations_ready:2,awaiting_approval:2,broll:3,rendering_exports:4,render:4,quality_review:5,package:5}[data.current_stage];
    stages.forEach((stage,index)=>{
      stage.classList.toggle('is-complete',Number.isInteger(stageIndex)&&index<stageIndex);
      stage.classList.toggle('is-active',data.status==='running'&&index===stageIndex);
    });
  };
  const render=data=>{
    progressFailures=0;
    connectionBox?.classList.add('hidden');
    pipeline.dataset.status=data.status;
    pipeline.dataset.stage=data.current_stage||data.status;
    pipeline.querySelector('.pipeline-percent').textContent=`${data.progress}%`;
    pipeline.querySelector('.pipeline-status').textContent=humanize(data.status);
    pipeline.querySelector('.pipeline-stage').textContent=humanize(data.current_stage||data.status);
    pipeline.querySelector('.progress-track i').style.width=`${data.progress}%`;
    if(pipelineErrorText)pipelineErrorText.textContent=data.error||'';
    pipelineCreditLink?.classList.toggle('hidden',!(/available balance|clipping credit/i.test(data.error||'')));
    errorBox.classList.toggle('hidden',!data.error);
    if(youtubeAuthPrompt){
      const prompt=data.youtube_auth_prompt;
      youtubeAuthPrompt.classList.toggle('hidden',!prompt||data.status!=='running');
      if(prompt){
        const link=youtubeAuthPrompt.querySelector('[data-youtube-auth-link]');
        link.href=prompt.verification_url;
        youtubeAuthPrompt.querySelector('[data-youtube-auth-code]').textContent=prompt.user_code;
      }
    }
    updateStages(data);
    updateCompanion(data.status,data.current_stage||data.status);
  };
  const refresh=async()=>{
    try{
      const response=await fetch(pipeline.dataset.pipelineUrl,{headers:{Accept:'application/json'}});
      if(response.status===401||response.status===403){if(connectionBox){connectionBox.querySelector('span').textContent='Your session expired. Refresh this page to continue.';connectionBox.classList.remove('hidden');}return;}
      if(response.status===404){if(connectionBox){connectionBox.querySelector('span').textContent='This run changed. Refreshing the project…';connectionBox.classList.remove('hidden');}setTimeout(()=>location.reload(),1200);return;}
      if(!response.ok)throw new Error('Progress temporarily unavailable.');
      const data=await response.json();render(data);
      if(['queued','running'].includes(data.status)){setTimeout(refresh,2000);return;}
      if(data.status==='failed'){
        if(/youtube could not verify this server|sign in to confirm (?:you’re|you're) not a bot/i.test(data.error||'')){
          location.reload();
          return;
        }
        const activeButton=renderButton||analyzeButton;
        if(activeButton){setButtonBusy(activeButton,false);activeButton.disabled=false;activeButton.textContent='Try again';}
        return;
      }
      location.reload();
    }catch(error){
      progressFailures+=1;
      if(progressFailures>=2&&connectionBox){connectionBox.querySelector('span').textContent='Live updates paused. Reconnecting automatically…';connectionBox.classList.remove('hidden');}
      setTimeout(refresh,Math.min(8000,1500*progressFailures));
    }
  };
  const start=async(button,url,busyLabel)=>{
    setButtonBusy(button,true,busyLabel);errorBox.classList.add('hidden');
    try{
      const response=await fetch(url,{method:'POST',headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json'}});
      const data=await response.json();
      if(!response.ok){if(pipelineErrorText)pipelineErrorText.textContent=data.detail||'Could not start this job.';pipelineCreditLink?.classList.toggle('hidden',response.status!==402);errorBox.classList.remove('hidden');throw new Error(data.detail||'Could not start this job.');}
      render(data);setTimeout(refresh,1000);
    }catch(error){if(pipelineErrorText)pipelineErrorText.textContent=error.message;errorBox.classList.remove('hidden');setButtonBusy(button,false);button.disabled=false;button.textContent='Try again';}
  };
  analyzeButton?.addEventListener('click',()=>start(analyzeButton,pipeline.dataset.startUrl,'Finding moments…'));
  renderButton?.addEventListener('click',()=>start(renderButton,pipeline.dataset.renderUrl,'Creating clips…'));
  youtubeAuthPrompt?.querySelector('[data-youtube-auth-confirm]')?.addEventListener('click',async event=>{
    const button=event.currentTarget;const note=youtubeAuthPrompt.querySelector('[data-youtube-auth-message]');
    setButtonBusy(button,true,'Confirming…');note.textContent='Checking with YouTube…';
    try{
      const response=await fetch(youtubeAuthPrompt.dataset.confirmUrl,{method:'POST',headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json'}});
      const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not confirm the sign-in yet.');
      note.textContent='Approved. The video import is resuming.';youtubeAuthPrompt.classList.add('is-approved');
    }catch(error){note.textContent=error.message;button.disabled=false;setButtonBusy(button,false);}
  });
  updateStages({status:pipeline.dataset.status,current_stage:pipeline.dataset.stage});
  updateCompanion(pipeline.dataset.status,pipeline.dataset.stage);
  setInterval(()=>updateCompanion(pipeline.dataset.status,pipeline.dataset.stage,true),7200);
  if(pipeline.dataset.status==='running')setTimeout(refresh,500);
}

const musicFile=document.querySelector('.music-file-field input[type="file"]');
musicFile?.addEventListener('change',()=>{const label=document.querySelector('[data-file-name]');if(label)label.textContent=musicFile.files?.[0]?.name||'Choose an audio file';});
const studioProgress=document.querySelector('[data-studio-progress]');
if(studioProgress){
  const pollStudio=async()=>{try{const response=await fetch(studioProgress.dataset.url,{headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json();studioProgress.querySelector('[data-progress-bar]').style.width=`${data.progress}%`;studioProgress.querySelector('[data-progress-label]').textContent=`${data.progress}%`;studioProgress.querySelector('[data-stage-label]').textContent=data.stage_label;if(['direction','review','failed'].includes(data.status)){window.location.reload();return;}}catch(error){}setTimeout(pollStudio,1800);};
  setTimeout(pollStudio,1200);
}

document.querySelectorAll('.clip-decision').forEach(button=>button.addEventListener('click',async()=>{
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const card=button.closest('.clip-card');
  card.querySelectorAll('.clip-decision').forEach(item=>item.disabled=true);
  setButtonBusy(button,true,'Saving choice…');
  try{
    const response=await fetch(button.dataset.url,{method:'POST',headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json'}});
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not update this clip.');
    const stateLabel=data.status==='approved'?'Selected':data.status==='rejected'?'Skipped':data.status.charAt(0).toUpperCase()+data.status.slice(1);
    const stateOutput=card.querySelector('.clip-state');if(stateOutput)stateOutput.textContent=stateLabel;
    const stateMeta=card.querySelector('.clip-state-meta');if(stateMeta)stateMeta.textContent=stateLabel;
    card.querySelectorAll('.clip-decision').forEach(item=>{const selected=item.dataset.state===data.status;item.classList.toggle('primary',selected);item.setAttribute('aria-pressed',String(selected));item.textContent=item.dataset.state==='approved'?(selected?'Selected':'Select clip'):(selected?'Skipped':'Skip clip');});
    const approved=document.querySelectorAll('.clip-decision.primary[data-state="approved"]').length;
    document.querySelector('.approved-count').textContent=approved;
    const renderButton=document.querySelector('.pipeline-render');
    if(renderButton){renderButton.disabled=approved===0;renderButton.dataset.approvedCount=approved;renderButton.textContent=`Create ${approved} selected clip${approved===1?'':'s'}`;}
  }catch(error){alert(error.message);}
  finally{setButtonBusy(button,false);card.querySelectorAll('.clip-decision').forEach(item=>item.disabled=false);}
}));

const socialManager=document.querySelector('.connection-workspace[data-api-url],.social-manager[data-api-url]');
if(socialManager){
  const form=socialManager.querySelector('.social-handle-form'),list=socialManager.querySelector('.social-handle-list'),errorBox=socialManager.querySelector('.social-form-error');
  const iconSprite=socialManager.dataset.iconSprite||'/static/images/social-platforms.svg',connectedCount=document.querySelector('.destinations-head>p');
  const platformSelect=form?.querySelector('select[name="platform"]');
  if(platformSelect){
    const field=platformSelect.closest('div'),trigger=document.createElement('button'),menu=document.createElement('div');
    const fieldLabel=field?.querySelector('label');if(fieldLabel&&!fieldLabel.id)fieldLabel.id='social-platform-label';
    const iconFor=value=>{if(!value)return null;const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),use=document.createElementNS('http://www.w3.org/2000/svg','use');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('platform-icon');use.setAttribute('href',`${iconSprite}#${value}`);svg.append(use);return svg;};
    const selectedOption=()=>platformSelect.options[platformSelect.selectedIndex];
    const wrapper=document.createElement('div');wrapper.className='platform-select-control';
    trigger.type='button';trigger.className='platform-select-trigger';trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-required','true');trigger.setAttribute('aria-controls','social-platform-options');
    menu.id='social-platform-options';menu.className='platform-select-menu';menu.setAttribute('role','listbox');menu.setAttribute('aria-label','Social media platforms');menu.hidden=true;
    const refreshSelection=()=>{const option=selectedOption();trigger.replaceChildren();trigger.dataset.platform=option?.value||'';const label=option?.textContent.trim()||'Select platform';trigger.setAttribute('aria-label',`Platform: ${label}`);const icon=iconFor(option?.value);if(icon)trigger.append(icon);const text=document.createElement('span');text.textContent=label;trigger.append(text);menu.querySelectorAll('[role="option"]').forEach(item=>item.setAttribute('aria-selected',String(item.dataset.value===platformSelect.value)));};
    [...platformSelect.options].forEach(option=>{const item=document.createElement('button');item.type='button';item.className='platform-select-option';item.setAttribute('role','option');item.dataset.value=option.value;item.dataset.platform=option.value;item.setAttribute('aria-selected','false');if(option.value)item.append(iconFor(option.value));const text=document.createElement('span');text.textContent=option.textContent.trim();item.append(text);item.tabIndex=-1;item.addEventListener('click',()=>{platformSelect.value=option.value;platformSelect.dispatchEvent(new Event('change',{bubbles:true}));refreshSelection();menu.hidden=true;trigger.setAttribute('aria-expanded','false');trigger.focus();});menu.append(item);});
    const openMenu=(focusCurrent=false)=>{menu.hidden=false;trigger.setAttribute('aria-expanded','true');if(focusCurrent){const current=menu.querySelector(`[data-value="${CSS.escape(platformSelect.value)}"]`)||menu.querySelector('[role="option"]');current?.focus();}};
    trigger.addEventListener('click',()=>menu.hidden?openMenu(true):(menu.hidden=true,trigger.setAttribute('aria-expanded','false')));
    trigger.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp','Enter',' '].includes(event.key)){event.preventDefault();openMenu(true);}});
    menu.addEventListener('keydown',event=>{const options=[...menu.querySelectorAll('[role="option"]')],index=options.indexOf(document.activeElement);let next=index;if(event.key==='ArrowDown')next=(index+1)%options.length;else if(event.key==='ArrowUp')next=(index-1+options.length)%options.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=options.length-1;else if(event.key==='Escape'){event.preventDefault();menu.hidden=true;trigger.setAttribute('aria-expanded','false');trigger.focus();return;}else if(event.key==='Tab'){menu.hidden=true;trigger.setAttribute('aria-expanded','false');return;}else return;event.preventDefault();options[next]?.focus();});
    document.addEventListener('click',event=>{if(!wrapper.contains(event.target)){menu.hidden=true;trigger.setAttribute('aria-expanded','false');}});
    platformSelect.classList.add('platform-native-select');platformSelect.removeAttribute('required');platformSelect.setAttribute('aria-hidden','true');platformSelect.tabIndex=-1;
    wrapper.append(trigger,menu);platformSelect.insertAdjacentElement('afterend',wrapper);refreshSelection();platformSelect.addEventListener('change',refreshSelection);form.addEventListener('reset',()=>setTimeout(refreshSelection,0));
    form.addEventListener('submit',event=>{if(!platformSelect.value){event.preventDefault();event.stopImmediatePropagation();trigger.focus();openMenu(true);errorBox.textContent='Choose a social platform to continue.';errorBox.classList.remove('hidden');}} ,true);
  }
  const syncConnectedCount=()=>{if(connectedCount){const total=list.querySelectorAll('article').length;connectedCount.textContent=`${total} connected`;}};
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const request=async(url,method,body)=>{const response=await fetch(url,{method,headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json','Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=response.status===204?{}:await response.json();if(!response.ok)throw new Error(data.detail||data.platform?.[0]||data.handle?.[0]||Object.values(data).flat().join(' ')||'Could not save this profile.');return data;};
  const showError=error=>{errorBox.textContent=error.message;errorBox.classList.remove('hidden');};
  const bind=row=>{
    row.querySelector('.social-update').addEventListener('click',async()=>{const button=row.querySelector('.social-update');setButtonBusy(button,true,'Saving…');try{await request(`${socialManager.dataset.apiUrl}${row.dataset.id}/`,'PATCH',{handle:row.querySelector('input').value});button.textContent='Saved';setTimeout(()=>button.textContent='Save changes',1200);}catch(error){showError(error);}finally{setButtonBusy(button,false);button.disabled=false;}});
    row.querySelector('.social-delete').addEventListener('click',async()=>{if(!confirm('Remove this social profile?'))return;const button=row.querySelector('.social-delete');setButtonBusy(button,true,'Removing…');try{await request(`${socialManager.dataset.apiUrl}${row.dataset.id}/`,'DELETE');row.remove();syncConnectedCount();if(!list.querySelector('article'))list.innerHTML='<div class="social-empty connection-empty"><div><h3>Your publishing network is waiting.</h3><p>Add one destination above. The rest can grow with you.</p></div><i>↗</i></div>';}catch(error){showError(error);setButtonBusy(button,false);button.disabled=false;}});
  };
  list.querySelectorAll('article').forEach(bind);
  form.addEventListener('submit',async event=>{event.preventDefault();errorBox.classList.add('hidden');const button=form.querySelector('button[type="submit"]');setButtonBusy(button,true,'Adding profile…');try{const data=await request(socialManager.dataset.apiUrl,'POST',{platform:form.platform.value,handle:form.handle.value});list.querySelector('.social-empty')?.remove();const row=document.createElement('article');row.classList.add('social-row-entering');row.dataset.id=data.id;row.dataset.platform=data.platform;row.innerHTML='<div class="platform-avatar"><svg class="platform-icon" viewBox="0 0 24 24" focusable="false" aria-hidden="true"><use></use></svg></div><div class="destination-name"><small>PLATFORM</small><strong></strong></div><input maxlength="160"><button class="download-chip social-update" type="button">Save changes</button><button class="download-chip social-delete" type="button">Remove</button>';row.querySelector('use').setAttribute('href',`${iconSprite}#${data.platform}`);row.querySelector('.destination-name strong').textContent=data.platform_label;const handleInput=row.querySelector('input');handleInput.value=data.handle;handleInput.setAttribute('aria-label',`${data.platform_label} handle`);list.appendChild(row);requestAnimationFrame(()=>requestAnimationFrame(()=>row.classList.remove('social-row-entering')));bind(row);syncConnectedCount();form.reset();}catch(error){showError(error);}finally{setButtonBusy(button,false);button.disabled=false;}});
  syncConnectedCount();
}

const intel=document.querySelector('.intel-shell');
if(intel){
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const api=async(url,method='GET',body)=>{const response=await fetch(url,{method,headers:{Accept:'application/json','Content-Type':'application/json','X-CSRFToken':decodeURIComponent(cookie('csrftoken'))},body:body?JSON.stringify(body):undefined});const data=response.status===204?{}:await response.json();if(!response.ok)throw new Error(data.detail||data.action?.[0]||Object.values(data).flat().join(' ')||'Request failed.');return data;};
  const poll=async()=>{try{const data=await api(intel.dataset.intelligenceUrl);if(data.status==='ready'||data.status==='failed'){location.reload();return;}setTimeout(poll,1800);}catch(error){document.querySelector('.intel-error').textContent=error.message;}};
  const start=async()=>{const button=document.querySelector('.intel-analyze');if(button)setButtonBusy(button,true,'Reviewing this clip…');try{await api(intel.dataset.startUrl,'POST');setTimeout(poll,1000);}catch(error){if(button){setButtonBusy(button,false);button.disabled=false;button.textContent='Try again';}document.querySelector('.intel-error').textContent=error.message;}};
  document.querySelector('.intel-analyze')?.addEventListener('click',start);
  if(intel.dataset.status==='queued')start();else if(intel.dataset.status==='running')poll();
  document.querySelectorAll('.intel-decision').forEach(button=>button.addEventListener('click',async()=>{
    const buttons=[...document.querySelectorAll('.intel-decision')],label=document.querySelector('.intel-decision-state');
    buttons.forEach(item=>item.disabled=true);
    setButtonBusy(button,true,'Saving choice…');
    try{
      const data=await api(button.dataset.url,'POST');
      buttons.forEach(item=>item.classList.toggle('is-active',item.dataset.state===data.status));
      if(label)label.textContent=data.status==='approved'?'Selected':data.status==='rejected'?'Skipped':data.status;
    }catch(error){alert(error.message);}
    finally{setButtonBusy(button,false);buttons.forEach(item=>item.disabled=false);}
  }));
  document.querySelectorAll('.repurpose-list article').forEach(asset=>{
    const textarea=asset.querySelector('textarea');
    asset.querySelector('.asset-copy')?.addEventListener('click',async event=>{await navigator.clipboard.writeText(textarea.value);event.currentTarget.textContent='Copied';setTimeout(()=>event.currentTarget.textContent='Copy',1200);});
    asset.querySelector('.asset-save')?.addEventListener('click',async event=>{const button=event.currentTarget;setButtonBusy(button,true,'Saving edits…');try{await api(`/api/v1/repurpose-assets/${asset.dataset.assetId}/`,'PATCH',{content:textarea.value});button.textContent='Saved';}catch(error){alert(error.message);}finally{setButtonBusy(button,false);button.disabled=false;setTimeout(()=>button.textContent='Save edits',1200);}});
    asset.querySelectorAll('footer button[data-operation]').forEach(button=>button.addEventListener('click',async()=>{const label={regenerate:'Regenerating…',improve:'Improving…',shorten:'Shortening…'}[button.dataset.operation]||'Working…';setButtonBusy(button,true,label);try{const data=await api(`/api/v1/repurpose-assets/${asset.dataset.assetId}/transform/`,'POST',{operation:button.dataset.operation});textarea.value=data.content;}catch(error){alert(error.message);}finally{setButtonBusy(button,false);button.disabled=false;}}));
  });
  document.querySelectorAll('.editor-accept').forEach(button=>button.addEventListener('click',async()=>{setButtonBusy(button,true,'Saving suggestion…');try{await api(`${intel.dataset.intelligenceUrl}accept-editor-recommendation/`,'POST',{action_id:button.dataset.actionId});button.textContent='Suggestion saved ✓';setButtonBusy(button,false);}catch(error){setButtonBusy(button,false);button.disabled=false;alert(error.message);}}));
  const publicationForm=document.querySelector('.publication-form');
  if(publicationForm){
    const actionField=publicationForm.querySelector('[name="action"]'),scheduleField=publicationForm.querySelector('[name="scheduled_for"]'),titleField=publicationForm.querySelector('[name="title"]'),captionField=publicationForm.querySelector('[name="caption"]');
    actionField.addEventListener('change',()=>publicationForm.querySelector('.schedule-field').classList.toggle('hidden',actionField.value!=='schedule'));
    publicationForm.addEventListener('submit',async event=>{event.preventDefault();const destinations=[...publicationForm.querySelectorAll('[name="destination"]:checked')],button=publicationForm.querySelector('button[type="submit"]');const result=publicationForm.querySelector('.publish-result');if(!destinations.length){result.textContent='Choose at least one social profile.';return;}setButtonBusy(button,true,'Saving publishing plan…');const clipId=Number(intel.dataset.startUrl.match(/clips\/(\d+)/)[1]);try{await Promise.all(destinations.map(destination=>api(intel.dataset.publicationUrl,'POST',{clip:clipId,social_handle:Number(destination.value),action:actionField.value,scheduled_for:scheduleField.value||null,platform_payload:{title:titleField.value,caption:captionField.value}})));result.textContent=`Publishing plan saved for ${destinations.length} profile${destinations.length===1?'':'s'}.`;result.className='publish-result success';}catch(error){result.textContent=error.message;result.className='publish-result error';}finally{setButtonBusy(button,false);button.disabled=false;}});
  }
}
