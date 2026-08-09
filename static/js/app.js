document.querySelectorAll('.copy-button').forEach(button=>button.addEventListener('click',async()=>{await navigator.clipboard.writeText(button.dataset.copy);const old=button.textContent;button.textContent='Copied';setTimeout(()=>button.textContent=old,1600)}));
const message=document.querySelector('.message');if(message)setTimeout(()=>message.remove(),4500);
const pipeline=document.querySelector('.pipeline-card');
if(pipeline){
  const button=pipeline.querySelector('.pipeline-start');
  const errorBox=pipeline.querySelector('.pipeline-error');
  const cookie=name=>document.cookie.split('; ').find(row=>row.startsWith(`${name}=`))?.split('=')[1]||'';
  const render=data=>{
    pipeline.dataset.status=data.status;
    pipeline.querySelector('.pipeline-percent').textContent=`${data.progress}%`;
    pipeline.querySelector('.pipeline-status').textContent=data.status.replaceAll('_',' ');
    pipeline.querySelector('.pipeline-stage').textContent=(data.current_stage||data.status).replaceAll('_',' ');
    pipeline.querySelector('.progress-track i').style.width=`${data.progress}%`;
    errorBox.textContent=data.error||''; errorBox.classList.toggle('hidden',!data.error);
  };
  const refresh=async()=>{
    try{
      const response=await fetch(pipeline.dataset.pipelineUrl,{headers:{Accept:'application/json'}});
      if(!response.ok)throw new Error('Could not read job progress.');
      const data=await response.json(); render(data);
      if(['queued','running'].includes(data.status)){setTimeout(refresh,2000);return;}
      if(data.status==='failed'){button.disabled=false;button.textContent='Retry analysis';return;}
      location.reload();
    }catch(error){errorBox.textContent=error.message;errorBox.classList.remove('hidden');button.disabled=false;}
  };
  button?.addEventListener('click',async()=>{
    button.disabled=true;button.textContent='Starting…';errorBox.classList.add('hidden');
    try{
      const response=await fetch(pipeline.dataset.startUrl,{method:'POST',headers:{'X-CSRFToken':decodeURIComponent(cookie('csrftoken')),Accept:'application/json'}});
      const data=await response.json();
      if(!response.ok)throw new Error(data.detail||'Could not start analysis.');
      render(data);button.textContent='Analyzing…';setTimeout(refresh,1000);
    }catch(error){errorBox.textContent=error.message;errorBox.classList.remove('hidden');button.disabled=false;button.textContent='Try again';}
  });
  if(pipeline.dataset.status==='running')setTimeout(refresh,500);
}
