
/* ---- Sichtbarkeits-Trigger, Zähl-Animation, Segment-Umschalter ---- */
(function(){
  const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}}),{threshold:.25});
  document.querySelectorAll('.card,.panel,.quote,.kpi,.frame,.tile,section').forEach(el=>io.observe(el));

  const nf=(dec)=>new Intl.NumberFormat('de-DE',{minimumFractionDigits:dec,maximumFractionDigits:dec});
  function countTo(el,target,dec,suffix,dur){
    if(reduce){el.textContent=nf(dec).format(target)+suffix;return;}
    const from=parseFloat(el.dataset.cur||0),t0=performance.now();
    el.classList.remove('tick');void el.offsetWidth;el.classList.add('tick');
    (function step(t){const p=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-p,3),v=from+(target-from)*e;
      el.textContent=nf(dec).format(v)+suffix;if(p<1)requestAnimationFrame(step);else el.dataset.cur=target;})(t0);
  }
  // Zähler beim ersten Sichtbarwerden
  const nums=document.querySelectorAll('[data-val]');
  const nio=new IntersectionObserver(es=>es.forEach(e=>{if(!e.isIntersecting)return;const el=e.target;
    countTo(el,parseFloat(el.dataset.val),+(el.dataset.dec||0),el.dataset.suffix||'',1400);nio.unobserve(el);}),{threshold:.5});
  nums.forEach(n=>{n.textContent=nf(+(n.dataset.dec||0)).format(0)+(n.dataset.suffix||'');nio.observe(n);});
  // Karussell (Relevante Zahlen)
  document.querySelectorAll('.carousel').forEach(c=>{const tr=c.querySelector('.track'),items=[...tr.children],dots=c.querySelector('.dots-ind');
    const pages=Math.max(1,items.length-2);for(let i=0;i<pages;i++){const d=document.createElement('i');if(!i)d.classList.add('on');dots.appendChild(d);}
    const upd=()=>{const w=items[0].getBoundingClientRect().width+32,i=Math.round(tr.scrollLeft/w);[...dots.children].forEach((d,k)=>d.classList.toggle('on',k===Math.min(i,pages-1)));};
    tr.addEventListener('scroll',upd,{passive:true});
    c.querySelector('.prev').addEventListener('click',()=>tr.scrollBy({left:-(items[0].getBoundingClientRect().width+32),behavior:'smooth'}));
    c.querySelector('.next').addEventListener('click',()=>tr.scrollBy({left:items[0].getBoundingClientRect().width+32,behavior:'smooth'}));});
  // Tab-Module: Tabs, Serien-Checkboxen, Diagramm/Tabelle, PNG
  function layoutGrouped(svg){const on=[...svg.closest('.pane').querySelectorAll('input[type=checkbox]')].filter(c=>c.checked).map(c=>+c.value);
    svg.querySelectorAll('.grp').forEach(g=>{const x0=+g.dataset.x0,w=+g.dataset.w,n=on.length||1,inner=w*0.72,bw=Math.min(52,(inner-(n-1)*4)/n),start=x0+(w-(bw*n+(n-1)*4))/2;
      g.querySelectorAll('.gbar').forEach(b=>{const k=on.indexOf(+b.dataset.s);b.classList.toggle('off',k<0);if(k>=0){b.setAttribute('x',(start+k*(bw+4)).toFixed(1));b.setAttribute('width',bw.toFixed(1));}});});}
  document.querySelectorAll('.module').forEach(m=>{
    const panes=m.querySelectorAll('.pane');
    m.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>{m.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));
      panes.forEach(p=>p.hidden=p.dataset.pane!==b.dataset.pane);m.querySelectorAll('svg.grouped').forEach(layoutGrouped);}));
    m.querySelectorAll('.chk input').forEach(c=>c.addEventListener('change',()=>m.querySelectorAll('svg.grouped').forEach(layoutGrouped)));
    m.querySelectorAll('.rad input').forEach(r=>r.addEventListener('change',()=>r.closest('.pane').querySelectorAll('.view').forEach(v=>v.hidden=v.dataset.view!==r.value)));
    m.querySelectorAll('svg.grouped').forEach(layoutGrouped);
    const dl=m.querySelector('.dl');if(dl)dl.addEventListener('click',()=>{const svg=m.querySelector('.pane:not([hidden]) svg');if(!svg)return;
      const clone=svg.cloneNode(true);clone.querySelectorAll('.off').forEach(e=>e.remove());const cs=getComputedStyle(svg);
      clone.querySelectorAll('[fill^="var("]').forEach(e=>e.setAttribute('fill',cs.getPropertyValue('--band')));
      clone.querySelectorAll('.grid').forEach(e=>{e.setAttribute('stroke','#e5e3de');});clone.querySelectorAll('.axis').forEach(e=>e.setAttribute('stroke','#b9b6ae'));
      clone.querySelectorAll('text').forEach(e=>{e.setAttribute('fill','#2e2d2c');e.setAttribute('font-family','Helvetica,Arial,sans-serif');e.setAttribute('font-size',e.classList.contains('tick')?'11':'12');});
      const vb=svg.viewBox.baseVal,sc=2,cv=document.createElement('canvas');cv.width=vb.width*sc;cv.height=vb.height*sc;const ctx=cv.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);
      const img=new Image();img.onload=()=>{ctx.drawImage(img,0,0,cv.width,cv.height);const a=document.createElement('a');a.download=(dl.dataset.name||'chart')+'.png';a.href=cv.toDataURL('image/png');a.click();};
      img.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+vb.width+' '+vb.height+'">'+clone.innerHTML+'</svg>');});
  });
  // Segment-Umschalter (Gesamt / Persönlich / Digital)
  document.querySelectorAll('.seg button').forEach(b=>b.addEventListener('click',()=>{const k=b.dataset.seg;
    document.querySelectorAll('.seg button').forEach(x=>x.classList.toggle('on',x.dataset.seg===k));
    document.querySelectorAll('.num.sw').forEach(n=>{const v=parseFloat(n.dataset[k]);n.dataset.val=v;countTo(n,v,+(n.dataset.dec||0),n.dataset.suffix||'',700);});}));
})();


(function(){const t=document.getElementById('tip');
document.querySelectorAll('.mark[data-tip],.bub[data-tip]').forEach(m=>{
 m.addEventListener('mousemove',e=>{t.textContent=m.dataset.tip;t.style.left=e.clientX+'px';t.style.top=e.clientY+'px';t.style.opacity=1;});
 m.addEventListener('mouseleave',()=>t.style.opacity=0);});})();
