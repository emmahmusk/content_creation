(()=>{
  const field=document.querySelector('.welcome-balloon-field');
  const toast=document.querySelector('.welcome-credit-toast');
  if(!field||!toast)return;
  const reduceMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(!reduceMotion){
    const colors=['#5478ff','#eb8b5e','#53c9b8','#d889cf','#f2c65d','#9b8cff'];
    for(let i=0;i<26;i++){
      const balloon=document.createElement('i');
      balloon.className='welcome-balloon';
      balloon.style.setProperty('--x',`${Math.random()*96}%`);
      balloon.style.setProperty('--size',`${22+Math.random()*25}px`);
      balloon.style.setProperty('--duration',`${5.5+Math.random()*4}s`);
      balloon.style.setProperty('--delay',`${Math.random()*1.8}s`);
      balloon.style.setProperty('--drift',`${Math.random()*130-65}px`);
      balloon.style.setProperty('--string',`${24+Math.random()*22}px`);
      balloon.style.setProperty('--balloon-color',colors[i%colors.length]);
      field.append(balloon);
    }
    window.setTimeout(()=>field.remove(),11500);
  }else field.remove();
  toast.querySelector('.welcome-credit-dismiss')?.addEventListener('click',()=>toast.remove());
  window.setTimeout(()=>toast.remove(),12000);
})();
