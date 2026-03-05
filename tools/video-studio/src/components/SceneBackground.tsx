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
 * SceneBackground：AI 圖片背景 + Ken Burns 緩慢縮放視差 + 漸層遮罩
 * 無 imageFile 時 fallback 為粒子動畫純色背景
 */
export const SceneBackground: React.FC<SceneBackgroundProps> = ({
  imageFile,
  sceneIndex = 0,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  // Ken Burns：慢速縮放 1.0 → 1.08
  const scale = interpolate(frame, [0, durationInFrames], [1.0, 1.08], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 左右微移：奇偶場景交替方向（±20px），增加動感
  const direction = sceneIndex % 2 === 0 ? 1 : -1;
  const translateX = interpolate(frame, [0, durationInFrames], [0, 20 * direction], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const translateY = interpolate(frame, [0, durationInFrames], [0, 8], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (imageFile) {
    return (
      <AbsoluteFill style={{ overflow: "hidden" }}>
        {/* AI 圖片 + Ken Burns 動畫 */}
        <Img
          src={staticFile(imageFile)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale}) translate(${translateX}px, ${translateY}px)`,
            transformOrigin: "center center",
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

/** 無圖片時的 fallback：動態粒子 + 脈動光暈 */
const FallbackBackground: React.FC<{ frame: number }> = ({ frame }) => {
  const t = frame / 30; // 秒數

  // 左上角藍色光暈脈動
  const blueOpacity = 0.12 + 0.05 * Math.sin(t * 0.8);
  // 右下角紅色光暈脈動（相位偏移）
  const redOpacity = 0.10 + 0.04 * Math.sin(t * 0.6 + 1.2);

  // 預先計算 20 個粒子的位置（用固定 seed 避免每幀重算）
  const particles = PARTICLES.map((p) => ({
    ...p,
    x: p.baseX + p.rangeX * Math.sin(t * p.speedX + p.phaseX),
    y: p.baseY + p.rangeY * Math.cos(t * p.speedY + p.phaseY),
    opacity: 0.2 + 0.15 * Math.sin(t * p.speedO + p.phaseO),
  }));

  return (
    <AbsoluteFill style={{ backgroundColor: "#0f0f1a", overflow: "hidden" }}>
      {/* 光暈 */}
      <div
        style={{
          position: "absolute",
          top: -200,
          left: -200,
          width: 600,
          height: 600,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(59,130,246,${blueOpacity}) 0%, transparent 70%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: -200,
          right: -200,
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(233,69,96,${redOpacity}) 0%, transparent 70%)`,
        }}
      />
      {/* 粒子 */}
      <svg style={{ position: "absolute", width: "100%", height: "100%" }}>
        {particles.map((p) => (
          <circle
            key={p.id}
            cx={`${p.x}%`}
            cy={`${p.y}%`}
            r={p.r}
            fill="#e0e0f0"
            opacity={p.opacity}
          />
        ))}
      </svg>
    </AbsoluteFill>
  );
};

/** 固定粒子資料（避免每次渲染重新計算隨機值） */
const PARTICLES = Array.from({ length: 20 }, (_, i) => {
  const seed = (i * 137.508) % 1;
  const seed2 = (i * 97.333) % 1;
  const seed3 = (i * 61.618) % 1;
  return {
    id: i,
    baseX: (seed * 100),
    baseY: (seed2 * 100),
    rangeX: 2 + seed3 * 4,
    rangeY: 1.5 + seed * 3,
    speedX: 0.3 + seed2 * 0.5,
    speedY: 0.2 + seed3 * 0.4,
    speedO: 0.4 + seed * 0.6,
    phaseX: seed * Math.PI * 2,
    phaseY: seed2 * Math.PI * 2,
    phaseO: seed3 * Math.PI * 2,
    r: 1.5 + seed * 2.5,
  };
});
