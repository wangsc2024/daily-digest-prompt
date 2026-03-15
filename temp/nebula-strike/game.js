/**
 * 星雲殲擊 Nebula Strike
 * 創意太空射擊遊戲 — 波次敵人、Boss 關、升級道具、連擊系統
 * requestAnimationFrame game loop | Web Audio API | 鍵盤+觸控
 */
(function () {
  'use strict';

  const canvas = document.getElementById('gameCanvas');
  const ctx = canvas.getContext('2d');
  const W = 480;
  const H = 640;

  // --- Audio ---
  let audioCtx = null;
  function ensureAudio() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
  }
  function playTone(freq, dur, type, vol) {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = type || 'square';
    osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
    gain.gain.setValueAtTime(vol || 0.06, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + dur);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + dur);
  }
  const sfx = {
    shoot: () => playTone(880, 0.06, 'square', 0.05),
    explode: () => { playTone(120, 0.12, 'sawtooth', 0.08); playTone(80, 0.15, 'square', 0.06); },
    hit: () => { playTone(200, 0.25, 'sawtooth', 0.1); playTone(100, 0.3, 'triangle', 0.08); },
    powerup: () => { playTone(660, 0.07, 'square', 0.07); setTimeout(() => playTone(990, 0.1, 'triangle', 0.08), 80); },
    boss: () => playTone(200, 0.2, 'sawtooth', 0.1),
    wave: () => { playTone(523, 0.12, 'square', 0.07); playTone(659, 0.12, 'square', 0.07); },
  };

  // --- State ---
  const STATE = { MENU: 0, PLAYING: 1, PAUSED: 2, GAME_OVER: 3, WAVE_CLEAR: 4 };
  let state = STATE.MENU;
  let score = 0, highScore = parseInt(localStorage.getItem('ns_high') || '0', 10);
  let lives = 3, wave = 1, combo = 0, comboTimer = 0;
  let screenShake = 0;

  // --- Player ---
  const player = { x: W / 2, y: H - 70, w: 32, h: 24, speed: 260, cooldown: 0, spread: 0, rapid: 0 };

  // --- Bullets ---
  const bullets = [];
  const MAX_BULLETS = 40;
  for (let i = 0; i < MAX_BULLETS; i++) bullets.push({ active: false, x: 0, y: 0, vx: 0, vy: 0, owner: 'player' });

  function fireBullet(x, y, vx, vy, owner) {
    for (const b of bullets) {
      if (!b.active) {
        b.active = true; b.x = x; b.y = y; b.vx = vx; b.vy = vy; b.owner = owner;
        return true;
      }
    }
    return false;
  }

  // --- Enemies ---
  const enemies = [];
  const ENEMY_TYPES = {
    sweeper: { w: 24, h: 18, hp: 1, points: 30, color: '#ff6644', vx: 80, vy: 0, pattern: 'sweep' },
    orbiter: { w: 20, h: 20, hp: 1, points: 50, color: '#44ddff', vx: 0, vy: 40, pattern: 'orbit' },
    charger: { w: 28, h: 22, hp: 2, points: 80, color: '#ff44aa', vx: 0, vy: 120, pattern: 'charge' },
    boss: { w: 80, h: 48, hp: 30, points: 500, color: '#ff0066', vx: 60, vy: 20, pattern: 'boss' },
  };

  function spawnEnemy(type, x, y) {
    const t = ENEMY_TYPES[type];
    enemies.push({
      type, x, y, w: t.w, h: t.h, hp: t.hp, maxHp: t.hp, points: t.points, color: t.color,
      vx: t.vx, vy: t.vy, dir: 1, t: 0, pattern: t.pattern,
    });
  }

  function spawnWave() {
    const isBoss = wave % 5 === 0 && wave > 0;
    if (isBoss) {
      spawnEnemy('boss', W / 2 - 40, 60);
      sfx.boss();
    } else {
      const count = 5 + Math.floor(wave * 1.5);
      for (let i = 0; i < count; i++) {
        const r = Math.random();
        let type = 'sweeper';
        if (r < 0.25 && wave >= 2) type = 'orbiter';
        else if (r < 0.45 && wave >= 3) type = 'charger';
        const x = 40 + Math.random() * (W - 80);
        spawnEnemy(type, x, -30 - i * 25);
      }
      sfx.wave();
    }
  }

  // --- Powerups ---
  const powerups = [];
  const POWERUP_TYPES = [{ id: 'spread', color: '#ffaa00', dur: 8 }, { id: 'rapid', color: '#ff44ff', dur: 6 }, { id: 'life', color: '#44ff44', dur: 0 }];
  const activePowerups = { spread: 0, rapid: 0 };

  function spawnPowerup(x, y) {
    if (Math.random() > 0.2) return;
    const pt = POWERUP_TYPES[Math.floor(Math.random() * POWERUP_TYPES.length)];
    powerups.push({ x, y, w: 20, h: 20, type: pt, vy: 70 });
  }

  // --- Particles ---
  const particles = [];
  const MAX_PARTICLES = 150;
  for (let i = 0; i < MAX_PARTICLES; i++) particles.push({ active: false, x: 0, y: 0, vx: 0, vy: 0, life: 0, maxLife: 0, r: 255, g: 255, b: 255, size: 2 });

  function spawnParticles(x, y, n, r, g, b) {
    let c = 0;
    for (const p of particles) {
      if (!p.active && c < n) {
        p.active = true; p.x = x; p.y = y; p.r = r; p.g = g; p.b = b;
        const a = Math.random() * Math.PI * 2, s = 60 + Math.random() * 100;
        p.vx = Math.cos(a) * s; p.vy = Math.sin(a) * s;
        p.life = p.maxLife = 0.35 + Math.random() * 0.3; c++;
      }
    }
  }

  // --- Stars ---
  const stars = [];
  for (let i = 0; i < 60; i++) {
    stars.push({ x: Math.random() * W, y: Math.random() * H, speed: 0.2 + Math.random() * 0.8, size: 1 + Math.random() * 2, b: 80 + Math.random() * 120 });
  }

  // --- Input ---
  const keys = {};
  let touchLeft = false, touchRight = false, touchFire = false;
  window.addEventListener('keydown', e => { keys[e.key] = true; if (e.key === 'Escape') togglePause(); });
  window.addEventListener('keyup', e => { keys[e.key] = false; });

  function setupTouch(id, down, up) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('touchstart', e => { e.preventDefault(); ensureAudio(); down(); });
    el.addEventListener('touchend', e => { e.preventDefault(); up(); });
    el.addEventListener('touchcancel', e => { e.preventDefault(); up(); });
  }
  setupTouch('btnLeft', () => { touchLeft = true; }, () => { touchLeft = false; });
  setupTouch('btnRight', () => { touchRight = true; }, () => { touchRight = false; });
  setupTouch('btnFire', () => { touchFire = true; }, () => { touchFire = false; });

  const btnPause = document.getElementById('btnPause');
  if (btnPause) btnPause.addEventListener('touchstart', e => { e.preventDefault(); togglePause(); });
  if (btnPause) btnPause.addEventListener('click', e => { e.preventDefault(); togglePause(); });

  canvas.addEventListener('click', () => {
    ensureAudio();
    if (state === STATE.MENU || state === STATE.GAME_OVER) startGame();
    else if (state === STATE.WAVE_CLEAR) nextWave();
  });
  canvas.addEventListener('touchstart', e => {
    e.preventDefault();
    ensureAudio();
    if (state === STATE.MENU || state === STATE.GAME_OVER) startGame();
    else if (state === STATE.WAVE_CLEAR) nextWave();
  });

  // --- Collision ---
  function aabb(ax, ay, aw, ah, bx, by, bw, bh) {
    return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
  }

  function registerKill(base, x, y) {
    combo++;
    comboTimer = 2;
    const mult = Math.min(4, 1 + Math.floor(combo / 4));
    score += base * mult;
    spawnParticles(x, y, 10, 255, 200, 50);
  }

  function togglePause() {
    if (state === STATE.PLAYING) state = STATE.PAUSED;
    else if (state === STATE.PAUSED) state = STATE.PLAYING;
  }

  function startGame() {
    score = 0; lives = 3; wave = 0; combo = 0;
    enemies.length = 0; powerups.length = 0;
    for (const b of bullets) b.active = false;
    for (const p of particles) p.active = false;
    activePowerups.spread = 0; activePowerups.rapid = 0;
    player.x = W / 2; player.cooldown = 0;
    nextWave();
  }

  function nextWave() {
    wave++;
    enemies.length = 0;
    state = STATE.PLAYING;
    spawnWave();
  }

  // --- Update ---
  function update(dt) {
    if (screenShake > 0) screenShake -= dt * 25;
    if (comboTimer > 0) comboTimer -= dt;
    if (comboTimer <= 0 && combo > 0) combo = 0;

    if (state !== STATE.PLAYING) return;

    // Player
    let dx = 0;
    if (keys['ArrowLeft'] || keys['a'] || keys['A'] || touchLeft) dx = -1;
    if (keys['ArrowRight'] || keys['d'] || keys['D'] || touchRight) dx = 1;
    player.x += dx * player.speed * dt;
    player.x = Math.max(player.w / 2, Math.min(W - player.w / 2, player.x));

    const cdMult = activePowerups.rapid > 0 ? 0.5 : 1;
    player.cooldown -= dt;
    if ((keys[' '] || keys['ArrowUp'] || touchFire) && player.cooldown <= 0) {
      const vy = -420;
      fireBullet(player.x, player.y - player.h / 2, 0, vy, 'player');
      if (activePowerups.spread > 0) {
        fireBullet(player.x - 8, player.y - player.h / 2, -60, vy, 'player');
        fireBullet(player.x + 8, player.y - player.h / 2, 60, vy, 'player');
      }
      sfx.shoot();
      player.cooldown = (activePowerups.rapid > 0 ? 0.12 : 0.2) * cdMult;
    }

    for (const k of Object.keys(activePowerups)) {
      if (activePowerups[k] > 0) activePowerups[k] -= dt;
    }

    // Powerups
    for (let i = powerups.length - 1; i >= 0; i--) {
      const pw = powerups[i];
      pw.y += pw.vy * dt;
      if (pw.y > H + 20) { powerups.splice(i, 1); continue; }
      if (aabb(pw.x, pw.y, pw.w, pw.h, player.x - player.w / 2, player.y - player.h / 2, player.w, player.h)) {
        if (pw.type.id === 'life') lives = Math.min(5, lives + 1);
        else activePowerups[pw.type.id] = pw.type.dur;
        sfx.powerup();
        spawnParticles(pw.x + pw.w / 2, pw.y + pw.h / 2, 6, 255, 215, 0);
        powerups.splice(i, 1);
      }
    }

    // Bullets
    for (const b of bullets) {
      if (!b.active) continue;
      b.x += b.vx * dt;
      b.y += b.vy * dt;
      if (b.y < -20 || b.y > H + 20 || b.x < -20 || b.x > W + 20) { b.active = false; continue; }

      if (b.owner === 'player') {
        for (const e of enemies) {
          if (e.hp <= 0) continue;
          if (aabb(b.x - 2, b.y - 2, 4, 4, e.x, e.y, e.w, e.h)) {
            e.hp--;
            b.active = false;
            if (e.hp <= 0) {
              registerKill(e.points, e.x + e.w / 2, e.y + e.h / 2);
              sfx.explode();
              screenShake = e.type === 'boss' ? 8 : 4;
              spawnParticles(e.x + e.w / 2, e.y + e.h / 2, 15, 255, 100, 100);
              spawnPowerup(e.x + e.w / 2, e.y);
            }
            break;
          }
        }
      }
    }

    // Enemies
    for (const e of enemies) {
      if (e.hp <= 0) continue;
      e.t += dt;
      if (e.pattern === 'sweep') {
        e.x += e.vx * e.dir * dt;
        if (e.x <= 5 || e.x + e.w >= W - 5) e.dir *= -1;
        e.y += 25 * dt;
      } else if (e.pattern === 'orbit') {
        e.x = W / 2 + Math.cos(e.t * 1.5) * 120;
        e.y += e.vy * dt;
      } else if (e.pattern === 'charge') {
        e.y += e.vy * dt;
        if (e.t > 1) e.vx = 40 * (e.x < player.x ? 1 : -1);
        e.x += e.vx * dt;
      } else if (e.pattern === 'boss') {
        e.x += e.vx * e.dir * dt;
        if (e.x <= 40 || e.x + e.w >= W - 40) e.dir *= -1;
        e.y += Math.sin(e.t * 2) * 15 * dt;
      }
      if (e.y > H + 50) e.hp = 0;
      if (aabb(e.x, e.y, e.w, e.h, player.x - player.w / 2, player.y - player.h / 2, player.w, player.h)) {
        e.hp = 0;
        lives--;
        sfx.hit();
        screenShake = 10;
        spawnParticles(player.x, player.y, 12, 100, 200, 255);
        combo = 0;
        if (lives <= 0) state = STATE.GAME_OVER;
      }
    }

    // Particles
    for (const p of particles) {
      if (!p.active) continue;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= dt;
      if (p.life <= 0) p.active = false;
    }

    // Wave clear
    if (enemies.every(e => e.hp <= 0)) {
      state = STATE.WAVE_CLEAR;
      if (score > highScore) { highScore = score; localStorage.setItem('ns_high', String(highScore)); }
    }
  }

  // --- Draw ---
  function drawStars(t) {
    for (const s of stars) {
      s.y += s.speed;
      if (s.y > H) { s.y = -2; s.x = Math.random() * W; }
      const twinkle = 0.6 + 0.4 * Math.sin(t * 2 + s.x);
      const b = s.b * twinkle;
      ctx.fillStyle = `rgb(${b},${b},${Math.min(255, b + 30)})`;
      ctx.fillRect(s.x, s.y, s.size, s.size);
    }
  }

  function draw() {
    const t = performance.now() / 1000;
    ctx.save();
    if (screenShake > 0) ctx.translate((Math.random() - 0.5) * screenShake, (Math.random() - 0.5) * screenShake);

    ctx.fillStyle = '#0a0618';
    ctx.fillRect(-10, -10, W + 20, H + 20);
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, 'rgba(80,40,120,0.4)');
    grad.addColorStop(0.5, 'rgba(40,20,80,0.2)');
    grad.addColorStop(1, 'rgba(20,10,40,0.5)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);
    drawStars(t);

    if (state === STATE.MENU) {
      ctx.fillStyle = '#00ffff';
      ctx.font = 'bold 28px "Courier New", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('星雲殲擊 NEBULA STRIKE', W / 2, H / 2 - 50);
      ctx.fillStyle = '#ffffff';
      ctx.font = '16px "Courier New", monospace';
      ctx.fillText('點擊 / Enter 開始', W / 2, H / 2 + 10);
      ctx.fillStyle = '#888888';
      ctx.fillText('← → 移動  空格 射擊  Esc 暫停', W / 2, H / 2 + 45);
      ctx.fillText('HI: ' + highScore, W / 2, H / 2 + 80);
      ctx.restore();
      return;
    }

    if (state === STATE.GAME_OVER) {
      for (const e of enemies) if (e.hp > 0) { ctx.fillStyle = e.color; ctx.fillRect(e.x, e.y, e.w, e.h); }
      for (const p of particles) if (p.active) { ctx.fillStyle = `rgba(${p.r},${p.g},${p.b},${p.life / p.maxLife})`; ctx.fillRect(p.x, p.y, p.size, p.size); }
      ctx.fillStyle = 'rgba(0,0,0,0.7)';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#ff4466';
      ctx.font = 'bold 32px "Courier New", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('GAME OVER', W / 2, H / 2 - 30);
      ctx.fillStyle = '#ffffff';
      ctx.font = '18px "Courier New", monospace';
      ctx.fillText('SCORE: ' + score + '  WAVE: ' + wave, W / 2, H / 2 + 20);
      ctx.fillStyle = '#00ffff';
      ctx.fillText('點擊 / Enter 重玩', W / 2, H / 2 + 60);
      ctx.restore();
      return;
    }

    if (state === STATE.WAVE_CLEAR) {
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#00ffaa';
      ctx.font = 'bold 24px "Courier New", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('WAVE ' + wave + ' CLEAR!', W / 2, H / 2 - 20);
      ctx.fillStyle = '#ffffff';
      ctx.font = '16px "Courier New", monospace';
      ctx.fillText('點擊繼續', W / 2, H / 2 + 20);
      ctx.restore();
      return;
    }

    if (state === STATE.PLAYING || state === STATE.PAUSED) {
      for (const e of enemies) {
        if (e.hp <= 0) continue;
        ctx.fillStyle = e.color;
        if (e.type === 'boss') {
          ctx.fillRect(e.x, e.y, e.w, e.h);
          ctx.fillStyle = 'rgba(0,0,0,0.5)';
          ctx.fillRect(e.x + 4, e.y + 4, (e.w - 8) * (1 - e.hp / e.maxHp), 6);
          ctx.fillStyle = '#ff0066';
          ctx.fillRect(e.x + 4, e.y + 4, (e.w - 8) * (e.hp / e.maxHp), 6);
        } else ctx.fillRect(e.x, e.y, e.w, e.h);
      }
      for (const b of bullets) {
        if (!b.active) continue;
        ctx.fillStyle = b.owner === 'player' ? '#00ffff' : '#ff4444';
        ctx.fillRect(b.x - 1, b.y - 2, 2, 4);
      }
      for (const pw of powerups) {
        ctx.fillStyle = pw.type.color;
        ctx.fillRect(pw.x, pw.y, pw.w, pw.h);
      }
      ctx.fillStyle = '#00ffff';
      ctx.fillRect(player.x - player.w / 2, player.y - player.h / 2, player.w, player.h);
      for (const p of particles) {
        if (!p.active) continue;
        ctx.fillStyle = `rgba(${p.r},${p.g},${p.b},${p.life / p.maxLife})`;
        ctx.fillRect(p.x, p.y, p.size, p.size);
      }
      ctx.fillStyle = '#ffffff';
      ctx.font = '14px "Courier New", monospace';
      ctx.textAlign = 'left';
      ctx.fillText('SCORE: ' + score, 10, 22);
      ctx.textAlign = 'center';
      ctx.fillText('WAVE ' + wave, W / 2, 22);
      ctx.textAlign = 'right';
      ctx.fillText('HI: ' + highScore, W - 10, 22);
      for (let i = 0; i < lives; i++) ctx.fillRect(10 + i * 22, H - 24, 18, 8);
      if (combo >= 2) {
        ctx.fillStyle = '#ffaa00';
        ctx.font = 'bold 12px "Courier New", monospace';
        ctx.textAlign = 'left';
        ctx.fillText('COMBO x' + Math.min(4, 1 + Math.floor(combo / 4)), 10, 42);
      }
      if (state === STATE.PAUSED) {
        ctx.fillStyle = 'rgba(0,0,0,0.7)';
        ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = '#00ffff';
        ctx.font = 'bold 24px "Courier New", monospace';
        ctx.textAlign = 'center';
        ctx.fillText('暫停', W / 2, H / 2);
      }
    }
    ctx.restore();
  }

  // --- Loop ---
  let last = 0;
  function loop(ts) {
    update(Math.min((ts - last) / 1000, 0.05));
    last = ts;
    draw();
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  window.addEventListener('keydown', e => {
    if ((e.key === ' ' || e.key === 'Enter') && (state === STATE.MENU || state === STATE.GAME_OVER)) { e.preventDefault(); ensureAudio(); startGame(); }
    if ((e.key === ' ' || e.key === 'Enter') && state === STATE.WAVE_CLEAR) { e.preventDefault(); nextWave(); }
  });
})();
