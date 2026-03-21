// ═══════ Draw Player ═══════
function drawPlayer(x,y){
  var form=FORMS[fIdx], wp=WEAP[wIdx], t=performance.now()/1000;
  var br=Math.sin(t*3)*2, wf=Math.sin(t*6)*0.3;

  // Trail
  trailH.unshift({x:x,y:y});while(trailH.length>MAX_TR)trailH.pop();
  for(var i=trailH.length-1;i>0;i--){
    var ta=(1-i/trailH.length)*0.35, ts=(1-i/trailH.length)*6*form.sc;
    ctx.fillStyle="rgba("+wp.r+","+wp.g+","+wp.b+","+ta+")";
    ctx.beginPath();ctx.arc(trailH[i].x,trailH[i].y+8,ts,0,Math.PI*2);ctx.fill();
  }

  ctx.save();ctx.translate(x,y);
  if(invT>0&&Math.floor(invT*10)%2===0)ctx.globalAlpha=0.4;

  // Reflect shield visual
  if(reflectT>0){
    glow("#88ffff",20);ctx.strokeStyle="rgba(136,255,255,"+(0.3+Math.sin(t*8)*0.2)+")";
    ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,form.ws+12,0,Math.PI*2);ctx.stroke();noGlow();
  }

  if(form.bt==="larva"){
    // Star Larva
    glow(form.wc,10);
    for(var seg=3;seg>=0;seg--){
      var sy2=seg*6-3, sr=6-seg*0.8, sa=1-seg*0.15;
      var gr=ctx.createRadialGradient(0,sy2,0,0,sy2,sr+2);
      gr.addColorStop(0,form.c2);gr.addColorStop(1,form.c1);ctx.fillStyle=gr;
      ctx.globalAlpha=(invT>0&&Math.floor(invT*10)%2===0)?0.4*sa:sa;
      ctx.beginPath();ctx.ellipse(0,sy2,sr,sr*0.8,0,0,Math.PI*2);ctx.fill();
    }
    ctx.globalAlpha=1;
    ctx.strokeStyle=form.c2;ctx.lineWidth=1.5;
    ctx.beginPath();ctx.moveTo(-3,-8);ctx.quadraticCurveTo(-8,-16+br,-6,-18);ctx.stroke();
    ctx.beginPath();ctx.moveTo(3,-8);ctx.quadraticCurveTo(8,-16+br,6,-18);ctx.stroke();
    ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(-3,-5,2,0,Math.PI*2);ctx.fill();
    ctx.beginPath();ctx.arc(3,-5,2,0,Math.PI*2);ctx.fill();
    ctx.fillStyle="#222";ctx.beginPath();ctx.arc(-3,-5,1,0,Math.PI*2);ctx.fill();
    ctx.beginPath();ctx.arc(3,-5,1,0,Math.PI*2);ctx.fill();

  } else if(form.bt==="pupa"){
    // Light Pupa
    glow(form.wc,15);
    var pg=ctx.createRadialGradient(0,0,0,0,0,16);
    pg.addColorStop(0,"#fff8e0");pg.addColorStop(0.4,form.c2);pg.addColorStop(1,form.c1);
    ctx.fillStyle=pg;ctx.beginPath();ctx.ellipse(0,0,10,16,0,0,Math.PI*2);ctx.fill();
    var pu=0.3+Math.sin(t*4)*0.2;
    ctx.fillStyle="rgba(255,255,240,"+pu+")";
    ctx.beginPath();ctx.ellipse(0,-2,6,10,0,0,Math.PI*2);ctx.fill();
    var wh=Math.sin(t*2)*3;
    ctx.strokeStyle=form.c2+"88";ctx.lineWidth=2;
    ctx.beginPath();ctx.moveTo(-8,-4);ctx.quadraticCurveTo(-16-wh,-10+br,-14,5);ctx.stroke();
    ctx.beginPath();ctx.moveTo(8,-4);ctx.quadraticCurveTo(16+wh,-10+br,14,5);ctx.stroke();
    glow("#fff",8);ctx.fillStyle="#fff";
    ctx.beginPath();ctx.arc(0,-14,2+Math.sin(t*5)*0.5,0,Math.PI*2);ctx.fill();

  } else {
    // Butterfly / Monarch
    var ws=form.ws+br, isK=form.bt==="king";
    drawWings(ws,wf,form,wp,t,isK);
  }

  noGlow();ctx.restore();
  if(Math.random()<0.25) emitP(x+(Math.random()-0.5)*20,y+(Math.random()-0.5)*15,1,wp.r,wp.g,wp.b,15,0.4,{type:fIdx>=2?"pet":"ci",size:1.5});
}

function drawWings(ws,wf,form,wp,t,isK){
  // Upper wings
  for(var side=-1;side<=1;side+=2){
    ctx.save();ctx.scale(side,1);
    var wg=ctx.createLinearGradient(0,-10,ws,5);
    wg.addColorStop(0,form.c1);wg.addColorStop(0.5,form.wc);wg.addColorStop(1,form.c2);
    glow(form.wc,isK?20:12);ctx.fillStyle=wg;
    ctx.beginPath();ctx.moveTo(3,-5);
    ctx.bezierCurveTo(ws*0.4,-22-wf*10,ws*0.9,-18,ws,-5);
    ctx.bezierCurveTo(ws+2,2,ws*0.7,8,ws*0.4,6);
    ctx.bezierCurveTo(ws*0.2,4,5,2,3,0);ctx.closePath();ctx.fill();
    // Iridescent spots
    var spc=isK?5:3;
    for(var sp=0;sp<spc;sp++){
      var spx2=8+sp*(ws-10)/spc, spy2=-6+Math.sin(sp*1.5)*4, spR=isK?3.5:2.5;
      ctx.fillStyle="rgba(255,255,255,"+(0.2+Math.sin(t*3+sp)*0.15)+")";
      ctx.beginPath();ctx.arc(spx2,spy2,spR,0,Math.PI*2);ctx.fill();
    }
    // Wing veins
    ctx.strokeStyle="rgba(255,255,255,0.12)";ctx.lineWidth=0.8;
    ctx.beginPath();ctx.moveTo(5,-2);ctx.quadraticCurveTo(ws*0.5,-12,ws*0.8,-8);ctx.stroke();
    ctx.beginPath();ctx.moveTo(5,0);ctx.quadraticCurveTo(ws*0.5,2,ws*0.7,4);ctx.stroke();
    // Lower wing
    ctx.fillStyle=form.c2+"cc";ctx.beginPath();ctx.moveTo(3,2);
    ctx.bezierCurveTo(ws*0.3,5,ws*0.6,12+wf*5,ws*0.5,16);
    ctx.bezierCurveTo(ws*0.3,18,ws*0.1,14,3,8);ctx.closePath();ctx.fill();
    // Monarch tail
    if(isK){
      ctx.fillStyle=form.c2;ctx.beginPath();ctx.moveTo(ws*0.4,14);
      ctx.quadraticCurveTo(ws*0.5,22+Math.sin(t*4)*3,ws*0.35,24);
      ctx.quadraticCurveTo(ws*0.25,20,ws*0.3,14);ctx.fill();
      ctx.strokeStyle="rgba(255,200,50,0.4)";ctx.lineWidth=1.5;
      ctx.beginPath();ctx.moveTo(3,-5);
      ctx.bezierCurveTo(ws*0.4,-22,ws*0.9,-18,ws,-5);
      ctx.bezierCurveTo(ws+2,2,ws*0.7,8,ws*0.4,6);ctx.stroke();
    }
    ctx.restore();
  }
  // Body
  noGlow();var bg2=ctx.createLinearGradient(0,-12,0,15);
  bg2.addColorStop(0,"#fff8e8");bg2.addColorStop(0.5,form.c1);bg2.addColorStop(1,form.c2);
  ctx.fillStyle=bg2;ctx.beginPath();ctx.ellipse(0,2,4,12,0,0,Math.PI*2);ctx.fill();
  // Head
  glow(form.c1,8);ctx.fillStyle="#fff8e8";ctx.beginPath();ctx.arc(0,-10,4,0,Math.PI*2);ctx.fill();
  // Antennae
  ctx.strokeStyle=form.c1;ctx.lineWidth=1.5;var aw=Math.sin(t*4)*3;
  ctx.beginPath();ctx.moveTo(-2,-13);ctx.quadraticCurveTo(-10,-24+aw,-8,-28);ctx.stroke();
  ctx.beginPath();ctx.moveTo(2,-13);ctx.quadraticCurveTo(10,-24-aw,8,-28);ctx.stroke();
  ctx.fillStyle=wp.col;ctx.beginPath();ctx.arc(-8,-28,2,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.arc(8,-28,2,0,Math.PI*2);ctx.fill();
  // Eyes
  ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(-2,-11,1.8,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.arc(2,-11,1.8,0,Math.PI*2);ctx.fill();
  ctx.fillStyle=wp.col;ctx.beginPath();ctx.arc(-2,-11,0.9,0,Math.PI*2);ctx.fill();
  ctx.beginPath();ctx.arc(2,-11,0.9,0,Math.PI*2);ctx.fill();
}
