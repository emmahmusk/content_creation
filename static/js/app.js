document.querySelectorAll('.copy-button').forEach(button=>button.addEventListener('click',async()=>{await navigator.clipboard.writeText(button.dataset.copy);const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1600)}));
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
