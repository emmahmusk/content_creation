/* Signed uploads send recording bytes straight to storage before project submission. */
document.querySelectorAll('form[data-direct-upload-url]').forEach(form=>{
  const input=form.querySelector('[name="file"]');
  const token=form.querySelector('[name="cloudinary_upload_token"]');
  const status=form.querySelector('[data-source-upload-status]');
  const progress=form.querySelector('[data-source-upload-progress]');
  const cancel=form.querySelector('[data-source-upload-cancel]');
  if(!input||!token||!status||!progress||!cancel)return;
  let submitting=false,uploading=false,aborted=false,currentRequest=null;
  if(token.value)status.textContent='Your recording is uploaded. Review the fields and submit again.';
  input.addEventListener('change',()=>{token.value='';status.textContent='';progress.hidden=true;});
  cancel.addEventListener('click',()=>{aborted=true;currentRequest?.abort();});
  const sendChunk=(configuration,file,start,end,uploadId)=>new Promise((resolve,reject)=>{
    if(aborted){reject(new Error('Upload cancelled. Your project has not been submitted.'));return;}
    const body=new FormData();
    Object.entries(configuration.params).forEach(([key,value])=>body.append(key,String(value)));
    body.append('api_key',configuration.api_key);
    body.append('signature',configuration.signature);
    body.append('file',file.slice(start,end),file.name);
    const xhr=new XMLHttpRequest();currentRequest=xhr;
    xhr.open('POST',configuration.upload_url);
    xhr.timeout=180000;
    xhr.setRequestHeader('X-Unique-Upload-Id',uploadId);
    xhr.setRequestHeader('Content-Range',`bytes ${start}-${end-1}/${file.size}`);
    xhr.upload.onprogress=event=>{
      const uploaded=event.lengthComputable?Math.min(end-start,(end-start)*event.loaded/event.total):0;
      progress.value=Math.min(99,Math.round((start+uploaded)/file.size*100));
      status.textContent=`Uploading recording… ${progress.value}%`;
    };
    xhr.onload=()=>{
      let result;try{result=JSON.parse(xhr.responseText);}catch(error){reject(new Error('The upload could not be confirmed. Please try again.'));return;}
      if(xhr.status<200||xhr.status>=300||result.error){reject(new Error('The recording could not be uploaded. Check your connection and file, then try again.'));return;}
      resolve(result);
    };
    xhr.onerror=()=>reject(new Error('The upload connection was interrupted. Please try again.'));
    xhr.ontimeout=()=>reject(new Error('The upload timed out. Please try again.'));
    xhr.onabort=()=>reject(new Error('Upload cancelled. Your project has not been submitted.'));
    xhr.send(body);
  });
  form.addEventListener('submit',async event=>{
    if(submitting)return;
    const file=input.files?.[0];
    if(!file)return;
    event.preventDefault();event.stopPropagation();
    if(uploading)return;
    const button=event.submitter||form.querySelector('[type="submit"]');
    if(form.querySelector('[name="external_url"]')?.value.trim()){
      status.textContent='Choose a recording or a source link, then submit again.';return;
    }
    if(!form.querySelector('[name="rights_confirmed"]')?.checked){
      status.textContent='Confirm your content rights before uploading the recording.';return;
    }
    if(!file.size||file.size>Number(form.dataset.uploadMaxBytes)){
      status.textContent='The recording is empty or exceeds the upload limit.';return;
    }
    uploading=true;aborted=false;input.disabled=true;
    progress.hidden=false;progress.value=0;cancel.hidden=false;
    setButtonBusy(button,true,'Uploading recording…');
    try{
      if(!token.value){
        const response=await fetchWithTimeout(form.dataset.directUploadUrl,{
          method:'POST',credentials:'same-origin',
          headers:{'Content-Type':'application/json','X-CSRFToken':form.querySelector('[name="csrfmiddlewaretoken"]').value},
          body:JSON.stringify({filename:file.name,size:file.size,rights_confirmed:true})
        });
        const configuration=await response.json();
        if(!response.ok)throw new Error(configuration.error||'Uploads are unavailable. Please try again.');
        const uploadId=configuration.params.public_id.split('/').pop();
        let result;
        for(let start=0;start<file.size;start+=configuration.chunk_bytes){
          const end=Math.min(file.size,start+configuration.chunk_bytes);
          result=await sendChunk(configuration,file,start,end,uploadId);
        }
        if(aborted)throw new Error('Upload cancelled. Your project has not been submitted.');
        if(result.public_id!==configuration.params.public_id||result.done===false)throw new Error('The recording has not finished uploading. Please retry.');
        token.value=configuration.token;
      }
      progress.value=100;cancel.hidden=true;
      status.textContent='Recording uploaded. Verifying and creating your project…';
      submitting=true;uploading=false;
      setButtonBusy(button,false);button.disabled=false;
      form.requestSubmit(button);
      // If a field was edited during upload, native validation can prevent submission.
      if(!form.checkValidity()){
        submitting=false;input.disabled=false;
        status.textContent='Recording uploaded. Complete the highlighted fields and submit again.';
      }
    }catch(error){
      status.textContent=error.message||'The upload could not be completed. Please try again.';
      input.disabled=false;uploading=false;submitting=false;cancel.hidden=true;
      setButtonBusy(button,false);button.disabled=false;
    }
  });
});
