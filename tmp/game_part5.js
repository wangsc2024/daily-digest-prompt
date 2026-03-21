// ═══════ Formation Patterns ═══════
function updFmt(dt){
  fmtOff+=dt;
  for(var i=0;i<enemies.length;i++){var e=enemies[i];if(!e.alive)continue;var ox=0,oy=0;
    if(fmtType===1)ox=Math.sin(fmtOff*2+e.by*0.05)*18;
    else if(fmtType===2){ox=Math.sin(fmtOff*1.5)*(e.bx-W/2)*0.12;oy=Math.sin(fmtOff*1.5)*(e.by-100)*0.06;}
    else if(fmtType===3){ox=Math.sin(fmtOff*1.2+e.ph)*22;oy=Math.cos(fmtOff*1.2+e.ph)*12;}
    else if(fmtType===4){if(e.by<100&&Math.sin(fmtOff+e.ph)>0.8)oy=Math.sin(fmtOff*3+e.ph)*30;ox=Math.sin(fmtOff*1.5+e.ph)*15;}
    e.x=e.bx+ox;e.y=e.by+oy;
  }
}

// ═══════ Updates ═══════
function updBullets(dt){
  for(var i=0;i<MB;i++){var b=bulls[i];if(!b.on)continue;
    if(b.home&&b.ow==="p"){
      var cl=null,cd=200,tgts=boss&&boss.alive?[boss]:enemies;
      for(var j=0;j<tgts.length;j++){var tg=tgts[j];if(!tg.alive)continue;
        var dx2=(tg.x+(tg.w||0)/2)-b.x,dy2=(tg.y+(tg.h||0)/2)-b.y,d2=Math.sqrt(dx2*dx2+dy2*dy2);
        if(d2<cd){cl=tg;cd=d2;}}
      if(cl){var tx2=(cl.x+(cl.w||0)/2)-b.x,ty2=(cl.y+(cl.h||0)/2)-b.y,td2=Math.sqrt(tx2*tx2+ty2*ty2)||1;
        var cs=Math.sqrt(b.vx*b.vx+b.vy*b.vy);b.vx+=(tx2/td2)*600*dt;b.vy+=(ty2/td2)*600*dt;
        var ns=Math.sqrt(b.vx*b.vx+b.vy*b.vy);if(ns>cs){b.vx*=cs/ns;b.vy*=cs/ns;}}
    }
    b.x+=b.vx*dt;b.y+=b.vy*dt;b.life-=dt;
    if(b.y<-10||b.y>H+10||b.x<-10||b.x>W+10||b.life<=0)b.on=false;
  }
}

function updPollen(dt){
  for(var i=0;i<MPL;i++){var p=plDrp[i];if(!p.on)continue;
    p.y+=p.vy*dt;p.t+=dt;
    var dx3=px-p.x,dy3=py-p.y,d3=Math.sqrt(dx3*dx3+dy3*dy3);
    if(d3<90){p.x+=dx3/d3*220*dt;p.y+=dy3/d3*220*dt;}
    if(p.y>H+20)p.on=false;
    if(d3<22){
      if(p.tp==="pol"){pollen+=p.val;
        if(fIdx<FORMS.length-1&&pollen>=FORMS[fIdx+1].thr){
          fIdx++;evolAnim=2.5;pLives=Math.min(pLives+1,FORMS[fIdx].lives);sfxEvolve();
          spawnFlt(px,py-35,"\u2605 "+FORMS[fIdx].name+" \u2605","#ffdd00",1.5);
          emitP(px,py,50,255,220,80,140,1.0,{type:"star",size:3,cv:30});
        }
      } else if(p.tp==="sp"){spCharge=Math.min(100,spCharge+25);spawnFlt(p.x,p.y,"SP+25","#88ffff");}
      p.on=false;
    }
  }
}

function updEnemies(dt){
  if(enemies.every(function(e){return !e.alive;}))return;
  eMoveT+=dt;if(eMoveT>=eMoveStep){eMoveT=0;var nr=false;
    for(var i=0;i<enemies.length;i++){var e=enemies[i];if(!e.alive)continue;e.bx+=eDirX*eSpd*0.3;if(e.bx+e.w>W-8||e.bx<8)nr=true;}
    if(nr){eDirX*=-1;for(var i=0;i<enemies.length;i++)if(enemies[i].alive)enemies[i].by+=10;}}
  updFmt(dt);
  eShootT+=dt;var si2=Math.max(0.35,1.4-wave*0.05);
  if(eShootT>=si2){eShootT=0;var alive2=enemies.filter(function(e){return e.alive;});
    if(alive2.length>0){var sh=alive2[Math.floor(Math.random()*alive2.length)];
      var dx4=px-(sh.x+sh.w/2),dy4=py-(sh.y+sh.h/2),d4=Math.sqrt(dx4*dx4+dy4*dy4)||1,bs2=110+wave*7;
      fireB(sh.x+sh.w/2,sh.y+sh.h,dx4/d4*bs2,dy4/d4*bs2,"e",null,4,1);}}
  for(var i=0;i<enemies.length;i++)if(enemies[i].hf>0)enemies[i].hf-=dt;
}

function updBoss(dt){
  if(!boss||!boss.alive)return;var b=boss;
  if(b.entering){b.y+=65*dt;if(b.y>=b.ty){b.y=b.ty;b.entering=false;}return;}
  b.ph+=dt;b.hf=Math.max(0,b.hf-dt);
  if(!b.enraged&&b.hp<b.mhp*0.3){b.enraged=true;
    spawnFlt(b.x+b.w/2,b.y-20,"\u26a0 \u72c2\u66b4\u5316\uff01","#ff4444",1.3);
    emitP(b.x+b.w/2,b.y+b.h/2,30,255,50,50,100,0.6,{type:"ci",size:3});}
  b.x+=Math.sin(b.ph*1.2)*b.spd*dt;if(b.enraged)b.x+=Math.cos(b.ph*2.5)*b.spd*0.5*dt;
  b.x=Math.max(5,Math.min(W-b.w-5,b.x));
  b.st+=dt;var sr2=b.enraged?0.25:0.5;
  if(b.st>=sr2){b.st=0;var cx2=b.x+b.w/2,cy2=b.y+b.h;b.patT+=1;
    var pi2=b.patT%(b.pats+(b.enraged?1:0));
    if(pi2===0){for(var a3=-40;a3<=40;a3+=12){var rd2=(a3-90)*Math.PI/180;fireB(cx2,cy2,Math.cos(rd2)*130,Math.sin(rd2)*130,"e",null,4,1);}}
    else if(pi2===1){var sa3=b.ph*4;for(var i=0;i<4;i++){var a4=sa3+i*Math.PI/2;fireB(cx2,cy2,Math.cos(a4)*110,Math.sin(a4)*110,"e",null,3,1);}}
    else if(pi2===2){var dx5=px-cx2,dy5=py-cy2,d5=Math.sqrt(dx5*dx5+dy5*dy5)||1;
      fireB(cx2,cy2,dx5/d5*150,dy5/d5*150,"e",null,5,1);fireB(cx2,cy2,dx5/d5*140+30,dy5/d5*140,"e",null,3,1);fireB(cx2,cy2,dx5/d5*140-30,dy5/d5*140,"e",null,3,1);}
    else{for(var i=0;i<12;i++){var a5=i*Math.PI/6;fireB(cx2,cy2,Math.cos(a5)*100,Math.sin(a5)*100,"e",null,3,1);}}}
}

function updPows(dt){
  for(var i=0;i<MPW;i++){var p=pows[i];if(!p.on)continue;p.y+=p.vy*dt;p.t+=dt;
    if(p.y>H+20){p.on=false;continue;}
    var dx6=px-p.x,dy6=py-p.y;
    if(dx6*dx6+dy6*dy6<25*25){p.on=false;sfxPow();
      if(p.tp==="shield"){reflectT=5;spawnFlt(p.x,p.y,"\u76fe \u53cd\u5c04\u76fe","#88ffff");}
      else if(p.tp==="rapid"){sRate=0.08;setTimeout(function(){sRate=0.18;},5000);spawnFlt(p.x,p.y,"\u26a1 \u9023\u5c04","#ffaa44");}
      else if(p.tp==="heal"){pLives=Math.min(pLives+1,FORMS[fIdx].lives);spawnFlt(p.x,p.y,"\u2665 +1","#ff66aa");}
      else if(p.tp==="bomb"){
        for(var j=0;j<enemies.length;j++){if(enemies[j].alive){enemies[j].hp-=3;if(enemies[j].hp<=0){enemies[j].alive=false;score+=enemies[j].sc;var rgb2=hexRgb(enemies[j].col);emitP(enemies[j].x+enemies[j].w/2,enemies[j].y+enemies[j].h/2,8,rgb2[0],rgb2[1],rgb2[2],80,0.4,{type:"ci"});}}}
        shake=0.3;shakeI=8;spawnFlt(p.x,p.y,"\u2604 \u82b1\u7c89\u7206\u88c2","#ffdd00");
        emitP(W/2,H/2,60,255,200,100,200,0.8,{type:"pet",size:3,spread:200});
      }
    }
  }
}

// ═══════ Shooting ═══════
function playerShoot(){
  if(sCD>0)return;var form=FORMS[fIdx],wp=WEAP[wIdx],spd=-480;
  if(wIdx===0){sfxPetal();
    if(form.bc>=3){fireB(px,py-15,0,spd,"p",wp,3,1);fireB(px-10,py-12,-40,spd,"p",wp,3,1);fireB(px+10,py-12,40,spd,"p",wp,3,1);}
    else if(form.bc>=2){fireB(px-6,py-12,-15,spd,"p",wp,3,1);fireB(px+6,py-12,15,spd,"p",wp,3,1);}
    else fireB(px,py-15,0,spd,"p",wp,3,1);
  } else if(wIdx===1){sfxBeam();fireB(px,py-15,0,spd*1.2,"p",wp,4,2,{pierce:true});
    if(form.bc>=2)fireB(px,py-15,0,spd*1.1,"p",wp,2,1,{pierce:true});
  } else {sfxSpore();
    fireB(px,py-15,(Math.random()-0.5)*40,spd*0.7,"p",wp,5,1,{homing:true,aoe:25,life:3});
    if(form.bc>=2)fireB(px-15,py-10,-30,spd*0.6,"p",wp,4,1,{homing:true,aoe:20,life:3});
    if(form.bc>=3)fireB(px+15,py-10,30,spd*0.6,"p",wp,4,1,{homing:true,aoe:20,life:3});
  }
  sCD=wIdx===1?sRate*1.5:sRate;
}

function useSpecial(){
  if(spCharge<100)return;spCharge=0;shake=0.5;shakeI=10;
  var wp=WEAP[wIdx];
  for(var i=0;i<24;i++){var a6=(i/24)*Math.PI*2;fireB(px,py,Math.cos(a6)*300,Math.sin(a6)*300,"p",wp,5,3,{pierce:true,life:1.5});}
  emitP(px,py,80,wp.r,wp.g,wp.b,200,1.0,{type:"pet",size:4,cv:40});
  spawnFlt(px,py-40,"\u2605 \u5e7b\u8776\u98a8\u66b4 \u2605","#ffdd00",1.5);
}
