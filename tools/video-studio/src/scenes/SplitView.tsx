import React from "react";
import { AbsoluteFill, Audio, staticFile, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneBackground } from "../components/SceneBackground";
import { SubtitleOverlay } from "../components/SubtitleOverlay";

interface SplitViewProps {
  heading: string;
  body_text: string;
  note?: string;
  audioFile?: string;
  imageFile?: string;
  sceneIndex?: number;
  subtitleText?: string;
  durationFrames?: number;
}

export const SplitView: React.FC<SplitViewProps> = ({
  heading,
  body_text,
  note,
  audioFile,
  imageFile,
  sceneIndex = 0,
  subtitleText,
  durationFrames = 150,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const leftOpacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });
  const leftX = interpolate(frame, [0, fps * 0.5], [-40, 0], {
    extrapolateRight: "clamp",
  });
  const rightOpacity = interpolate(frame, [fps * 0.3, fps * 0.8], [0, 1], {
    extrapolateRight: "clamp",
  });
  const rightX = interpolate(frame, [fps * 0.3, fps * 0.8], [40, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ flexDirection: "row" }}>
      <SceneBackground imageFile={imageFile} sceneIndex={sceneIndex} />

      {audioFile && <Audio src={staticFile(audioFile)} />}

      <div
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          flexDirection: "row",
          padding: "60px 80px",
          gap: 60,
          width: "100%",
          alignItems: "center",
        }}
      >
        {/* 左側：標題 + 主文 */}
        <div
          style={{
            flex: 1,
            justifyContent: "center",
            display: "flex",
            flexDirection: "column",
            opacity: leftOpacity,
            transform: `translateX(${leftX}px)`,
          }}
        >
          <h2
            style={{
              color: "#e94560",
              fontSize: 44,
              fontWeight: 700,
              margin: 0,
              marginBottom: 24,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 2px 10px rgba(0,0,0,0.9)",
              borderLeft: "5px solid #e94560",
              paddingLeft: 20,
            }}
          >
            {heading}
          </h2>
          <p
            style={{
              color: "#e8e8f4",
              fontSize: 30,
              lineHeight: 1.65,
              margin: 0,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 1px 6px rgba(0,0,0,0.8)",
            }}
          >
            {body_text}
          </p>
        </div>

        {/* 右側：備注區塊（毛玻璃效果） */}
        <div
          style={{
            flex: 1,
            justifyContent: "center",
            display: "flex",
            flexDirection: "column",
            opacity: rightOpacity,
            transform: `translateX(${rightX}px)`,
            backgroundColor: "rgba(255,255,255,0.07)",
            borderRadius: 16,
            padding: "40px 48px",
            border: "1px solid rgba(233,69,96,0.25)",
            backdropFilter: "blur(8px)",
          }}
        >
          <p
            style={{
              color: "#c8c8e0",
              fontSize: 27,
              lineHeight: 1.75,
              margin: 0,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 1px 4px rgba(0,0,0,0.7)",
            }}
          >
            {note || ""}
          </p>
        </div>
      </div>

      <SubtitleOverlay text={subtitleText} durationFrames={durationFrames} />
    </AbsoluteFill>
  );
};
