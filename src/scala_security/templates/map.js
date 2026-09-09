"use strict";
(() => {
  const data = JSON.parse(document.getElementById("map-data").textContent);
  const $ = id => document.getElementById(id);
  const ns = "http://www.w3.org/2000/svg";
  const svg = (tag, attrs, parent) => {
    const el = document.createElementNS(ns, tag);
    for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,value);
    if (parent) parent.appendChild(el);
    return el;
  };
  const text = (parent, tag, value, className) => {
    const el = document.createElement(tag); el.textContent=value;
    if (className) el.className=className;
    parent.appendChild(el); return el;
  };
  const fmt = v => v == null ? "Unknown" : Number(v).toLocaleString(undefined,{maximumFractionDigits:2});
  const pct = (n,d) => d > 0 ? (100*n/d).toFixed(1) : null;
  const projects = data.projects;
  const world = data.world;
  const index = new Map(projects.map((p,i)=>[p.id,i]));
  const country = Array(projects.length);
  for (const c of world.countries) country[index.get(c.project)] = c;
  const order = projects.map((_,i)=>i).sort((a,b)=>country[b].area-country[a].area);
  const compromised = new Set();
  let affected = new Set(), selected = null, hovered = null, layer = "exposure";
  let zoom=1, tx=0, ty=0, drag=null, suppressClick=false;
  let pendingFrame=0, labelsDirty=true, markerZoom=1, moving=false, settleTimer=0;
  let pointer=null, linksKey="", fineGeometry=false, inputMatrix=null, viewportScale=1;
  const detailPaths={land:[],lakes:[],rivers:[]};
  const labelPriority=()=>[...labels].sort((a,b)=>(b.i===selected)-(a.i===selected)||a.rank-b.rank);
  const width=world.width, height=world.height;
  $("atlas").setAttribute("viewBox",`0 0 ${width} ${height}`);
  const els = [], labels=[];
  const totalValue = projects.reduce((s,p)=>s+(p.value??0),0);
  const unknownValueCount = projects.filter(p=>p.value==null).length;
  const maxExposure=Math.max(...projects.map(p=>p.exposure),1);
  const descriptions={
    exposure:"The combined Value of verified dependants. Brighter countries support more of the ecosystem.",
    maintenance:"Observed maintenance activity and contributor resilience. Warmer colors indicate lower scores.",
    security:"Observed security practices. Warmer colors indicate lower scores; missing evidence is hatched.",
    value:"Each project's provisional Value, calculated from stars with logarithmic saturation."
  };
  const names={exposure:"Exposed Value",maintenance:"Maintenance",security:"Security",value:"Project Value"};
  const palette=["#315b63","#668789","#c2cebd","#f7bd96","#f15b2c"];
  const color = t => {
    t=Math.max(0,Math.min(1,t));const v=t*(palette.length-1),a=Math.floor(v),b=Math.min(a+1,palette.length-1),f=v-a;
    const rgb=h=>[1,3,5].map(k=>parseInt(h.slice(k,k+2),16));
    return `rgb(${rgb(palette[a]).map((n,k)=>Math.round(n+(rgb(palette[b])[k]-n)*f)).join(",")})`;
  };
  for(let y=80;y<height;y+=85)for(let x=35;x<width;x+=140){
    svg("path",{d:`M${x+(y%3)*12},${y}h12m9,0h5`,stroke:"#476b73","stroke-width":1,opacity:.4},$("sea-details"));
  }
  world.land.forEach((d,i)=>detailPaths.land.push(svg("path",{d:world.overview.land[i],class:"coast"},$("land"))));
  projects.forEach((p,i)=>{
    const el=svg("path",{d:country[i].path,id:`country-${i}`,class:"country","data-project":p.id,"aria-label":p.id},$("countries"));
    svg("title",{},el).textContent=p.id;
    el.addEventListener("pointerenter",e=>{if(drag||moving)return;hovered=i;showTooltip(i,e);drawConnections(i);});
    el.addEventListener("pointermove",e=>{if(!drag&&!moving)positionTooltip(e);});
    el.addEventListener("pointerleave",()=>{if(moving)return;hovered=null;$("tooltip").hidden=true;drawConnections(null);});
    el.addEventListener("click",()=>{if(suppressClick)return;selected=i;toggleCompromise(i);});
    els.push(el);
  });
  world.rivers.forEach((d,i)=>detailPaths.rivers.push(svg("path",{d:world.overview.rivers[i],class:"river"},$("water"))));
  world.lakes.forEach((d,i)=>detailPaths.lakes.push(svg("path",{d:world.overview.lakes[i],class:"lake","pointer-events":"none"},$("water"))));
  world.scenery.forEach(batch=>{
    const group=svg("g",{opacity:batch.opacity},$("scenery"));
    batch.paths.forEach(p=>svg("path",p.stroke?
      {d:p.d,fill:"none",stroke:p.color,"stroke-width":p.stroke}:
      {d:p.d,fill:p.color},group));
  });
  // Quiet nautical landmarks in open water, chosen from the world geometry.
  const waterPoint=(x,y)=>!els.some(el=>el.isPointInFill(new DOMPoint(x,y)));
  let boats=0;
  for (const [x,y] of [[320,250],[1120,430],[1900,220],[2200,1200],[700,1310],[1200,1250]]){
    if(waterPoint(x,y)&&boats++<4)svg("use",{href:"#boat",x,y,width:37,height:30,opacity:.85},$("scenery"));
  }
  for (const [x,y,label] of [[1120,160,"THE SHARED SEA"],[1200,1450,"SCALALAND"]]){
    if(waterPoint(x,y))svg("text",{x,y,class:"sea-label"},$("sea-details")).textContent=label;
  }
  order.forEach((i,rank)=>{
    const c=country[i],label=svg("text",{x:c.x,y:c.y,class:`country-label${rank<15?" major":""}`},$("labels"));
    label.textContent=projects[i].id.split("/").at(-1);
    labels.push({el:label,i,rank});
  });
  function recolor(){
    projects.forEach((p,i)=>{
      const v=p[layer];
      const t=layer==="exposure"?Math.sqrt(v/maxExposure):layer==="maintenance"||layer==="security"?1-v:v;
      els[i].style.fill=v==null?"url(#unknown)":color(t);
    });
    $("layer-help").textContent=descriptions[layer];$("legend-title").textContent=names[layer];
    const reverse=layer==="maintenance"||layer==="security";
    $("legend-gradient").style.background=`linear-gradient(to right,${(reverse?[...palette].reverse():palette).join(",")})`;
    $("legend-min").textContent="0";$("legend-mid").textContent=fmt(layer==="exposure"?maxExposure/4:.5);
    $("legend-max").textContent=fmt(layer==="exposure"?maxExposure:1);
    if(selected!=null)renderDetail();
  }
  function impact(){
    affected=new Set(compromised);
    for(const i of compromised)for(const [j] of data.fallout[i])affected.add(j);
    const exposed=[...affected].filter(i=>!compromised.has(i));
    const known=[...affected].reduce((s,i)=>s+(projects[i].value??0),0);
    const unknown=[...affected].filter(i=>projects[i].value==null).length;
    $("affected-percent").textContent=pct(affected.size,projects.length);
    $("compromised-count").textContent=compromised.size;$("exposed-count").textContent=exposed.length;
    $("value-percent").textContent=totalValue?`${pct(known,totalValue)}%`:"Unknown";
    $("impact-bar").style.width=`${pct(affected.size,projects.length)}%`;
    $("impact-note").textContent=compromised.size?`${affected.size} of ${projects.length} projects affected, counted once. Includes verified dependants up to 5 hops.${unknownValueCount?` ${unknown} affected / ${unknownValueCount} total projects have unknown Value.`:""}`:"Click a country to compromise it. Click again to undo.";
    $("reset").disabled=!compromised.size;
    $("exposure-overlay").replaceChildren();
    projects.forEach((_,i)=>{
      els[i].classList.toggle("compromised",compromised.has(i));
      els[i].classList.toggle("exposed",affected.has(i)&&!compromised.has(i));
      els[i].classList.toggle("focused",selected===i);
    });
    for(const i of affected){
      svg("path",{d:country[i].path,fill:compromised.has(i)?"url(#infection)":"url(#exposure-hatch)","fill-opacity":compromised.has(i)?.8:.5,stroke:"none"},$("exposure-overlay"));
    }
    $("selected-list").replaceChildren();
    for(const i of compromised){const b=text($("selected-list"),"button",projects[i].id.split("/").at(-1)+" ×");b.setAttribute("aria-label",`Undo compromise ${projects[i].id}`);b.onclick=()=>toggleCompromise(i);}
    renderDetail();labelsDirty=true;scheduleTransform();
  }
  function toggleCompromise(i){if(compromised.has(i))compromised.delete(i);else compromised.add(i);impact();}
  function inspect(i,fly=false){selected=i;impact();if(fly){zoom=3.5;tx=width/2-country[i].x*zoom;ty=height/2-country[i].y*zoom;labelsDirty=true;scheduleTransform();}}
  function renderDetail(){
    if(selected==null)return;
    const i=selected,p=projects[i],box=$("project-detail");box.replaceChildren();
    text(box,"div","COUNTRY / PROJECT","eyebrow");
    text(box,"h2",p.id.split("/").at(-1));text(box,"div",p.id,"owner");
    text(box,"span",compromised.has(i)?"▧ COMPROMISED":affected.has(i)?"◇ EXPOSED":"NOT SELECTED","status");
    const metrics=text(box,"div","","project-metrics");
    for(const [name,v] of [["Exposed Value",p.exposure],["Verified dependants",data.fallout[i].length],["Maintenance",p.maintenance],["Security",p.security],["Project Value",p.value],["Stars",p.stars]]){
      const m=text(metrics,"div","");text(m,"span",name);text(m,"strong",fmt(v));
    }
    const action=text(box,"button",compromised.has(i)?"Undo compromise":"Compromise this project","primary");action.onclick=()=>toggleCompromise(i);
    const link=text(box,"a","View repository ↗","repo-link");link.href=`https://github.com/${p.id}`;link.target="_blank";link.rel="noopener";
    if(p.unvalued)text(box,"p",`${p.unvalued} dependants have unknown Value and do not contribute to Exposed Value.`,"small");
    text(box,"p",p.categories.join(" · "),"small");
  }
  function showTooltip(i,e){
    const tip=$("tooltip");tip.replaceChildren();text(tip,"strong",projects[i].id);
    text(tip,"span",`${names[layer]}: ${fmt(projects[i][layer])} · ${data.fallout[i].length} dependants`);
    text(tip,"span",compromised.has(i)?"Click to undo compromise":"Click to compromise");tip.hidden=false;positionTooltip(e);
  }
  function positionTooltip(e){const rect=$("atlas").getBoundingClientRect(),tip=$("tooltip");tip.style.left=Math.max(8,Math.min(e.clientX-rect.left+16,rect.width-tip.offsetWidth-10))+"px";tip.style.top=Math.max(8,Math.min(e.clientY-rect.top+16,rect.height-tip.offsetHeight-10))+"px";}
  function drawConnections(i){
    const group=$("connections"), key=`${i}/${$("hops").value}/${$("show-links").checked}`;
    if(key===linksKey)return;
    linksKey=key;group.replaceChildren();if(i==null||!$("show-links").checked)return;
    markerZoom=zoom;
    const a=country[i],depth=Number($("hops").value);
    for(const [j,hops] of data.fallout[i]){
      if(hops>depth)continue;
      const b=country[j],dx=b.x-a.x,dy=b.y-a.y;
      svg("path",{d:`M${a.x} ${a.y}Q${(a.x+b.x)/2-dy*.12} ${(a.y+b.y)/2+dx*.12} ${b.x} ${b.y}`,class:"connection"},group);
      svg("circle",{cx:b.x,cy:b.y,r:2.3/zoom,fill:"var(--exposure)"},group);
    }
    svg("circle",{cx:a.x,cy:a.y,r:4/zoom,fill:"#fa5927",stroke:"#fff1df","stroke-width":1/zoom},group);
  }
  function updateLabels(){
    const scale=viewportScale*zoom;
    const occupied=[];
    const priority=labelPriority();
    for(const {el,i,rank} of priority){
      const c=country[i],size=rank<15?26:13;
      const w=el.textContent.length*size*.54*scale,h=size*scale;
      const x=c.x*scale,y=c.y*scale;
      const box=[x-w/2-4,y-h/2-3,x+w/2+4,y+h/2+3];
      const fits=scale*Math.sqrt(c.area)>w*.55;
      const show=(i===selected||(h>=8&&fits))&&!occupied.some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1]);
      el.style.display=show?"":"none";
      if(show)occupied.push(box);
    }
  }
  function transform(){
    pendingFrame=0;
    tx=Math.max(width*(1-zoom)-width*.2,Math.min(width*.2,tx));
    ty=Math.max(height*(1-zoom)-height*.2,Math.min(height*.2,ty));
    $("world").setAttribute("transform",`translate(${tx} ${ty}) scale(${zoom})`);
    document.querySelector(".map-top").hidden=zoom>1.3;
    const fine=zoom>(fineGeometry?2.2:2.5);
    if(fine!==fineGeometry){
      fineGeometry=fine;
      for(const kind of Object.keys(detailPaths))detailPaths[kind].forEach((el,i)=>el.setAttribute("d",(fine?world:world.overview)[kind][i]));
    }
    if(labelsDirty){updateLabels();labelsDirty=false;}
    if(markerZoom!==zoom){
      const circles=$("connections").querySelectorAll("circle");
      circles.forEach((c,i)=>{
        c.setAttribute("r",(i===circles.length-1?4:2.3)/zoom);
        if(c.hasAttribute("stroke"))c.setAttribute("stroke-width",1/zoom);
      });
      markerZoom=zoom;
    }
  }
  function scheduleTransform(){if(!pendingFrame)pendingFrame=requestAnimationFrame(transform);}
  function settleMovement(){
    if(drag){settleTimer=setTimeout(settleMovement,120);return;}
    moving=false;$("connections").style.visibility="";
    const hit=pointer?document.elementFromPoint(pointer.x,pointer.y)?.closest(".country"):null;
    hovered=hit?Number(hit.id.slice(8)):null;
    drawConnections(hovered);
    if(hovered!=null)showTooltip(hovered,{clientX:pointer.x,clientY:pointer.y});
  }
  function movement(){
    moving=true;$("connections").style.visibility="hidden";$("tooltip").hidden=true;
    clearTimeout(settleTimer);settleTimer=setTimeout(settleMovement,120);
  }
  function zoomAt(factor,x=width/2,y=height/2){
    const next=Math.max(1,Math.min(9,zoom*factor)),r=next/zoom;
    tx=x-(x-tx)*r;ty=y-(y-ty)*r;labelsDirty ||= next!==zoom;zoom=next;scheduleTransform();
  }
  function local(e){inputMatrix ??= $("atlas").getScreenCTM().inverse();return new DOMPoint(e.clientX,e.clientY).matrixTransform(inputMatrix);}
  $("atlas").addEventListener("wheel",e=>{e.preventDefault();pointer={x:e.clientX,y:e.clientY};movement();const p=local(e);zoomAt(Math.exp(-e.deltaY*.0015),p.x,p.y);},{passive:false});
  $("atlas").addEventListener("pointerdown",e=>{if(e.button!==0)return;const p=local(e);drag={x:p.x,y:p.y,tx,ty,cx:e.clientX,cy:e.clientY,id:e.pointerId};suppressClick=false;});
  $("atlas").addEventListener("pointermove",e=>{pointer={x:e.clientX,y:e.clientY};if(!drag)return;if(Math.hypot(e.clientX-drag.cx,e.clientY-drag.cy)>5){suppressClick=true;$("atlas").classList.add("dragging");$("atlas").setPointerCapture(e.pointerId);$("tooltip").hidden=true;const p=local(e);tx=drag.tx+p.x-drag.x;ty=drag.ty+p.y-drag.y;movement();scheduleTransform();}});
  const finish=()=>{drag=null;$("atlas").classList.remove("dragging");setTimeout(()=>{suppressClick=false;},0);};
  window.addEventListener("pointermove",e=>{pointer={x:e.clientX,y:e.clientY};});
  window.addEventListener("pointerup",finish);window.addEventListener("pointercancel",()=>{pointer=null;finish();});
  $("zoom-in").onclick=()=>zoomAt(1.5);$("zoom-out").onclick=()=>zoomAt(1/1.5);
  $("zoom-fit").onclick=()=>{zoom=1;tx=ty=0;labelsDirty=true;scheduleTransform();};
  $("layer").onchange=e=>{layer=e.target.value;recolor();};
  $("reset").onclick=()=>{compromised.clear();impact();};
  $("show-scenery").onchange=e=>{$("scenery").style.display=e.target.checked?"":"none";};
  $("show-links").onchange=()=>drawConnections(hovered);
  $("hops").oninput=e=>{$("hop-value").textContent=`${e.target.value} hop${e.target.value==1?"":"s"}`;drawConnections(hovered);};
  $("search").oninput=e=>{
    const query=e.target.value.trim().toLowerCase(),results=$("search-results");results.replaceChildren();results.hidden=!query;
    if(!query)return;
    const matches=projects.map((p,i)=>({p,i})).filter(({p})=>p.id.includes(query));
    for(const {p,i} of matches.slice(0,12)){const b=text(results,"button",p.id);b.onclick=()=>{inspect(i,true);results.hidden=true;$("search").value="";};}
    if(!matches.length)text(results,"p","No matching projects.","small");
  };
  $("search").onkeydown=e=>{if(e.key==="Escape"){$("search-results").hidden=true;}if(e.key==="ArrowDown"){$("search-results").querySelector("button")?.focus();e.preventDefault();}if(e.key==="Enter")$("search-results").querySelector("button")?.click();};
  $("try-project").onclick=()=>inspect(projects.reduce((best,p,i)=>p.exposure>projects[best].exposure?i:best,0),true);
  $("about-open").onclick=()=>$("about").showModal();$("about-close").onclick=()=>$("about").close();
  $("snapshot-label").textContent=`${projects.length} projects · Snapshot ${data.snapshot.slice(0,8).replace(/^(\d{4})(\d{2})(\d{2})$/,"$1-$2-$3")}`;
  $("scope-label").textContent=`Seed-only exposure · Up to 5 hops · ${data.gaps.toLocaleString()} evidence gaps`;
  window.addEventListener("scroll",()=>{inputMatrix=null;},{capture:true,passive:true});
  window.addEventListener("resize",()=>{inputMatrix=null;});
  new ResizeObserver(([entry])=>{
    viewportScale=Math.min(entry.contentRect.width/width,entry.contentRect.height/height);
    inputMatrix=null;labelsDirty=true;scheduleTransform();
  }).observe($("atlas"));
  recolor();impact();
  document.documentElement.dataset.mapReady="true";
})();
