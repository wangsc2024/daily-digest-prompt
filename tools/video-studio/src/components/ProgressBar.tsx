import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

/**
 * ProgressBar：頂部全域進度條
 * 在 Article.tsx 最外層疊加，顯示整體影片播放進度
 */
export const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const progress = Math.min(frame / durationInFrames, 1);

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: 4,
        backgroundColor: "rgba(255,255,255,0.10)",
        zIndex: 100,
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${progress * 100}%`,
          background: "linear-gradient(to right, #e94560, #ff6b8a)",
          borderRadius: "0 2px 2px 0",
          boxShadow: "0 0 8px rgba(233,69,96,0.6)",
          transition: "width 0.033s linear",
        }}
      />
    </div>
  );
};
