// ═══════ Title / GameOver / WaveClear / Paused ═══════
function drawTitle(){
  ctx.save();var t=performance.now()/1000;
  glow("#cc66ff",25);ctx.fillStyle="#cc66ff";ctx.font="bold 34px Courier New";ctx.textAlign="center";
  ctx.fillText("\u5e7b\u8776\u661f\u57df",W/2,H/2-85);noGlow();
  ctx.fillStyle="#8888aa";ctx.font="13px Courier New";ctx.fillText("Phantom Butterfly Nebula",W/2,H/2-55);
  // Demo butterfly
  ctx.save();ctx.translate(W/2,H/2-145);var ds=0.8+Math.sin(t*2)*0.05;ctx.scale(ds,ds);
  var dws=22+Math.sin(t*3)*2,dwf=Math.sin(t*6)*0.3;
  for(var s=-1;s<=1;s+=2){
    var wg2=ctx.createLinearGradient(0,0,s*dws,0);wg2.addColorStop(0,"#cc66ff");wg2.addColorStop(1,"#ff66cc");
    glow("#cc66ff",15);ctx.fillStyle=wg2;ctx.beginPath();ctx.moveTo(2*s,-4);
    ctx.bezierCurveTo(s*dws*0.4,-18-dwf*10,s*dws*0.9,-14,s*dws,-3);
    ctx.bezierCurveTo(s*(dws+1),3,s*dws*0.6,7,s*dws*0.3,5);ctx.quadraticCurveTo(s*4,3,s*2,0);ctx.fill();
    ctx.fillStyle="#ff66cc88";ctx.beginPath();ctx.moveTo(2*s,2);
    ctx.bezierCurveTo(s*dws*0.3,4,s*dws*0.5,12,s*dws*0.4,14);ctx.quadraticCurveTo(s*dws*0.2,12,s*2,6);ctx.fill();
  }
  noGlow();ctx.fillStyle="#fff8e8";ctx.beginPath();ctx.ellipse(0,1,3,10,0,0,Math.PI*2);ctx.fill();
  ctx.restore();
  var al2=0.5+Math.sin(t*3)*0.5;ctx.fillStyle="rgba(200,150,255,"+al2+")";ctx.font="16px Courier New";
  ctx.fillText("\u6309\u4efb\u610f\u9375\u958b\u59cb",W/2,H/2+15);
  ctx.fillStyle="#666";ctx.font="11px Courier New";
  var ins=["\u2190 \u2192 \u79fb\u52d5  |  Space \u5c04\u64ca  |  E \u5207\u63db\u6b66\u5668",
    "\u4e09\u6b66\u5668\uff1a\u82b1\u66b4\u98a8(\u64f4\u6563) \u82b1\u871c\u5149\u675f(\u96c6\u4e2d) \u5b62\u5b50\u96f2(\u8ffd\u8e64)",
    "\u9032\u5316\uff1a\u661f\u87f2 \u2192 \u5149\u86f9 \u2192 \u5e7b\u8776 \u2192 \u5e1d\u738b\u8776",
    "\u6bcf4\u6ce2Boss | Q\u5927\u62db | \u53cd\u5c04\u76fe\u5f48\u56de\u6575\u5f48"];
  for(var i=0;i<ins.length;i++)ctx.fillText(ins[i],W/2,H/2+55+i*18);
  ctx.restore();
}

function drawGOver(){
  ctx.save();ctx.fillStyle="rgba(0,0,0,0.7)";ctx.fillRect(0,0,W,H);
  glow("#ff4444",15);ctx.fillStyle="#ff4444";ctx.font="bold 32px Courier New";ctx.textAlign="center";
  ctx.fillText("GAME OVER",W/2,H/2-50);noGlow();
  ctx.fillStyle="#ffd700";ctx.font="bold 22px Courier New";ctx.fillText("SCORE: "+score,W/2,H/2);
  if(score>=hi&&score>0){ctx.fillStyle="#ffaa00";ctx.font="14px Courier New";ctx.fillText("\u2605 NEW HIGH SCORE \u2605",W/2,H/2+28);}
  ctx.fillStyle="#aaa";ctx.font="13px Courier New";ctx.fillText("WAVE: "+wave+"  |  "+FORMS[fIdx].name,W/2,H/2+55);
  var al3=0.5+Math.sin(performance.now()/1000*3)*0.5;ctx.fillStyle="rgba(200,150,255,"+al3+")";ctx.font="14px Courier New";
  ctx.fillText("\u6309 Space \u91cd\u65b0\u958b\u59cb",W/2,H/2+95);ctx.restore();
}

function drawWClear(){
  ctx.save();var s=season();glow(s.acc,20);ctx.fillStyle=s.acc;ctx.font="bold 28px Courier New";ctx.textAlign="center";
  ctx.fillText(s.name+" WAVE "+wave+" CLEAR!",W/2,H/2-20);noGlow();
  ctx.fillStyle="#aaa";ctx.font="14px Courier New";
  ctx.fillText((wave+1)%4===0?"\u26a0 Boss \u5373\u5c07\u73fe\u8eab...":SEASONS[wave%4].name+" \u5373\u5c07\u4f86\u81e8...",W/2,H/2+20);
  ctx.restore();
}

function drawPaused(){
  ctx.save();ctx.fillStyle="rgba(0,0,0,0.5)";ctx.fillRect(0,0,W,H);
  ctx.fillStyle="#fff";ctx.font="bold 24px Courier New";ctx.textAlign="center";ctx.fillText("PAUSED",W/2,H/2);
  ctx.fillStyle="#aaa";ctx.font="12px Courier New";ctx.fillText("\u6309 P \u6216 ESC \u7e7c\u7e8c",W/2,H/2+30);ctx.restore();
}

// ═══════ Main Loop ═══════
var lastT=0;
function loop(ts){
  requestAnimationFrame(loop);var dt=Math.min(0.05,(ts-lastT)/1000);lastT=ts;
  ctx.save();
  if(shake>0){shake-=dt;var sx2=(Math.random()-0.5)*shakeI*shake*10,sy4=(Math.random()-0.5)*shakeI*shake*10;ctx.translate(sx2,sy4);}
  drawBG();updStars(dt);
  if(gState===ST.TITLE){drawTitle();ctx.restore();return;}
  if(gState===ST.PAUSE){drawAllObj();drawHUD();drawPaused();ctx.restore();return;}
  if(gState===ST.GOVER){drawAllObj();drawGOver();ctx.restore();return;}
  if(gState===ST.WCLEAR){updParts(dt);drawParts();drawPlayer(px,py);drawHUD();drawFlts(dt);drawPolDrps();updPollen(dt);drawWClear();ctx.restore();return;}
  // Playing / Boss
  if(keys["ArrowLeft"]||keys["KeyA"])px-=pSpd*dt;if(keys["ArrowRight"]||keys["KeyD"])px+=pSpd*dt;
  px=Math.max(20,Math.min(W-20,px));if(keys["Space"])playerShoot();
  sCD=Math.max(0,sCD-dt);invT=Math.max(0,invT-dt);if(evolAnim>0)evolAnim-=dt;if(reflectT>0)reflectT-=dt;
  if(comboT>0){comboT-=dt;if(comboT<=0){combo=0;comboM=1;}}
  spCharge=Math.min(100,spCharge+dt*2);
  updBullets(dt);updParts(dt);updPollen(dt);updPows(dt);
  if(boss&&boss.alive)updBoss(dt);else if(gState!==ST.BOSS)updEnemies(dt);
  if(gState===ST.PLAY&&enemies.length>0&&enemies.every(function(e){return !e.alive;}))waveTrans();
  checkColl();drawAllObj();drawEvoFlash();drawHUD();drawFlts(dt);
  ctx.restore();
}
requestAnimationFrame(loop);
})();
