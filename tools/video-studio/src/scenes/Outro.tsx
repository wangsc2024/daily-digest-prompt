import React from "react";
import { AbsoluteFill, Audio, staticFile, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneBackground } from "../components/SceneBackground";
import { SubtitleOverlay } from "../components/SubtitleOverlay";

interface OutroProps {
  title?: string;
  call_to_action?: string;
  audioFile?: string;
  imageFile?: string;
  sceneIndex?: number;
  subtitleText?: string;
  durationFrames?: number;
}

export const Outro: React.FC<OutroProps> = ({
  title = "感謝觀看",
  call_to_action,
  audioFile,
  imageFile,
  sceneIndex = 0,
  subtitleText,
  durationFrames = 150,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, fps * 0.8], [0, 1], {
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - fps, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const opacity = Math.min(fadeIn, fadeOut);

  // 圓圈擴散
  const circleScale = interpolate(frame, [0, fps * 1.5], [0.4, 1], {
    extrapolateRight: "clamp",
  });
  const circleOpacity = interpolate(frame, [0, fps * 1.2], [0, 1], {
    extrapolateRight: "clamp",
  });

  // 標題從下方升起
  const titleY = interpolate(frame, [fps * 0.6, fps * 1.3], [30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleOpacity = interpolate(frame, [fps * 0.6, fps * 1.3], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column" }}>
      <SceneBackground imageFile={imageFile} sceneIndex={sceneIndex} />

      {audioFile && <Audio src={staticFile(audioFile)} />}

      <div
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          opacity,
        }}
      >
        {/* 裝飾圓圈（雙層） */}
        <div
          style={{
            position: "relative",
            width: 160,
            height: 160,
            marginBottom: 52,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* 外圈 */}
          <div
            style={{
              position: "absolute",
              width: 160,
              height: 160,
              borderRadius: "50%",
              border: "2px solid rgba(233,69,96,0.35)",
              transform: `scale(${circleScale * 1.25})`,
              opacity: circleOpacity * 0.5,
            }}
          />
          {/* 內圈 */}
          <div
            style={{
              width: 130,
              height: 130,
              borderRadius: "50%",
              border: "3px solid #e94560",
              transform: `scale(${circleScale})`,
              opacity: circleOpacity,
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              boxShadow: "0 0 30px rgba(233,69,96,0.4)",
            }}
          >
            <span style={{ color: "#e94560", fontSize: 56, lineHeight: 1 }}>✓</span>
          </div>
        </div>

        {/* 主標題 */}
        <h2
          style={{
            color: "#ffffff",
            fontSize: 64,
            fontWeight: 800,
            margin: 0,
            fontFamily: "system-ui, sans-serif",
            textAlign: "center",
            textShadow: "0 4px 20px rgba(0,0,0,0.9)",
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
          }}
        >
          {title}
        </h2>

        {call_to_action && (
          <p
            style={{
              color: "#c8c8e0",
              fontSize: 30,
              marginTop: 24,
              textAlign: "center",
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 2px 10px rgba(0,0,0,0.8)",
              opacity: titleOpacity,
              maxWidth: 800,
              lineHeight: 1.5,
            }}
          >
            {call_to_action}
          </p>
        )}
      </div>

      <SubtitleOverlay text={subtitleText} durationFrames={durationFrames} />
    </AbsoluteFill>
  );
};
