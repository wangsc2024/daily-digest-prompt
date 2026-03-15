/**
 * Cosmic Shooter - 創意太空射擊遊戲
 * 依 game-design Skill 實作：requestAnimationFrame、AABB、預載、鍵鼠觸控、狀態機
 * 創意元素：星雲背景、黑洞重力、能量波、連擊系統、陣型敵機
 */
(function () {
  'use strict';

  const W = 640;
  const H = 480;
  let canvas, ctx;
  let gameState = 'LOADING'; // LOADING | MENU | PLAYING | PAUSED | GAME_OVER
  let keys = {};
  let lastTime = 0;
  let screenShake = 0;
  let stars = [];
  let loadProgress = 0;

  // 玩家
  const player = { x: W / 2 - 20, y: H - 80, w: 40, h: 32, vx: 0, vy: 0, speed: 6, lives: 3, invincible: 0 };
  let bullets = [];
  let enemies = [];
  let particles = [];
  let powerUps = [];
  let blackHoles = [];
  let energyWaves = [];

  // 分數與連擊
  let score = 0;
  let combo = 0;
  let comboTimeout = 0;
  let comboMultiplier = 1;
  let wave = 1;

  // 子彈池（物件池優化）
  const BULLET_POOL_SIZE = 80;
  let bulletPool = [];
  let bulletPoolIndex = 0;

  const COLORS = {
    nebula1: '#0d0221',
    nebula2: '#261447',
    nebula3: '#540d6e',
    accent: '#ee4266',
    accent2: '#ff6b6b',
    bullet: '#00f5d4',
    player: '#7b2cbf',
    enemy: '#9d4edd',
    powerup: '#06ffa5',
    blackhole: '#1a0a2e',
    white: '#ffffff',
    star: '#e0e0e0'
  };

  // ========== 工具函數 ==========
  function rnd(min, max) {
    return min + Math.random() * (max - min);
  }
  function rndInt(min, max) {
    return Math.floor(rnd(min, max + 1));
  }

  function aabb(a, b) {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  }

  function addParticle(x, y, color, vx, vy, life = 30) {
    particles.push({ x, y, vx, vy, life, maxLife: life, color, size: rnd(2, 5) });
  }

  // ========== 子彈池 ==========
  function initBulletPool() {
    for (let i = 0; i < BULLET_POOL_SIZE; i++) {
      bulletPool.push({ x: 0, y: 0, w: 4, h: 12, vy: 0, active: false });
    }
  }

  function shootBullet(x, y, vy = -14, isTriple = false) {
    if (isTriple) {
      for (let i = -1; i <= 1; i++) {
        const b = bulletPool[bulletPoolIndex % BULLET_POOL_SIZE];
        bulletPoolIndex++;
        b.x = x + i * 12;
        b.y = y;
        b.vy = vy;
        b.vx = i * 2;
        b.active = true;
        bullets.push(b);
      }
    } else {
      const b = bulletPool[bulletPoolIndex % BULLET_POOL_SIZE];
      bulletPoolIndex++;
      b.x = x + player.w / 2 - 2;
      b.y = y;
      b.vy = vy;
      b.vx = 0;
      b.active = true;
      bullets.push(b);
    }
  }

  // ========== 星雲背景 ==========
  function initStars() {
    stars = [];
    for (let i = 0; i < 120; i++) {
      stars.push({
        x: rnd(0, W),
        y: rnd(0, H),
        r: rnd(0.5, 2),
        alpha: rnd(0.3, 1),
        speed: rnd(0.2, 1)
      });
    }
  }

  function drawStars(dt) {
    ctx.fillStyle = COLORS.nebula1;
    ctx.fillRect(0, 0, W, H);

    const grd = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, W);
    grd.addColorStop(0, COLORS.nebula3);
    grd.addColorStop(0.4, COLORS.nebula2);
    grd.addColorStop(0.8, COLORS.nebula1);
    grd.addColorStop(1, '#050008');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, W, H);

    stars.forEach(s => {
      s.y += s.speed * dt * 0.06;
      if (s.y > H) s.y = 0;
      ctx.fillStyle = COLORS.star;
      ctx.globalAlpha = s.alpha;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }

  // ========== 黑洞（創意元素：重力牽引）==========
  function spawnBlackHole() {
    if (blackHoles.length >= 2) return;
    blackHoles.push({
      x: rnd(60, W - 60),
      y: rnd(80, H - 120),
      r: 25,
      pullRange: 100,
      pullForce: 0.15,
      life: 300,
      maxLife: 300
    });
  }

  function updateBlackHoles(dt) {
    blackHoles = blackHoles.filter(bh => {
      bh.life -= dt;
      if (bh.life <= 0) {
        for (let i = 0; i < 20; i++) addParticle(bh.x, bh.y, COLORS.blackhole, rnd(-3, 3), rnd(-3, 3));
        return false;
      }

      const dx = bh.x - (player.x + player.w / 2);
      const dy = bh.y - (player.y + player.h / 2);
      const dist = Math.hypot(dx, dy);
      if (dist < bh.pullRange && dist > 5) {
        const force = (1 - dist / bh.pullRange) * bh.pullForce * dt * 0.1;
        player.x += (dx / dist) * force * 50;
        player.y += (dy / dist) * force * 50;
      }
      return true;
    });
  }

  function drawBlackHoles() {
    blackHoles.forEach(bh => {
      const alpha = bh.life / bh.maxLife;
      ctx.save();
      ctx.globalAlpha = alpha;
      const grd = ctx.createRadialGradient(bh.x, bh.y, 0, bh.x, bh.y, bh.r * 2);
      grd.addColorStop(0, '#2d1b4e');
      grd.addColorStop(0.5, '#1a0a2e');
      grd.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = grd;
      ctx.beginPath();
      ctx.arc(bh.x, bh.y, bh.r * 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = COLORS.accent;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(bh.x, bh.y, bh.r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    });
  }

  // ========== 能量波（創意元素：清屏）==========
  function fireEnergyWave() {
    if (energyWaves.length > 0) return;
    energyWaves.push({ y: H, r: 0, maxR: W * 1.5, expanding: true });
  }

  function updateEnergyWaves(dt) {
    energyWaves = energyWaves.filter(ew => {
      if (ew.expanding) {
        ew.r += dt * 8;
        if (ew.r >= ew.maxR) ew.expanding = false;
      } else {
        ew.y -= dt * 2;
        if (ew.y < -100) return false;
      }
      enemies = enemies.filter(e => {
        const hit = Math.hypot(e.x + e.w / 2 - W / 2, e.y + e.h / 2 - ew.y) > ew.r;
        if (!hit) {
          score += 50;
          for (let i = 0; i < 8; i++) addParticle(e.x + e.w / 2, e.y + e.h / 2, COLORS.accent2, rnd(-4, 4), rnd(-4, 4));
          return false;
        }
        return true;
      });
      return true;
    });
  }

  function drawEnergyWaves() {
    energyWaves.forEach(ew => {
      ctx.strokeStyle = COLORS.bullet;
      ctx.lineWidth = 4;
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.arc(W / 2, ew.y, ew.r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    });
  }

  // ========== 敵人生成（陣型）==========
  const FORMATIONS = [
    (wave) => Array.from({ length: 4 + Math.min(wave, 3) }, (_, i) => ({ x: 80 + i * 120, y: 60, vx: 1, vy: 0, w: 28, h: 24, hp: 1 })),
    (wave) => Array.from({ length: 3 }, (_, i) => ({ x: 200 + i * 120, y: 40 + i * 30, vx: -1, vy: 0.3, w: 32, h: 28, hp: 2 })),
    (wave) => [{ x: W / 2 - 40, y: 50, vx: 0, vy: 0.5, w: 48, h: 40, hp: 5 }]
  ];

  function spawnWave() {
    const form = FORMATIONS[(wave - 1) % FORMATIONS.length](wave);
    form.forEach(e => {
      e.x = e.x || rnd(40, W - 40);
      e.y = e.y || 30;
      enemies.push({ ...e, color: COLORS.enemy });
    });
    if (wave % 3 === 0) spawnBlackHole();
  }

  // ========== 道具 ==========
  const POWER_TYPES = ['triple', 'shield', 'wave'];
  function spawnPowerUp(x, y) {
    if (Math.random() < 0.25) {
      powerUps.push({
        x, y, w: 24, h: 24,
        type: POWER_TYPES[rndInt(0, POWER_TYPES.length - 1)],
        vy: 1.5, life: 300
      });
    }
  }

  function applyPowerUp(pu) {
    if (pu.type === 'triple') player.tripleShot = 300;
    if (pu.type === 'shield') player.shield = 400;
    if (pu.type === 'wave') fireEnergyWave();
  }

  // ========== 遊戲循環 ==========
  function clampPlayer() {
    player.x = Math.max(10, Math.min(W - player.w - 10, player.x));
    player.y = Math.max(H - 120, Math.min(H - player.h - 20, player.y));
  }

  function updatePlaying(dt) {
    const moveSpeed = player.speed * (dt / 16);
    if (keys['ArrowLeft'] || keys['a'] || keys['A']) player.x -= moveSpeed;
    if (keys['ArrowRight'] || keys['d'] || keys['D']) player.x += moveSpeed;
    if (keys['ArrowUp'] || keys['w'] || keys['W']) player.y -= moveSpeed;
    if (keys['ArrowDown'] || keys['s'] || keys['S']) player.y += moveSpeed;
    clampPlayer();

    if (player.tripleShot) player.tripleShot -= dt;
    if (player.shield) player.shield -= dt;
    if (player.invincible) player.invincible -= dt;

    comboTimeout -= dt;
    if (comboTimeout <= 0) {
      combo = 0;
      comboMultiplier = 1;
    }

    bullets = bullets.filter(b => {
      b.x += (b.vx || 0) * (dt / 16);
      b.y += b.vy * (dt / 16);
      if (b.y < -20 || b.y > H + 20 || b.x < -20 || b.x > W + 20) { b.active = false; return false; }
      return true;
    });

    enemies.forEach(e => {
      e.x += e.vx * (dt / 16);
      e.y += e.vy * (dt / 16);
      if (e.x < 0 || e.x > W - e.w) e.vx *= -1;
      if (e.y > H) enemies = enemies.filter(x => x !== e);
    });

    bullets.forEach(b => {
      if (!b.active) return;
      enemies.forEach(e => {
        if (aabb(b, e)) {
          e.hp--;
          b.active = false;
          combo++;
          comboTimeout = 120;
          comboMultiplier = 1 + Math.min(combo, 10) * 0.1;
          score += Math.floor(20 * comboMultiplier);
          for (let i = 0; i < 6; i++) addParticle(e.x + e.w / 2, e.y + e.h / 2, COLORS.accent2, rnd(-3, 3), rnd(-3, 3));
          if (e.hp <= 0) {
            spawnPowerUp(e.x + e.w / 2, e.y + e.h / 2);
            enemies = enemies.filter(x => x !== e);
          }
        }
      });
    });

    powerUps = powerUps.filter(pu => {
      pu.y += pu.vy * (dt / 16);
      pu.life -= dt;
      if (pu.life <= 0 || pu.y > H) return false;
      if (aabb(player, pu)) {
        applyPowerUp(pu);
        return false;
      }
      return true;
    });

    updateBlackHoles(dt);
    updateEnergyWaves(dt);

    particles = particles.filter(p => {
      p.x += p.vx * (dt / 16);
      p.y += p.vy * (dt / 16);
      p.life -= dt;
      return p.life > 0;
    });

    if (enemies.length === 0) {
      wave++;
      setTimeout(() => spawnWave(), 500);
    }

    enemies.forEach(e => {
      if (aabb(player, e) && !player.invincible) {
        player.lives--;
        player.invincible = 180;
        screenShake = 15;
        combo = 0;
        for (let i = 0; i < 15; i++) addParticle(player.x + player.w / 2, player.y + player.h / 2, COLORS.player, rnd(-5, 5), rnd(-5, 5));
        enemies = enemies.filter(x => x !== e);
        if (player.lives <= 0) gameState = 'GAME_OVER';
      }
    });

    if (screenShake > 0) screenShake -= dt;
  }

  let shootCooldown = 0;
  function handleShoot() {
    if (gameState !== 'PLAYING' || shootCooldown > 0) return;
    shootCooldown = 8;
    shootBullet(player.x + player.w / 2 - 2, player.y, -14, !!player.tripleShot);
  }

  // ========== 繪製 ==========
  function drawPlayer() {
    ctx.save();
    if (screenShake > 0) ctx.translate(rndInt(-3, 3), rndInt(-3, 3));

    const px = player.x, py = player.y;
    ctx.fillStyle = COLORS.player;
    ctx.beginPath();
    ctx.moveTo(px + player.w / 2, py);
    ctx.lineTo(px + player.w, py + player.h);
    ctx.lineTo(px + player.w / 2, py + player.h - 8);
    ctx.lineTo(px, py + player.h);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = COLORS.accent;
    ctx.lineWidth = 1;
    ctx.stroke();

    if (player.shield > 0) {
      ctx.strokeStyle = COLORS.bullet;
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.arc(px + player.w / 2, py + player.h / 2, player.w + 10, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    ctx.restore();
  }

  function drawUI() {
    ctx.fillStyle = COLORS.white;
    ctx.font = '16px monospace';
    ctx.fillText(`Score: ${score}`, 12, 24);
    ctx.fillText(`Wave ${wave}`, 12, 44);
    ctx.fillText(`Lives: ${player.lives}`, W - 100, 24);
    if (combo > 0) {
      ctx.fillStyle = COLORS.accent2;
      ctx.fillText(`Combo x${comboMultiplier.toFixed(1)} (${combo})`, W - 200, 44);
    }
    if (player.tripleShot > 0) ctx.fillText('TRIPLE', W - 80, 64);
    if (player.shield > 0) ctx.fillText('SHIELD', W - 80, 80);
  }

  function drawParticles() {
    particles.forEach(p => {
      ctx.fillStyle = p.color;
      ctx.globalAlpha = p.life / p.maxLife;
      ctx.fillRect(p.x, p.y, p.size, p.size);
    });
    ctx.globalAlpha = 1;
  }

  function draw() {
    const now = performance.now();
    const dt = Math.min(now - lastTime, 50);
    lastTime = now;

    ctx.save();
    if (screenShake > 0 && gameState === 'PLAYING') ctx.translate(rndInt(-4, 4), rndInt(-4, 4));

    drawStars(dt);

    if (gameState === 'LOADING') {
      ctx.fillStyle = COLORS.white;
      ctx.font = '20px monospace';
      ctx.fillText('Loading...', W / 2 - 50, H / 2 - 10);
      ctx.fillStyle = COLORS.nebula3;
      ctx.fillRect(80, H / 2, (W - 160) * (loadProgress / 100), 8);
      ctx.strokeStyle = COLORS.accent;
      ctx.strokeRect(80, H / 2, W - 160, 8);
      ctx.restore();
      return;
    }

    if (gameState === 'MENU') {
      ctx.fillStyle = COLORS.white;
      ctx.font = '36px monospace';
      ctx.fillText('COSMIC SHOOTER', W / 2 - 140, H / 2 - 60);
      ctx.font = '16px monospace';
      ctx.fillText('Press SPACE or Tap to Start', W / 2 - 120, H / 2);
      ctx.fillText('Arrow Keys / WASD: Move | Space: Shoot', W / 2 - 160, H / 2 + 40);
      ctx.fillText('Esc: Pause', W / 2 - 50, H / 2 + 60);
      ctx.restore();
      return;
    }

    if (gameState === 'GAME_OVER') {
      ctx.fillStyle = COLORS.accent;
      ctx.font = '32px monospace';
      ctx.fillText('GAME OVER', W / 2 - 90, H / 2 - 40);
      ctx.fillStyle = COLORS.white;
      ctx.font = '18px monospace';
      ctx.fillText(`Final Score: ${score}`, W / 2 - 70, H / 2);
      ctx.fillText('Press SPACE to Restart', W / 2 - 100, H / 2 + 40);
      ctx.restore();
      return;
    }

    drawBlackHoles();
    drawEnergyWaves();

    enemies.forEach(e => {
      ctx.fillStyle = e.color || COLORS.enemy;
      ctx.fillRect(e.x, e.y, e.w, e.h);
    });

    bullets.forEach(b => {
      if (!b.active) return;
      ctx.fillStyle = COLORS.bullet;
      ctx.fillRect(b.x, b.y, b.w, b.h);
    });

    powerUps.forEach(pu => {
      ctx.fillStyle = COLORS.powerup;
      ctx.fillRect(pu.x, pu.y, pu.w, pu.h);
      ctx.fillStyle = COLORS.nebula1;
      ctx.font = '10px monospace';
      ctx.fillText(pu.type[0].toUpperCase(), pu.x + 6, pu.y + 16);
    });

    drawParticles();
    if (gameState === 'PLAYING') drawPlayer();
    drawUI();

    if (gameState === 'PAUSED') {
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = COLORS.white;
      ctx.font = '28px monospace';
      ctx.fillText('PAUSED', W / 2 - 55, H / 2);
      ctx.font = '14px monospace';
      ctx.fillText('Press Esc to Resume', W / 2 - 70, H / 2 + 30);
    }
    ctx.restore();
  }

  function gameLoop(now) {
    const dt = Math.min(now - lastTime, 50);
    lastTime = now;

    if (gameState === 'PLAYING') {
      if (shootCooldown > 0) shootCooldown -= dt;
      if (keys[' ']) handleShoot();
      updatePlaying(dt);
    }

    draw();
    requestAnimationFrame(gameLoop);
  }

  // ========== 輸入 ==========
  function onKey(e, down) {
    if (e.code === 'Space') e.preventDefault();
    keys[e.code] = down;
    keys[e.key] = down;

    if (e.code === 'Escape' && down) {
      if (gameState === 'PLAYING') gameState = 'PAUSED';
      else if (gameState === 'PAUSED') gameState = 'PLAYING';
    }

    if ((e.code === 'Space' || e.key === ' ') && down) {
      if (gameState === 'MENU') {
        gameState = 'PLAYING';
        resetGame();
      } else if (gameState === 'GAME_OVER') {
        gameState = 'PLAYING';
        resetGame();
      }
    }
  }

  function resetGame() {
    bullets = [];
    enemies = [];
    particles = [];
    powerUps = [];
    blackHoles = [];
    energyWaves = [];
    score = 0;
    combo = 0;
    wave = 1;
    player.x = W / 2 - 20;
    player.y = H - 80;
    player.lives = 3;
    player.invincible = 0;
    player.tripleShot = 0;
    player.shield = 0;
    spawnWave();
  }

  // ========== 預載與啟動 ==========
  function simulateLoad() {
    return new Promise(resolve => {
      const steps = [20, 40, 60, 80, 100];
      let i = 0;
      const id = setInterval(() => {
        loadProgress = steps[i] || 100;
        i++;
        if (loadProgress >= 100) {
          clearInterval(id);
          resolve();
        }
      }, 120);
    });
  }

  function init() {
    canvas = document.getElementById('gameCanvas');
    ctx = canvas.getContext('2d');

    initStars();
    initBulletPool();

    simulateLoad().then(() => {
      gameState = 'MENU';
    });

    document.addEventListener('keydown', e => onKey(e, true));
    document.addEventListener('keyup', e => onKey(e, false));

    canvas.addEventListener('click', e => {
      if (gameState === 'MENU' || gameState === 'GAME_OVER') {
        if (gameState === 'GAME_OVER') resetGame();
        gameState = 'PLAYING';
        resetGame();
      }
    });

    canvas.addEventListener('touchstart', e => {
      e.preventDefault();
      if (gameState === 'MENU' || gameState === 'GAME_OVER') {
        if (gameState === 'GAME_OVER') resetGame();
        gameState = 'PLAYING';
        resetGame();
      } else if (gameState === 'PLAYING') handleShoot();
    }, { passive: false });

    canvas.addEventListener('touchmove', e => e.preventDefault(), { passive: false });

    lastTime = performance.now();
    requestAnimationFrame(gameLoop);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
