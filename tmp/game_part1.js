// ============================================================
// 幻蝶星域 (Phantom Butterfly Nebula) v1.0
// HTML5 Canvas + Web Audio API
// 創新：蛻變進化 + 三元素花瓣武器 + 蟲群智能 + 季節波次 + 反射盾
// ============================================================
(function () {
"use strict";
var canvas = document.getElementById("gameCanvas");
var ctx = canvas.getContext("2d");
var W = canvas.width, H = canvas.height;

// ═══════ Audio ═══════
var audioCtx = null;
function ensureAudio() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === "suspended") audioCtx.resume();
}
function playTone(f, d, t, v) {
  if (!audioCtx) return;
  var o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.type = t || "square"; o.frequency.setValueAtTime(f, audioCtx.currentTime);
  g.gain.setValueAtTime(v || 0.05, audioCtx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + d);
  o.connect(g); g.connect(audioCtx.destination); o.start(); o.stop(audioCtx.currentTime + d);
}
function sfxPetal() { playTone(880, 0.06, "sine", 0.04); playTone(1320, 0.04, "sine", 0.03); }
function sfxBeam() { playTone(440, 0.12, "triangle", 0.05); playTone(660, 0.1, "sine", 0.04); }
function sfxSpore() { playTone(220, 0.15, "sawtooth", 0.04); playTone(330, 0.12, "triangle", 0.03); }
function sfxHit() { playTone(200, 0.08, "square", 0.06); }
function sfxDie() { playTone(150, 0.15, "sawtooth", 0.08); playTone(100, 0.2, "square", 0.06); }
function sfxBossDie() { playTone(60, 0.4, "sawtooth", 0.1); playTone(40, 0.5, "square", 0.08); }
function sfxPlrHit() { playTone(180, 0.3, "sawtooth", 0.08); playTone(90, 0.4, "triangle", 0.06); }
function sfxEvolve() { [523,659,784,1047,1319,1568].forEach(function(f,i) { setTimeout(function() { playTone(f,0.25,"triangle",0.08); }, i*100); }); }
function sfxPow() { playTone(523,0.15,"sine",0.06); playTone(659,0.15,"sine",0.05); playTone(784,0.15,"sine",0.04); }
function sfxWave() { [523,659,784,1047].forEach(function(f,i) { setTimeout(function() { playTone(f,0.15,"sine",0.06); }, i*120); }); }
function sfxBossWarn() { for (var i=0;i<4;i++) setTimeout(function() { playTone(110,0.25,"sawtooth",0.08); }, i*300); }
function sfxReflect() { playTone(1200,0.08,"sine",0.06); playTone(1800,0.06,"sine",0.05); }

// BGM
var bgmOn=false, bgmTmr=null, bgmBt=0;
var bgmB=[130.81,146.83,164.81,174.61,196], bgmM=[523.25,587.33,659.25,698.46,783.99,880,987.77];
var bgmBS=[0,0,2,2,3,3,4,2], bgmMS=[-1,4,-1,6,-1,5,-1,3,-1,6,-1,2,-1,4,-1,5];
function startBGM() { if(bgmOn||!audioCtx)return; bgmOn=true; bgmBt=0; tickBGM(); }
function stopBGM() { bgmOn=false; if(bgmTmr){clearTimeout(bgmTmr);bgmTmr=null;} }
function tickBGM() {
  if(!bgmOn||(gState!==ST.PLAY&&gState!==ST.BOSS)){bgmTmr=null;return;}
  var tp=Math.max(160,320-wave*6);
  playTone(bgmB[bgmBS[bgmBt%8]],tp/1000*0.7,"triangle",0.025);
  var m=bgmMS[bgmBt%16]; if(m>=0) playTone(bgmM[m],tp/1000*0.4,"sine",0.018);
  if(bgmBt%4===0) playTone(bgmB[bgmBS[bgmBt%8]]*3,tp/1000*0.3,"sine",0.012);
  bgmBt++; bgmTmr=setTimeout(tickBGM,tp);
}

// ═══════ States ═══════
var ST={TITLE:0,PLAY:1,PAUSE:2,WCLEAR:3,BOSS:4,GOVER:5};
var gState=ST.TITLE;

// ═══════ Seasons ═══════
var SEASONS=[
  {name:"春",bg1:"#0a0025",bg2:"#150835",neb:"rgba(255,150,200,0.06)",acc:"#ffaacc"},
  {name:"夏",bg1:"#001020",bg2:"#002035",neb:"rgba(100,255,150,0.06)",acc:"#66ffaa"},
  {name:"秋",bg1:"#150800",bg2:"#201005",neb:"rgba(255,180,80,0.07)",acc:"#ffcc66"},
  {name:"冬",bg1:"#080818",bg2:"#101030",neb:"rgba(150,200,255,0.06)",acc:"#aaddff"}
];
function season(){return SEASONS[(wave-1)%4];}

// ═══════ Weapons ═══════
var WEAP=[
  {name:"花暴風",col:"#ff88cc",gl:"#ffaadd",r:255,g:136,b:204},
  {name:"花蜜光束",col:"#88ffaa",gl:"#aaffcc",r:136,g:255,b:170},
  {name:"孢子雲",col:"#aa88ff",gl:"#ccaaff",r:170,g:136,b:255}
];
var wIdx=0;

// ═══════ Evolution Forms ═══════
var FORMS=[
  {name:"星蟲",thr:0,ws:14,sc:0.7,lives:3,bc:1,c1:"#88cc88",c2:"#44aa44",wc:"#66bb66",bt:"larva"},
  {name:"光蛹",thr:1500,ws:18,sc:0.85,lives:4,bc:1,c1:"#ccaa44",c2:"#ffdd66",wc:"#eebb33",bt:"pupa"},
  {name:"幻蝶",thr:4000,ws:28,sc:1.0,lives:5,bc:2,c1:"#cc66ff",c2:"#ff66cc",wc:"#dd88ff",bt:"fly"},
  {name:"帝王蝶",thr:10000,ws:36,sc:1.2,lives:6,bc:3,c1:"#ffaa00",c2:"#ff4488",wc:"#ffcc44",bt:"king"}
];
var fIdx=0, pollen=0, evolAnim=0;

// ═══════ Player ═══════
var px, py, pSpd=240, pLives=3, sCD=0, sRate=0.18;
var score=0, wave=1, hi=parseInt(localStorage.getItem("pbn_hi"))||0;
var invT=0, combo=0, comboT=0, comboM=1;
var shake=0, shakeI=0, spCharge=0, reflectT=0;

function resetP() {
  px=W/2; py=H-80; fIdx=0; pollen=0; pLives=FORMS[0].lives;
  score=0; wave=1; sCD=0; invT=0; wIdx=0; evolAnim=0;
  combo=0; comboT=0; comboM=1; shake=0; spCharge=0; reflectT=0;
}

// ═══════ Particles ═══════
var MP=500, parts=[];
for(var i=0;i<MP;i++) parts.push({on:false,x:0,y:0,vx:0,vy:0,life:0,ml:0,r:0,g:0,b:0,sz:2,tp:"sq",rot:0,rs:0,grav:0,fric:1});

function emitP(x,y,n,r,g,b,sp,li,opts) {
  opts=opts||{};var c=0;
  for(var i=0;i<MP&&c<n;i++){var p=parts[i];if(!p.on){
    p.on=true; p.x=x+(opts.spread||0)*(Math.random()-0.5); p.y=y+(opts.spread||0)*(Math.random()-0.5);
    var a=opts.angle!=null?opts.angle+(opts.as||Math.PI*2)*(Math.random()-0.5):Math.random()*Math.PI*2;
    var s=(sp||80)*(0.3+Math.random()*0.7);
    p.vx=Math.cos(a)*s; p.vy=Math.sin(a)*s;
    p.life=(li||0.5)*(0.6+Math.random()*0.4); p.ml=p.life;
    p.r=r+Math.floor((Math.random()-0.5)*(opts.cv||0));
    p.g=g+Math.floor((Math.random()-0.5)*(opts.cv||0));
    p.b=b+Math.floor((Math.random()-0.5)*(opts.cv||0));
    p.sz=(opts.size||2)+Math.random()*(opts.sv||1);
    p.tp=opts.type||"sq"; p.grav=opts.gravity||0; p.fric=opts.friction||1;
    p.rot=Math.random()*Math.PI*2; p.rs=(Math.random()-0.5)*5;
    c++;
  }}
}

function updParts(dt){for(var i=0;i<MP;i++){var p=parts[i];if(!p.on)continue;p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy+=p.grav*dt;p.vx*=p.fric;p.vy*=p.fric;p.rot+=p.rs*dt;p.life-=dt;if(p.life<=0)p.on=false;}}

function drawParts(){
  for(var i=0;i<MP;i++){var p=parts[i];if(!p.on)continue;
    var a=Math.max(0,p.life/p.ml), sz=p.sz*(0.5+a*0.5);
    ctx.save(); ctx.globalAlpha=a; ctx.translate(p.x,p.y);
    ctx.fillStyle="rgb("+p.r+","+p.g+","+p.b+")";
    if(p.tp==="ci"){ctx.beginPath();ctx.arc(0,0,sz,0,Math.PI*2);ctx.fill();}
    else if(p.tp==="pet"){ctx.rotate(p.rot);ctx.beginPath();ctx.ellipse(0,0,sz*0.5,sz*1.5,0,0,Math.PI*2);ctx.fill();}
    else if(p.tp==="star"){ctx.rotate(p.rot);drawStar5(0,0,sz,sz*0.4);}
    else{ctx.fillRect(-sz/2,-sz/2,sz,sz);}
    ctx.restore();
  }
}

function drawStar5(cx,cy,oR,iR){
  ctx.beginPath();
  for(var i=0;i<10;i++){var r=i%2===0?oR:iR,a=(i/10)*Math.PI*2-Math.PI/2;
    if(i===0)ctx.moveTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);
    else ctx.lineTo(cx+Math.cos(a)*r,cy+Math.sin(a)*r);}
  ctx.closePath();ctx.fill();
}
