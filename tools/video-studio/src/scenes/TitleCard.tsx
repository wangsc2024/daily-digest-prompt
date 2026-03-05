import React from "react";
import { AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneBackground } from "../components/SceneBackground";
import { SubtitleOverlay } from "../components/SubtitleOverlay";

interface TitleCardProps {
  title: string;
  subtitle?: string;
  audioFile?: string;
  imageFile?: string;
  sceneIndex?: number;
  subtitleText?: string;
  durationFrames?: number;
}

export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  subtitle,
  audioFile,
  imageFile,
  sceneIndex = 0,
  subtitleText,
  durationFrames = 150,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [fps * 0.5, fps * 1.2], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [fps * 0.5, fps * 1.2], [30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const subtitleOpacity = interpolate(frame, [fps * 1.2, fps * 2], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const lineWidth = interpolate(frame, [fps * 0.3, fps * 0.8], [0, 240], {
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
          padding: "60px 80px",
          textAlign: "center",
        }}
      >
        {/* 裝飾線 */}
        <div
          style={{
            width: lineWidth,
            height: 4,
            background: "linear-gradient(to right, #e94560, #ff6b8a)",
            marginBottom: 36,
            borderRadius: 2,
            boxShadow: "0 0 12px rgba(233,69,96,0.5)",
          }}
        />

        {/* 主標題 */}
        <h1
          style={{
            color: "#ffffff",
            fontSize: 72,
            fontWeight: 800,
            textAlign: "center",
            margin: 0,
            opacity: titleOpacity,
            transform: `translateY(${titleY}px)`,
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
            fontFamily: "system-ui, sans-serif",
            textShadow: "0 4px 20px rgba(0,0,0,0.9)",
          }}
        >
          {title}
        </h1>

        {/* 副標題 */}
        {subtitle && (
          <p
            style={{
              color: "#d0d0e8",
              fontSize: 34,
              marginTop: 28,
              textAlign: "center",
              opacity: subtitleOpacity,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 2px 10px rgba(0,0,0,0.8)",
              maxWidth: 900,
              lineHeight: 1.4,
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      <SubtitleOverlay text={subtitleText} durationFrames={durationFrames} />
    </AbsoluteFill>
  );
};
