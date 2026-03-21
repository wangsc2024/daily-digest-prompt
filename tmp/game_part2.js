// ═══════ Trail / Bullets / Pollen / FloatText ═══════
var trailH=[], MAX_TR=20;

var MB=80, bulls=[];
for(var i=0;i<MB;i++) bulls.push({on:false,x:0,y:0,vx:0,vy:0,ow:"p",wp:null,sz:3,dmg:1,prc:false,life:5,home:false,aoe:0});

function fireB(x,y,vx,vy,ow,wp,sz,dmg,opts){
  opts=opts||{};
  for(var i=0;i<MB;i++){var b=bulls[i];if(!b.on){
    b.on=true;b.x=x;b.y=y;b.vx=vx;b.vy=vy;b.ow=ow;b.wp=wp||WEAP[wIdx];
    b.sz=sz||3;b.dmg=dmg||1;b.prc=opts.pierce||false;b.life=opts.life||5;
    b.home=opts.homing||false;b.aoe=opts.aoe||0;return true;}}return false;
}

var MPL=40, plDrp=[];
for(var i=0;i<MPL;i++) plDrp.push({on:false,x:0,y:0,vy:0,val:0,t:0,tp:"pol"});

function spawnPol(x,y,v,tp){
  for(var i=0;i<MPL;i++){var p=plDrp[i];if(!p.on){
    p.on=true;p.x=x;p.y=y;p.vy=30+Math.random()*25;p.val=v;p.t=0;p.tp=tp||"pol";return;}}
}

var MFT=20, flts=[];
for(var i=0;i<MFT;i++) flts.push({on:false,x:0,y:0,txt:"",life:0,col:"#fff",sc:1});

function spawnFlt(x,y,txt,col,sc){
  for(var i=0;i<MFT;i++){var f=flts[i];if(!f.on){
    f.on=true;f.x=x;f.y=y;f.txt=txt;f.life=1.5;f.col=col||"#ffdd00";f.sc=sc||1;return;}}
}

// ═══════ Enemy Types ═══════
var ET=[
  {name:"蛾蟲",hp:1,sc:10,w:24,h:20,pv:5,col:"#88ff88",gl:"#44cc44",df:"moth"},
  {name:"螢甲",hp:2,sc:20,w:28,h:24,pv:10,col:"#ff88ff",gl:"#cc44cc",df:"beetle"},
  {name:"毒蠍",hp:3,sc:40,w:30,h:26,pv:20,col:"#ff6644",gl:"#cc3322",df:"scorp"},
  {name:"幻蛾",hp:2,sc:30,w:26,h:22,pv:15,col:"#44ddff",gl:"#22aacc",df:"phmoth"},
  {name:"織蛛",hp:4,sc:50,w:32,h:28,pv:25,col:"#ffaa44",gl:"#cc8822",df:"spider"}
];

var enemies=[], eDirX=1, eSpd=25, eShootT=0, eMoveT=0, eMoveStep=0.7, fmtOff=0, fmtType=0;

function createWave(wn){
  enemies=[]; var rows=Math.min(5,3+Math.floor(wn/3)), cols=Math.min(9,6+Math.floor(wn/3));
  eSpd=25+wn*4; eMoveStep=Math.max(0.25,0.7-wn*0.03); eDirX=1; eMoveT=0; eShootT=0;
  fmtType=wn%5; fmtOff=0;
  var sx=(W-cols*44)/2+10, sy=55;
  for(var r=0;r<rows;r++){
    var ti=Math.min(r,ET.length-1);
    if(wn>6)ti=Math.min(ti+1,ET.length-1);
    var et=ET[ti];
    for(var c=0;c<cols;c++){
      enemies.push({alive:true,x:sx+c*44,y:sy+r*36,bx:sx+c*44,by:sy+r*36,
        w:et.w,h:et.h,hp:et.hp+Math.floor(wn/4),mhp:et.hp+Math.floor(wn/4),
        type:ti,sc:et.sc+wn*2,pv:et.pv,col:et.col,gl:et.gl,hf:0,ph:Math.random()*Math.PI*2,df:et.df});
    }
  }
}

// ═══════ Boss ═══════
var boss=null;
var BD=[
  {name:"蛾后",hp:100,w:90,h:70,c1:"#cc44ff",c2:"#ff44aa",spd:55,pats:2},
  {name:"鎧甲蟲王",hp:180,w:100,h:75,c1:"#44ffaa",c2:"#ff8800",spd:45,pats:3},
  {name:"織夢蛛后",hp:280,w:110,h:80,c1:"#ff2244",c2:"#ffdd00",spd:35,pats:4}
];

function spawnBoss(wn){
  var d=BD[Math.min(Math.floor(wn/4),BD.length-1)], hm=1+(wn-4)*0.25;
  boss={alive:true,x:W/2-d.w/2,y:-100,ty:55,w:d.w,h:d.h,
    hp:Math.floor(d.hp*hm),mhp:Math.floor(d.hp*hm),name:d.name,c1:d.c1,c2:d.c2,
    spd:d.spd,pats:d.pats,ph:0,st:0,hf:0,entering:true,curPat:0,patT:0,enraged:false};
  sfxBossWarn();
}

// ═══════ Powerups ═══════
var MPW=8, pows=[];
for(var i=0;i<MPW;i++) pows.push({on:false,x:0,y:0,vy:0,tp:"",t:0});
var PWT=["shield","rapid","heal","bomb"];

function spawnPow(x,y){
  if(Math.random()>0.15)return;
  for(var i=0;i<MPW;i++){var p=pows[i];if(!p.on){
    p.on=true;p.x=x;p.y=y;p.vy=35+Math.random()*20;
    p.tp=PWT[Math.floor(Math.random()*PWT.length)];p.t=0;return;}}
}

// ═══════ Stars ═══════
var stars=[];
for(var i=0;i<150;i++) stars.push({x:Math.random()*W,y:Math.random()*H,spd:10+Math.random()*50,sz:0.3+Math.random()*1.8,br:0.2+Math.random()*0.8,tw:1+Math.random()*3});

var nebCvs=null;
function initNeb(){
  nebCvs=document.createElement("canvas");nebCvs.width=W;nebCvs.height=H;
  var nc=nebCvs.getContext("2d"), s=season();
  var g=nc.createLinearGradient(0,0,0,H);
  g.addColorStop(0,s.bg1);g.addColorStop(0.5,s.bg2);g.addColorStop(1,s.bg1);
  nc.fillStyle=g;nc.fillRect(0,0,W,H);
  [{x:W*0.2,y:H*0.25,r:180},{x:W*0.75,y:H*0.15,r:140},{x:W*0.5,y:H*0.65,r:200},{x:W*0.85,y:H*0.55,r:150},{x:W*0.3,y:H*0.8,r:130}].forEach(function(cl){
    var rg=nc.createRadialGradient(cl.x,cl.y,0,cl.x,cl.y,cl.r);
    rg.addColorStop(0,s.neb);rg.addColorStop(1,"transparent");
    nc.fillStyle=rg;nc.beginPath();nc.arc(cl.x,cl.y,cl.r,0,Math.PI*2);nc.fill();
  });
}

// ═══════ Helpers ═══════
function glow(c,bl){ctx.shadowColor=c;ctx.shadowBlur=bl;}
function noGlow(){ctx.shadowColor="transparent";ctx.shadowBlur=0;}
function hexRgb(h){h=h.replace("#","");return[parseInt(h.substr(0,2),16),parseInt(h.substr(2,2),16),parseInt(h.substr(4,2),16)];}
