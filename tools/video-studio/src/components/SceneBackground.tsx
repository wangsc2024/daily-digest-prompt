import React from "react";
import {
  AbsoluteFill,
  Img,
  staticFile,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface SceneBackgroundProps {
  /** remotion-data.json 中的 imageFile 欄位，相對於 public/ */
  imageFile?: string | null;
  /** 場景在整個影片中的索引，決定 Ken Burns 移動方向 */
  sceneIndex?: number;
}

/**
 * SceneBackground：圖片背景 + 五種運鏡微動畫 + 入場聚焦 + 亮度脈動 + 光暈掃過
 * 無 imageFile 時 fallback 為粒子動畫純色背景
 */
export const SceneBackground: React.FC<SceneBackgroundProps> = ({
  imageFile,
  sceneIndex = 0,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames, fps } = useVideoConfig();
  const mode = sceneIndex % 5;

  // ── 1. 五種運鏡模式 ───────────────────────────────────────
  let scale: number;
  let translateX: number;
  let translateY: number;

  if (mode === 0) {
    // 緩慢推進 + 右移
    scale = interpolate(frame, [0, durationInFrames], [1.0, 1.1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateX = interpolate(frame, [0, durationInFrames], [0, 30], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateY = 0;
  } else if (mode === 1) {
    // 緩慢拉遠 + 左移
    scale = interpolate(frame, [0, durationInFrames], [1.1, 1.0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateX = interpolate(frame, [0, durationInFrames], [0, -25], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateY = 0;
  } else if (mode === 2) {
    // 對角線漂移
    scale = interpolate(frame, [0, durationInFrames], [1.04, 1.08], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateX = interpolate(frame, [0, durationInFrames], [-15, 15], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    translateY = interpolate(frame, [0, durationInFrames], [-10, 10], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  } else if (mode === 3) {
    // 垂直下移
    scale = 1.06;
    translateX = 0;
    translateY = interpolate(frame, [0, durationInFrames], [-20, 20], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  } else {
    // 弧形呼吸：scale 1.0→1.05→1.02，X sin 波 ±15px
    scale = interpolate(
      frame,
      [0, durationInFrames * 0.5, durationInFrames],
      [1.0, 1.05, 1.02],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
    );
    const t = (frame / fps) * 0.5;
    translateX = 15 * Math.sin(t);
    translateY = 0;
  }

  // ── 2. 入場聚焦（前 15 幀 blur 8px → 0px）──────────────────
  const blurPx = interpolate(frame, [0, 15], [8, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // ── 3. 亮度脈動（整個場景 ±8%）────────────────────────────
  const brightness = 0.92 + 0.08 * Math.sin((frame / fps) * 0.4);

  // ── 4. 光暈掃過（前 1.5s 左→右）──────────────────────────
  const shimmerX = interpolate(frame, [0, fps * 1.5], [-150, 150], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (imageFile) {
    return (
      <AbsoluteFill style={{ overflow: "hidden" }}>
        {/* 圖片 + 運鏡 + 入場聚焦 + 亮度脈動 */}
        <Img
          src={staticFile(imageFile)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
            transformOrigin: "center center",
            filter: `blur(${blurPx}px) brightness(${brightness})`,
          }}
        />
        {/* 光暈掃過（斜向半透明白色漸層） */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(105deg, transparent 38%, rgba(255,255,255,0.12) 50%, transparent 62%)",
            transform: `translateX(${shimmerX}%)`,
            pointerEvents: "none",
          }}
        />
        {/* 深色漸層遮罩：確保上方文字清晰可讀 */}
        <AbsoluteFill
          style={{
            background:
              "linear-gradient(to bottom, rgba(15,15,26,0.35) 0%, rgba(15,15,26,0.60) 50%, rgba(15,15,26,0.88) 100%)",
          }}
        />
      </AbsoluteFill>
    );
  }

  // Fallback：粒子動畫純色背景
  return <FallbackBackground frame={frame} />;
};

/** 無圖片時的 fallback：漸層背景 + 動態粒子 + 脈動光暈 */
const FallbackBackground: React.FC<{ frame: number }> = ({ frame }) => {
  const t = frame / 30;

  // 藍色光暈脈動（左上）
  const blueScale = 1 + 0.08 * Math.sin(t * 0.5);
  const blueOpacity = 0.45 + 0.12 * Math.sin(t * 0.7);
  // 紅色光暈脈動（右下，相位偏移）
  const redScale = 1 + 0.06 * Math.sin(t * 0.4 + 1.5);
  const redOpacity = 0.35 + 0.10 * Math.sin(t * 0.6 + 1.2);
  // 中央紫色光暈（緩慢呼吸）
  const purpleOpacity = 0.15 + 0.07 * Math.sin(t * 0.3 + 0.8);

  const particles = PARTICLES.map((p) => ({
    ...p,
    x: p.baseX + p.rangeX * Math.sin(t * p.speedX + p.phaseX),
    y: p.baseY + p.rangeY * Math.cos(t * p.speedY + p.phaseY),
    opacity: 0.5 + 0.3 * Math.sin(t * p.speedO + p.phaseO),
  }));

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* 基底深色漸層（比純色更有層次） */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: "linear-gradient(135deg, #0a0a18 0%, #0f0f2a 40%, #12081a 100%)",
        }}
      />

      {/* 藍色光暈（左上，大範圍） */}
      <div
        style={{
          position: "absolute",
          top: -150,
          left: -150,
          width: 700,
          height: 700,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(59,130,246,${blueOpacity}) 0%, transparent 65%)`,
          transform: `scale(${blueScale})`,
        }}
      />

      {/* 紅色光暈（右下） */}
      <div
        style={{
          position: "absolute",
          bottom: -100,
          right: -100,
          width: 600,
          height: 600,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(233,69,96,${redOpacity}) 0%, transparent 65%)`,
          transform: `scale(${redScale})`,
        }}
      />

      {/* 中央紫色光暈（深度感） */}
      <div
        style={{
          position: "absolute",
          top: "30%",
          left: "35%",
          width: 500,
          height: 400,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(139,92,246,${purpleOpacity}) 0%, transparent 70%)`,
        }}
      />

      {/* 細格線紋理（增加質感） */}
      <svg
        style={{ position: "absolute", width: "100%", height: "100%", opacity: 0.06 }}
      >
        <defs>
          <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
            <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#a0a0f0" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>

      {/* 浮動粒子 */}
      <svg style={{ position: "absolute", width: "100%", height: "100%" }}>
        {particles.map((p) => (
          <circle
            key={p.id}
            cx={`${p.x}%`}
            cy={`${p.y}%`}
            r={p.r}
            fill={p.id % 3 === 0 ? "#6ea8fe" : p.id % 3 === 1 ? "#e94560" : "#c084fc"}
            opacity={p.opacity}
          />
        ))}
      </svg>
    </AbsoluteFill>
  );
};

/** 固定粒子資料（避免每次渲染重新計算隨機值） */
const PARTICLES = Array.from({ length: 28 }, (_, i) => {
  const seed = (i * 137.508) % 1;
  const seed2 = (i * 97.333) % 1;
  const seed3 = (i * 61.618) % 1;
  return {
    id: i,
    baseX: seed * 100,
    baseY: seed2 * 100,
    rangeX: 3 + seed3 * 5,
    rangeY: 2 + seed * 4,
    speedX: 0.2 + seed2 * 0.4,
    speedY: 0.15 + seed3 * 0.35,
    speedO: 0.3 + seed * 0.5,
    phaseX: seed * Math.PI * 2,
    phaseY: seed2 * Math.PI * 2,
    phaseO: seed3 * Math.PI * 2,
    r: 2.5 + seed * 4,   // 更大的粒子
  };
});
