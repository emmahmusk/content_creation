document.querySelectorAll('.copy-button').forEach(button=>button.addEventListener('click',async()=>{await navigator.clipboard.writeText(button.dataset.copy);const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1600)}));
const navToggle=document.querySelector('.nav-toggle');navToggle?.addEventListener('click',()=>{const open=document.body.classList.toggle('nav-open');navToggle.setAttribute('aria-expanded',String(open));navToggle.setAttribute('aria-label',open?'Close menu':'Open menu');});
document.querySelectorAll('.nav-links a').forEach(link=>link.addEventListener('click',()=>{document.body.classList.remove('nav-open');navToggle?.setAttribute('aria-expanded','false');}));
const themeControl=document.querySelector('.theme-control'),themeTrigger=document.querySelector('.theme-trigger'),themeChoices=[...document.querySelectorAll('[data-theme-choice]')],colorQuery=window.matchMedia('(prefers-color-scheme: dark)');
const paletteChoices=[...document.querySelectorAll('[data-palette-choice]')],paletteName=document.querySelector('.palette-name');
const applyTheme=(theme,persist=true)=>{const selected=['system','light','dark'].includes(theme)?theme:'system',dark=selected==='dark'||(selected==='system'&&colorQuery.matches);document.documentElement.dataset.theme=selected;document.documentElement.dataset.colorMode=dark?'dark':'light';document.querySelector('meta[name="theme-color"]')?.setAttribute('content',dark?'#0b0d0c':'#fbfcf8');themeChoices.forEach(choice=>choice.setAttribute('aria-checked',String(choice.dataset.themeChoice===selected)));if(persist)localStorage.setItem('recast-theme',selected)};
applyTheme(localStorage.getItem('recast-theme')||'system',false);
const applyPalette=(palette,persist=true)=>{const selected=['cobalt','copper','teal','mono'].includes(palette)?palette:'cobalt';document.documentElement.dataset.palette=selected;paletteChoices.forEach(choice=>choice.setAttribute('aria-checked',String(choice.dataset.paletteChoice===selected)));if(paletteName)paletteName.textContent=selected[0].toUpperCase()+selected.slice(1);if(persist)localStorage.setItem('recast-palette',selected)};applyPalette(localStorage.getItem('recast-palette')||'cobalt',false);
themeTrigger?.addEventListener('click',event=>{event.stopPropagation();const open=themeControl.classList.toggle('is-open');themeTrigger.setAttribute('aria-expanded',String(open));if(open)themeChoices.find(item=>item.getAttribute('aria-checked')==='true')?.focus()});
themeChoices.forEach(choice=>choice.addEventListener('click',()=>{applyTheme(choice.dataset.themeChoice);themeControl.classList.remove('is-open');themeTrigger?.setAttribute('aria-expanded','false');themeTrigger?.focus()}));
paletteChoices.forEach(choice=>choice.addEventListener('click',event=>{event.stopPropagation();applyPalette(choice.dataset.paletteChoice)}));
document.addEventListener('click',event=>{if(!themeControl?.contains(event.target)){themeControl?.classList.remove('is-open');themeTrigger?.setAttribute('aria-expanded','false')}});document.addEventListener('keydown',event=>{if(event.key==='Escape'&&themeControl?.classList.contains('is-open')){themeControl.classList.remove('is-open');themeTrigger?.setAttribute('aria-expanded','false');themeTrigger?.focus()}});colorQuery.addEventListener?.('change',()=>{if((localStorage.getItem('recast-theme')||'system')==='system')applyTheme('system',false)});
const message=document.querySelector('.message');if(message)setTimeout(()=>message.remove(),4500);

const pipeline=document.querySelector('.pipeline-card');
if(pipeline){
  const analyzeButton=pipeline.querySelector('.pipeline-start');
  const renderButton=pipeline.querySelector('.pipeline-render');
  const errorBox=pipeline.querySelector('.pipeline-error');
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const humanize=value=>(value||'processing').replaceAll('_',' ').replace(/\b\w/g,letter=>letter.toUpperCase());
  const updateStages=data=>{
    const stages=[...pipeline.querySelectorAll('.stage-track li')];
    if(!stages.length)return;
    const stageIndex={ingest:0,audio:0,transcribe:1,strategy:2,recommendations_ready:2,awaiting_approval:2,rendering_exports:3,render:3,quality_review:4,package:4}[data.current_stage];
    stages.forEach((stage,index)=>{
      stage.classList.toggle('is-complete',Number.isInteger(stageIndex)&&index<stageIndex);
      stage.classList.toggle('is-active',data.status==='running'&&index===stageIndex);
    });
  };
  const render=data=>{
    pipeline.dataset.status=data.status;
    pipeline.querySelector('.pipeline-percent').textContent=`${data.progress}%`;
    pipeline.querySelector('.pipeline-status').textContent=humanize(data.status);
    pipeline.querySelector('.pipeline-stage').textContent=humanize(data.current_stage||data.status);
    pipeline.querySelector('.progress-track i').style.width=`${data.progress}%`;
    errorBox.textContent=data.error||'';errorBox.classList.toggle('hidden',!data.error);
    updateStages(data);
  };
  const refresh=async()=>{
    try{
      const response=await fetch(pipeline.dataset.pipelineUrl,{headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error('Could not read job progress.');
      const data=await response.json();render(data);
      if(['queued','running'].includes(data.status)){setTimeout(refresh,2000);return;}
      if(data.status==='failed'){
        const activeButton=renderButton||analyzeButton;
        if(activeButton){activeButton.disabled=false;activeButton.textContent=renderButton?'Retry rendering':'Retry analysis';}
        return;
      }
      location.reload();
    }catch(error){
      errorBox.textContent=error.message;errorBox.classList.remove('hidden');
      const activeButton=renderButton||analyzeButton;if(activeButton)activeButton.disabled=false;
    }
  };
  const start=async(button,url,busyLabel)=>{
    button.disabled=true;button.textContent=busyLabel;errorBox.classList.add('hidden');
    try{
      const response=await fetch(url,{method:'POST',headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json'}});
      const data=await response.json();
      if(!response.ok)throw new Error(data.detail||'Could not start this job.');
      render(data);setTimeout(refresh,1000);
    }catch(error){errorBox.textContent=error.message;errorBox.classList.remove('hidden');button.disabled=false;button.textContent=renderButton?'Try rendering again':'Try analysis again';}
  };
  analyzeButton?.addEventListener('click',()=>start(analyzeButton,pipeline.dataset.startUrl,'Analyzing recording…'));
  renderButton?.addEventListener('click',()=>start(renderButton,pipeline.dataset.renderUrl,'Rendering exports…'));
  if(pipeline.dataset.status==='running')setTimeout(refresh,500);
}

document.querySelectorAll('.clip-decision').forEach(button=>button.addEventListener('click',async()=>{
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const card=button.closest('.clip-card');
  card.querySelectorAll('.clip-decision').forEach(item=>item.disabled=true);
  try{
    const response=await fetch(button.dataset.url,{method:'POST',headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json'}});
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'Could not update this clip.');
    card.querySelector('.clip-state').textContent=data.status.charAt(0).toUpperCase()+data.status.slice(1);
    card.querySelectorAll('.clip-decision').forEach(item=>item.classList.toggle('primary',item.dataset.state===data.status));
    const approved=document.querySelectorAll('.clip-decision.primary[data-state="approved"]').length;
    document.querySelector('.approved-count').textContent=approved;
    const renderButton=document.querySelector('.pipeline-render');
    if(renderButton){renderButton.disabled=approved===0;renderButton.dataset.approvedCount=approved;renderButton.textContent=`Render ${approved} approved clip${approved===1?'':'s'}`;}
  }catch(error){alert(error.message);}
  finally{card.querySelectorAll('.clip-decision').forEach(item=>item.disabled=false);}
}));

const socialManager=document.querySelector('.social-manager');
if(socialManager){
  const form=socialManager.querySelector('.social-handle-form'),list=socialManager.querySelector('.social-handle-list'),errorBox=socialManager.querySelector('.social-form-error');
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const request=async(url,method,body)=>{const response=await fetch(url,{method,headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json','Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=response.status===204?{}:await response.json();if(!response.ok)throw new Error(data.detail||data.platform?.[0]||data.handle?.[0]||Object.values(data).flat().join(' ')||'Could not save this profile.');return data;};
  const showError=error=>{errorBox.textContent=error.message;errorBox.classList.remove('hidden');};
  const bind=row=>{
    row.querySelector('.social-update').addEventListener('click',async()=>{const button=row.querySelector('.social-update');button.disabled=true;try{await request(`${socialManager.dataset.apiUrl}${row.dataset.id}/`,'PATCH',{handle:row.querySelector('input').value});button.textContent='Saved';setTimeout(()=>button.textContent='Update',1200);}catch(error){showError(error);}finally{button.disabled=false;}});
    row.querySelector('.social-delete').addEventListener('click',async()=>{if(!confirm('Remove this social profile?'))return;try{await request(`${socialManager.dataset.apiUrl}${row.dataset.id}/`,'DELETE');row.remove();if(!list.querySelector('article'))list.innerHTML='<p class="social-empty">No social profiles added yet.</p>';}catch(error){showError(error);}});
  };
  list.querySelectorAll('article').forEach(bind);
  form.addEventListener('submit',async event=>{event.preventDefault();errorBox.classList.add('hidden');const button=form.querySelector('button[type="submit"]');button.disabled=true;try{const data=await request(socialManager.dataset.apiUrl,'POST',{platform:form.platform.value,handle:form.handle.value});list.querySelector('.social-empty')?.remove();const row=document.createElement('article');row.dataset.id=data.id;row.dataset.platform=data.platform;row.innerHTML=`<strong>${data.platform_label}</strong><input maxlength="160" aria-label="${data.platform_label} handle"><button class="download-chip social-update" type="button">Update</button><button class="download-chip social-delete" type="button">Delete</button>`;row.querySelector('input').value=data.handle;list.appendChild(row);bind(row);form.reset();}catch(error){showError(error);}finally{button.disabled=false;}});
}

const intel=document.querySelector('.intel-shell');
if(intel){
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const api=async(url,method='GET',body)=>{const response=await fetch(url,{method,headers:{Accept:'application/json','Content-Type':'application/json','X-CSRFToken':decodeURIComponent(cookie('csrftoken'))},body:body?JSON.stringify(body):undefined});const data=response.status===204?{}:await response.json();if(!response.ok)throw new Error(data.detail||data.action?.[0]||Object.values(data).flat().join(' ')||'Request failed.');return data;};
  const poll=async()=>{try{const data=await api(intel.dataset.intelligenceUrl);if(data.status==='ready'||data.status==='failed'){location.reload();return;}setTimeout(poll,1800);}catch(error){document.querySelector('.intel-error').textContent=error.message;}};
  const start=async()=>{const button=document.querySelector('.intel-analyze');if(button){button.disabled=true;button.textContent='Analyzing content…';}try{await api(intel.dataset.startUrl,'POST');setTimeout(poll,1000);}catch(error){if(button)button.disabled=false;document.querySelector('.intel-error').textContent=error.message;}};
  document.querySelector('.intel-analyze')?.addEventListener('click',start);
  if(intel.dataset.status==='queued')start();else if(intel.dataset.status==='running')poll();
  document.querySelectorAll('.repurpose-list article').forEach(asset=>{
    const textarea=asset.querySelector('textarea');
    asset.querySelector('.asset-copy')?.addEventListener('click',async event=>{await navigator.clipboard.writeText(textarea.value);event.currentTarget.textContent='Copied';setTimeout(()=>event.currentTarget.textContent='Copy',1200);});
    asset.querySelector('.asset-save')?.addEventListener('click',async event=>{event.currentTarget.disabled=true;try{await api(`/api/v1/repurpose-assets/${asset.dataset.assetId}/`,'PATCH',{content:textarea.value});event.currentTarget.textContent='Saved';}catch(error){alert(error.message);}finally{event.currentTarget.disabled=false;setTimeout(()=>event.currentTarget.textContent='Save edits',1200);}});
    asset.querySelectorAll('footer button[data-operation]').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{const data=await api(`/api/v1/repurpose-assets/${asset.dataset.assetId}/transform/`,'POST',{operation:button.dataset.operation});textarea.value=data.content;}catch(error){alert(error.message);}finally{button.disabled=false;}}));
  });
  document.querySelectorAll('.editor-accept').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{await api(`${intel.dataset.intelligenceUrl}accept-editor-recommendation/`,'POST',{action_id:button.dataset.actionId});button.textContent='Accepted ✓';}catch(error){button.disabled=false;alert(error.message);}}));
  const publicationForm=document.querySelector('.publication-form');
  if(publicationForm){
    const actionField=publicationForm.querySelector('[name="action"]'),scheduleField=publicationForm.querySelector('[name="scheduled_for"]'),titleField=publicationForm.querySelector('[name="title"]'),captionField=publicationForm.querySelector('[name="caption"]');
    actionField.addEventListener('change',()=>publicationForm.querySelector('.schedule-field').classList.toggle('hidden',actionField.value!=='schedule'));
    publicationForm.addEventListener('submit',async event=>{event.preventDefault();const destinations=[...publicationForm.querySelectorAll('[name="destination"]:checked')];const result=publicationForm.querySelector('.publish-result');if(!destinations.length){result.textContent='Choose at least one destination.';return;}const clipId=Number(intel.dataset.startUrl.match(/clips\/(\d+)/)[1]);try{await Promise.all(destinations.map(destination=>api(intel.dataset.publicationUrl,'POST',{clip:clipId,social_handle:Number(destination.value),action:actionField.value,scheduled_for:scheduleField.value||null,platform_payload:{title:titleField.value,caption:captionField.value}})));result.textContent=`${destinations.length} publishing job${destinations.length===1?'':'s'} created.`;result.className='publish-result success';}catch(error){result.textContent=error.message;result.className='publish-result error';}});
  }
}
