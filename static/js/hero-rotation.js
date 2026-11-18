(()=>{
  const heading=document.querySelector('[data-hero-heading]');
  const primary=heading?.querySelector('[data-hero-primary]');
  const secondary=heading?.querySelector('[data-hero-secondary]');
  if(!heading||!primary||!secondary)return;
  const motion=window.matchMedia('(prefers-reduced-motion: reduce)');
  const captions=[
    ['Turn long videos into clips.','Ready for Reels, Shorts, & TikTok.'],
    ['Turn your podcast into more.','Give every great conversation another life.'],
    ['Make your streams go further.','Share the moments your audience loved.'],
    ['Turn client videos into clips.','Deliver more content with less editing time.'],
    ['Share what you know.','Turn lessons and interviews into stories worth watching.']
  ];
  let index=0,timer=null,swapTimer=null;
  const stop=()=>{clearInterval(timer);clearTimeout(swapTimer);timer=null;heading.classList.remove('hero-caption-changing');};
  const start=()=>{
    stop();
    if(motion.matches||document.hidden)return;
    timer=setInterval(()=>{
      heading.classList.add('hero-caption-changing');
      swapTimer=setTimeout(()=>{index=(index+1)%captions.length;primary.textContent=captions[index][0];secondary.textContent=captions[index][1];heading.classList.remove('hero-caption-changing');},250);
    },8000);
  };
  document.addEventListener('visibilitychange',start);
  motion.addEventListener?.('change',start);
  start();
})();
