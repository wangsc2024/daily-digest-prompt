// ═══════ Draw Enemies ═══════
function drawEnemy(e){
  var t=performance.now()/1000;
  ctx.save();ctx.translate(e.x+e.w/2,e.y+e.h/2);
  if(e.hf>0){ctx.fillStyle="#fff";ctx.fillRect(-e.w/2,-e.h/2,e.w,e.h);ctx.restore();return;}
  glow(e.gl,8);

  if(e.df==="moth"){
    var wf2=Math.sin(t*8+e.ph)*0.3;
    ctx.fillStyle=e.col;
    for(var s=-1;s<=1;s+=2){ctx.beginPath();ctx.moveTo(0,-2);ctx.quadraticCurveTo(s*14,-10+wf2*s*8,s*12,2);ctx.quadraticCurveTo(s*8,6,0,3);ctx.fill();}
    ctx.fillStyle="#ddd";ctx.beginPath();ctx.ellipse(0,0,3,6,0,0,Math.PI*2);ctx.fill();
    ctx.fillStyle="#ff4444";ctx.beginPath();ctx.arc(-2,-3,1.5,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(2,-3,1.5,0,Math.PI*2);ctx.fill();
  } else if(e.df==="beetle"){
    ctx.fillStyle=e.col;ctx.beginPath();ctx.moveTo(0,-e.h/2);ctx.bezierCurveTo(e.w/2,-e.h/3,e.w/2,e.h/3,0,e.h/2);ctx.bezierCurveTo(-e.w/2,e.h/3,-e.w/2,-e.h/3,0,-e.h/2);ctx.fill();
    ctx.strokeStyle="rgba(255,255,255,0.3)";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,-e.h/2+3);ctx.lineTo(0,e.h/2-3);ctx.stroke();
    if(Math.sin(t*10+e.ph)>0.5){ctx.strokeStyle="#ffff88";ctx.lineWidth=1;
      for(var sk=0;sk<3;sk++){var sa2=e.ph+sk*2.1+t*5,sx2=Math.cos(sa2)*(e.w/2+3),sy3=Math.sin(sa2)*(e.h/2+2);
        ctx.beginPath();ctx.moveTo(sx2,sy3);ctx.lineTo(sx2+(Math.random()-0.5)*6,sy3+(Math.random()-0.5)*6);ctx.stroke();}}
    ctx.fillStyle="#ffff44";ctx.beginPath();ctx.arc(-4,-2,2,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(4,-2,2,0,Math.PI*2);ctx.fill();
  } else if(e.df==="scorp"){
    ctx.fillStyle=e.col;ctx.beginPath();ctx.ellipse(0,2,e.w/2-4,e.h/2-4,0,0,Math.PI*2);ctx.fill();
    for(var s=-1;s<=1;s+=2){ctx.beginPath();ctx.moveTo(s*6,-4);ctx.quadraticCurveTo(s*16,-10,s*14,-2);ctx.quadraticCurveTo(s*15,2,s*10,0);ctx.fill();}
    var tw2=Math.sin(t*3+e.ph)*5;
    ctx.strokeStyle=e.col;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(0,-6);ctx.quadraticCurveTo(tw2,-18,tw2*0.5,-22);ctx.stroke();
    ctx.fillStyle="#ffcc00";ctx.beginPath();ctx.arc(tw2*0.5,-23,3,0,Math.PI*2);ctx.fill();
    ctx.fillStyle="#ff0000";ctx.beginPath();ctx.arc(-4,0,2,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(4,0,2,0,Math.PI*2);ctx.fill();
  } else if(e.df==="phmoth"){
    var ga2=0.6+Math.sin(t*4+e.ph)*0.2;ctx.globalAlpha=ga2;ctx.fillStyle=e.col;
    for(var s=-1;s<=1;s+=2){var wf3=Math.sin(t*6+e.ph)*4;ctx.beginPath();ctx.moveTo(0,-3);ctx.bezierCurveTo(s*8,-14+wf3,s*16,-8,s*14,4);ctx.bezierCurveTo(s*10,10,s*4,8,0,4);ctx.fill();
      ctx.fillStyle="rgba(255,255,255,0.2)";ctx.beginPath();ctx.ellipse(s*7,-2,4,5,0,0,Math.PI*2);ctx.fill();ctx.fillStyle=e.col;}
    ctx.globalAlpha=1;ctx.fillStyle="#eef";ctx.beginPath();ctx.ellipse(0,0,3,7,0,0,Math.PI*2);ctx.fill();
    glow(e.col,12);ctx.fillStyle=e.col;ctx.beginPath();ctx.arc(-2,-4,2,0,Math.PI*2);ctx.fill();ctx.beginPath();ctx.arc(2,-4,2,0,Math.PI*2);ctx.fill();
  } else if(e.df==="spider"){
    ctx.fillStyle=e.col;ctx.beginPath();ctx.ellipse(0,4,10,8,0,0,Math.PI*2);ctx.fill();
    ctx.beginPath();ctx.arc(0,-6,6,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle=e.col;ctx.lineWidth=1.5;
    for(var lg=0;lg<4;lg++){for(var s=-1;s<=1;s+=2){
      var lw2=Math.sin(t*5+lg+e.ph)*2;
      ctx.beginPath();ctx.moveTo(s*5,-2+lg*3);ctx.quadraticCurveTo(s*(12+lg*2),-4+lg*4+lw2,s*(14+lg),lg*5+lw2);ctx.stroke();}}
    ctx.fillStyle="#ff2222";for(var ey=0;ey<4;ey++){ctx.beginPath();ctx.arc((ey-1.5)*2.5,-7,1.2,0,Math.PI*2);ctx.fill();}
    ctx.strokeStyle="rgba(255,255,255,0.15)";ctx.lineWidth=0.5;ctx.beginPath();ctx.arc(0,4,6,0,Math.PI*2);ctx.stroke();
  }

  if(e.mhp>1){noGlow();var bw2=e.w-4;ctx.fillStyle="rgba(255,0,0,0.4)";ctx.fillRect(-bw2/2,e.h/2+4,bw2,3);ctx.fillStyle="rgba(0,255,100,0.7)";ctx.fillRect(-bw2/2,e.h/2+4,bw2*(e.hp/e.mhp),3);}
  noGlow();ctx.restore();
}

// ═══════ Draw Boss ═══════
function drawBoss(b){
  if(!b||!b.alive)return;var t=performance.now()/1000;
  ctx.save();ctx.translate(b.x+b.w/2,b.y+b.h/2);
  if(b.hf>0){glow("#fff",25);ctx.fillStyle="#fff";ctx.fillRect(-b.w/2,-b.h/2,b.w,b.h);noGlow();ctx.restore();return;}
  var ar2=b.w*0.75+Math.sin(t*2)*8;glow(b.c1,30);
  ctx.strokeStyle=b.c1+"33";ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,0,ar2,0,Math.PI*2);ctx.stroke();
  if(b.enraged){ctx.strokeStyle="#ff000044";ctx.lineWidth=3;ctx.beginPath();ctx.arc(0,0,ar2+10,0,Math.PI*2);ctx.stroke();}
  var bg3=ctx.createRadialGradient(0,0,0,0,0,b.w/2);bg3.addColorStop(0,b.c2);bg3.addColorStop(0.5,b.c1);bg3.addColorStop(1,"#000");ctx.fillStyle=bg3;
  ctx.beginPath();var sc2=10+(b.enraged?4:0);
  for(var i=0;i<sc2*2;i++){var a2=(i/(sc2*2))*Math.PI*2+t*0.3,r2=i%2===0?b.w/2:b.w/3;
    if(b.enraged&&i%2===0)r2+=Math.sin(t*8+i)*3;ctx.lineTo(Math.cos(a2)*r2,Math.sin(a2)*r2);}
  ctx.closePath();ctx.fill();
  // Core eye
  glow(b.c2,15);ctx.fillStyle=b.c2;ctx.beginPath();ctx.arc(0,0,14,0,Math.PI*2);ctx.fill();
  ctx.fillStyle="#000";ctx.beginPath();ctx.arc(0,0,7,0,Math.PI*2);ctx.fill();
  glow("#fff",8);ctx.fillStyle="#fff";ctx.beginPath();ctx.arc(3,-3,3.5,0,Math.PI*2);ctx.fill();
  // HP
  noGlow();var hw=b.w+30,hr=b.hp/b.mhp,hc=hr>0.5?"#44ff88":hr>0.25?"#ffaa44":"#ff4444";
  ctx.fillStyle="rgba(60,0,0,0.7)";ctx.fillRect(-hw/2,b.h/2+10,hw,7);
  ctx.fillStyle=hc;ctx.fillRect(-hw/2,b.h/2+10,hw*hr,7);
  ctx.fillStyle=hc+"88";ctx.fillRect(-hw/2,b.h/2+10,hw*hr,3);
  ctx.fillStyle=b.c1;ctx.font="bold 12px Courier New";ctx.textAlign="center";
  ctx.fillText(b.name+(b.enraged?" [狂暴]":""),0,-b.h/2-12);
  noGlow();ctx.restore();
}

// ═══════ Draw Bullets ═══════
function drawBullet(b){
  ctx.save();
  if(b.ow==="p"){
    glow(b.wp.gl,10);ctx.fillStyle=b.wp.col;
    if(b.aoe>0){ctx.beginPath();ctx.arc(b.x,b.y,b.sz*1.2,0,Math.PI*2);ctx.fill();
      ctx.fillStyle=b.wp.col+"44";ctx.beginPath();ctx.arc(b.x,b.y,b.sz*2,0,Math.PI*2);ctx.fill();}
    else{ctx.beginPath();ctx.ellipse(b.x,b.y,b.sz*0.5,b.sz*1.5,Math.atan2(b.vy,b.vx)+Math.PI/2,0,Math.PI*2);ctx.fill();
      ctx.fillStyle=b.wp.col+"33";ctx.beginPath();ctx.ellipse(b.x-b.vx*0.01,b.y-b.vy*0.01,b.sz*0.3,b.sz*2.5,Math.atan2(b.vy,b.vx)+Math.PI/2,0,Math.PI*2);ctx.fill();}
  } else {
    glow("#ff4466",6);ctx.fillStyle="#ff4466";ctx.beginPath();ctx.arc(b.x,b.y,b.sz,0,Math.PI*2);ctx.fill();
  }
  noGlow();ctx.restore();
}
