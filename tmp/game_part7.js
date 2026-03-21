// ═══════ Input ═══════
var keys={};
document.addEventListener("keydown",function(e){keys[e.code]=true;
  if(e.code==="Space"||e.code==="ArrowUp"||e.code==="ArrowDown")e.preventDefault();
  if(gState===ST.TITLE){ensureAudio();startGame();}
  else if(gState===ST.GOVER&&e.code==="Space")startGame();
  else if((gState===ST.PLAY||gState===ST.BOSS)&&e.code==="KeyE"){wIdx=(wIdx+1)%3;}
  else if(e.code==="KeyQ")useSpecial();
  else if(e.code==="KeyP"||e.code==="Escape"){
    if(gState===ST.PLAY||gState===ST.BOSS)gState=ST.PAUSE;else if(gState===ST.PAUSE)gState=ST.PLAY;}
});
document.addEventListener("keyup",function(e){keys[e.code]=false;});

function setupTouch(id,code){var el=document.getElementById(id);if(!el)return;
  el.addEventListener("touchstart",function(e){e.preventDefault();keys[code]=true;if(gState===ST.TITLE){ensureAudio();startGame();}});
  el.addEventListener("touchend",function(e){e.preventDefault();keys[code]=false;});
  el.addEventListener("touchcancel",function(){keys[code]=false;});}
setupTouch("btnLeft","ArrowLeft");setupTouch("btnRight","ArrowRight");setupTouch("btnFire","Space");

var btnW2=document.getElementById("btnWeapon");
if(btnW2)btnW2.addEventListener("touchstart",function(e){e.preventDefault();wIdx=(wIdx+1)%3;btnW2.style.color=WEAP[wIdx].col;});
var btnP2=document.getElementById("btnPause");
if(btnP2)btnP2.addEventListener("touchstart",function(e){e.preventDefault();
  if(gState===ST.PLAY||gState===ST.BOSS)gState=ST.PAUSE;else if(gState===ST.PAUSE)gState=ST.PLAY;});

// ═══════ Game Flow ═══════
function startGame(){
  resetP();bulls.forEach(function(b){b.on=false;});parts.forEach(function(p){p.on=false;});
  plDrp.forEach(function(p){p.on=false;});flts.forEach(function(f){f.on=false;});
  pows.forEach(function(p){p.on=false;});trailH.length=0;boss=null;nebCvs=null;
  createWave(1);gState=ST.PLAY;startBGM();
}

// ═══════ Rendering ═══════
function drawBG(){if(!nebCvs)initNeb();ctx.drawImage(nebCvs,0,0);
  var t=performance.now()/1000;
  for(var i=0;i<stars.length;i++){var s=stars[i];var a=s.br*(0.6+0.4*Math.sin(t*s.tw+s.x));ctx.fillStyle="rgba(255,255,255,"+a+")";ctx.fillRect(s.x,s.y,s.sz,s.sz);}
}
function updStars(dt){for(var i=0;i<stars.length;i++){var s=stars[i];s.y+=s.spd*dt;if(s.y>H){s.y=-2;s.x=Math.random()*W;}}}

function drawHUD(){
  ctx.save();noGlow();var s=season();
  ctx.fillStyle=s.acc;ctx.font="bold 16px Courier New";ctx.textAlign="left";ctx.fillText("SCORE "+score,10,22);
  ctx.fillStyle="#777";ctx.font="11px Courier New";ctx.fillText("HI "+hi,10,38);
  ctx.fillStyle="#aaa";ctx.textAlign="center";ctx.font="bold 13px Courier New";ctx.fillText(s.name+" WAVE "+wave,W/2,22);
  ctx.textAlign="right";ctx.fillStyle="#ff6688";ctx.font="14px Courier New";
  var ls="";for(var i=0;i<pLives;i++)ls+="\u2665 ";ctx.fillText(ls,W-10,22);
  var wp=WEAP[wIdx];ctx.fillStyle=wp.col;ctx.font="bold 12px Courier New";ctx.textAlign="right";ctx.fillText("[ "+wp.name+" ] E\u5207\u63db",W-10,38);
  // Evo bar
  var nf=FORMS[fIdx+1];
  if(nf){var bw3=130,bx3=W/2-bw3/2,by3=32,pr=Math.min(1,pollen/nf.thr);
    ctx.fillStyle="rgba(255,255,255,0.1)";ctx.fillRect(bx3,by3,bw3,6);
    var eg=ctx.createLinearGradient(bx3,0,bx3+bw3,0);eg.addColorStop(0,FORMS[fIdx].c1);eg.addColorStop(1,nf.c1);
    ctx.fillStyle=eg;ctx.fillRect(bx3,by3,bw3*pr,6);
    ctx.fillStyle="#aaa";ctx.font="9px Courier New";ctx.textAlign="center";
    ctx.fillText(FORMS[fIdx].name+" \u2192 "+nf.name,W/2,by3+16);
  } else {ctx.fillStyle="#ffdd00";ctx.font="10px Courier New";ctx.textAlign="center";ctx.fillText("\u2605 "+FORMS[fIdx].name+" (MAX) \u2605",W/2,48);}
  if(comboM>1){ctx.fillStyle="rgba(255,100,255,"+Math.min(1,comboT)+")";ctx.font="bold 14px Courier New";ctx.textAlign="left";ctx.fillText(comboM+"x COMBO",10,56);}
  // SP bar
  ctx.fillStyle="rgba(255,255,255,0.1)";ctx.fillRect(10,H-25,80,8);
  ctx.fillStyle=spCharge>=100?"#ffdd00":"#4488ff";ctx.fillRect(10,H-25,80*(spCharge/100),8);
  ctx.fillStyle="#aaa";ctx.font="9px Courier New";ctx.textAlign="left";ctx.fillText("SP [Q]",10,H-28);
  ctx.restore();
}

function drawFlts(dt){for(var i=0;i<MFT;i++){var f=flts[i];if(!f.on)continue;f.y-=35*dt;f.life-=dt;
  if(f.life<=0){f.on=false;continue;}ctx.save();ctx.globalAlpha=Math.min(1,f.life);ctx.fillStyle=f.col;
  ctx.font="bold "+Math.floor(13*f.sc)+"px Courier New";ctx.textAlign="center";ctx.fillText(f.txt,f.x,f.y);ctx.restore();}}

function drawPolDrps(){var t=performance.now()/1000;
  for(var i=0;i<MPL;i++){var p=plDrp[i];if(!p.on)continue;
    if(p.tp==="pol"){var pu2=0.6+Math.sin(t*8+p.x)*0.3;glow("#ffdd00",8);ctx.fillStyle="rgba(255,220,50,"+pu2+")";
      ctx.beginPath();for(var pt=0;pt<6;pt++){var a7=(pt*60-90+t*60)*Math.PI/180;ctx.lineTo(p.x+Math.cos(a7)*4,p.y+Math.sin(a7)*4);
        var ia2=((pt*60+30)-90+t*60)*Math.PI/180;ctx.lineTo(p.x+Math.cos(ia2)*2,p.y+Math.sin(ia2)*2);}ctx.closePath();ctx.fill();
    } else {glow("#88ffff",12);ctx.fillStyle="rgba(136,255,255,"+(0.5+Math.sin(t*6)*0.3)+")";
      ctx.beginPath();ctx.arc(p.x,p.y,5,0,Math.PI*2);ctx.fill();}
    noGlow();}
}

function drawPows(){var t=performance.now()/1000;
  for(var i=0;i<MPW;i++){var p=pows[i];if(!p.on)continue;var bob=Math.sin(t*4+p.x)*2;ctx.save();ctx.translate(p.x,p.y+bob);
    var cols2={shield:"#88ffff",rapid:"#ffaa44",heal:"#ff66aa",bomb:"#ffdd00"};
    var icons={shield:"\u25c8",rapid:"\u26a1",heal:"\u2665",bomb:"\u2604"};
    var col2=cols2[p.tp]||"#fff";glow(col2,10);
    ctx.fillStyle=col2+"44";ctx.beginPath();ctx.arc(0,0,12,0,Math.PI*2);ctx.fill();
    ctx.fillStyle=col2;ctx.font="bold 14px Courier New";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(icons[p.tp],0,0);
    noGlow();ctx.restore();}
}

function drawEvoFlash(){if(evolAnim<=0)return;var a=Math.min(1,evolAnim*0.4);ctx.fillStyle="rgba(255,255,200,"+a*0.3+")";ctx.fillRect(0,0,W,H);}

function drawAllObj(){
  for(var i=0;i<enemies.length;i++)if(enemies[i].alive)drawEnemy(enemies[i]);
  if(boss&&boss.alive)drawBoss(boss);drawPolDrps();drawPows();
  for(var i=0;i<MB;i++)if(bulls[i].on)drawBullet(bulls[i]);
  drawPlayer(px,py);drawParts();
}
