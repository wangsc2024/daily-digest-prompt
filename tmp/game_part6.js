// ═══════ Collisions ═══════
function checkColl(){
  for(var i=0;i<MB;i++){var b=bulls[i];if(!b.on)continue;
    if(b.ow==="p"){
      for(var j=0;j<enemies.length;j++){var e=enemies[j];if(!e.alive)continue;
        if(b.x>e.x&&b.x<e.x+e.w&&b.y>e.y&&b.y<e.y+e.h){
          e.hp-=b.dmg;e.hf=0.1;sfxHit();if(!b.prc)b.on=false;
          if(b.aoe>0){for(var k=0;k<enemies.length;k++){if(!enemies[k].alive||k===j)continue;
            var adx=(enemies[k].x+enemies[k].w/2)-b.x,ady=(enemies[k].y+enemies[k].h/2)-b.y;
            if(adx*adx+ady*ady<b.aoe*b.aoe){enemies[k].hp-=1;enemies[k].hf=0.08;}}}
          if(e.hp<=0){e.alive=false;score+=e.sc*comboM;var rgb3=hexRgb(e.col);
            emitP(e.x+e.w/2,e.y+e.h/2,18,rgb3[0],rgb3[1],rgb3[2],100,0.6,{type:"ci",size:2,cv:20});
            sfxDie();spawnPol(e.x+e.w/2,e.y+e.h/2,e.pv,"pol");
            if(Math.random()<0.08)spawnPol(e.x+e.w/2,e.y+e.h/2,0,"sp");
            spawnPow(e.x+e.w/2,e.y+e.h/2);
            spawnFlt(e.x+e.w/2,e.y,"+"+(e.sc*comboM),comboM>2?"#ffaa00":"#fff");
            combo++;comboT=2.0;comboM=Math.min(10,1+Math.floor(combo/3));
            if(comboM>=4)spawnFlt(px,py-45,comboM+"x COMBO!","#ff44ff");
            shake=0.1;shakeI=3;
          }break;
        }
      }
      if(boss&&boss.alive&&!boss.entering){
        if(b.x>boss.x&&b.x<boss.x+boss.w&&b.y>boss.y&&b.y<boss.y+boss.h){
          boss.hp-=b.dmg;boss.hf=0.06;if(!b.prc)b.on=false;
          emitP(b.x,b.y,3,255,200,100,40,0.2,{type:"ci"});
          if(boss.hp<=0){boss.alive=false;score+=600*wave;sfxBossDie();
            var bc3=hexRgb(boss.c1),bc4=hexRgb(boss.c2);
            emitP(boss.x+boss.w/2,boss.y+boss.h/2,70,bc3[0],bc3[1],bc3[2],160,1.2,{type:"star",size:4});
            emitP(boss.x+boss.w/2,boss.y+boss.h/2,50,bc4[0],bc4[1],bc4[2],130,1.0,{type:"pet",size:3});
            spawnFlt(boss.x+boss.w/2,boss.y,"\u2605 BOSS DEFEATED \u2605","#ffdd00",1.5);
            for(var sp2=0;sp2<8;sp2++)spawnPol(boss.x+boss.w/2+(Math.random()-0.5)*50,boss.y+boss.h/2,60,"pol");
            shake=0.6;shakeI=12;boss=null;waveTrans();
          }
        }
      }
    } else {
      if(invT<=0){
        if(reflectT>0){var rdx=b.x-px,rdy=b.y-py;
          if(rdx*rdx+rdy*rdy<35*35){b.ow="p";b.vx*=-1.2;b.vy*=-1.2;b.dmg=2;b.wp=WEAP[wIdx];sfxReflect();
            emitP(b.x,b.y,5,136,255,255,60,0.3,{type:"ci"});continue;}}
        var dx7=b.x-px,dy7=b.y-py;
        if(dx7*dx7+dy7*dy7<15*15){b.on=false;plrHit();}
      }
    }
  }
  if(invT<=0)for(var i=0;i<enemies.length;i++){var e=enemies[i];if(!e.alive)continue;
    if(e.y+e.h>py-15&&e.y<py+15&&e.x+e.w>px-15&&e.x<px+15){e.alive=false;plrHit();}}
}

function plrHit(){pLives--;sfxPlrHit();emitP(px,py,35,255,100,100,110,0.7,{type:"ci",size:2});
  invT=2.0;shake=0.3;shakeI=6;combo=0;comboM=1;
  if(pLives<=0){gState=ST.GOVER;stopBGM();if(score>hi){hi=score;localStorage.setItem("pbn_hi",hi);}}}

function waveTrans(){gState=ST.WCLEAR;sfxWave();stopBGM();
  setTimeout(function(){wave++;nebCvs=null;
    if(wave%4===0){gState=ST.BOSS;spawnBoss(wave);startBGM();}
    else{createWave(wave);gState=ST.PLAY;startBGM();}},2200);
}
