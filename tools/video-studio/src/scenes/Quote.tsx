import React from "react";
import { AbsoluteFill, Audio, staticFile, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneBackground } from "../components/SceneBackground";
import { SubtitleOverlay } from "../components/SubtitleOverlay";

interface QuoteProps {
  text: string;
  author?: string;
  audioFile?: string;
  imageFile?: string;
  sceneIndex?: number;
  subtitleText?: string;
  durationFrames?: number;
}

export const Quote: React.FC<QuoteProps> = ({
  text,
  author,
  audioFile,
  imageFile,
  sceneIndex = 0,
  subtitleText,
  durationFrames = 150,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, fps * 0.6], [0, 1], {
    extrapolateRight: "clamp",
  });
  const lineHeight = interpolate(frame, [0, fps * 0.5], [0, 130], {
    extrapolateRight: "clamp",
  });
  const textY = interpolate(frame, [fps * 0.2, fps * 0.8], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <SceneBackground imageFile={imageFile} sceneIndex={sceneIndex} />

      {audioFile && <Audio src={staticFile(audioFile)} />}

      <div
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          gap: 48,
          alignItems: "flex-start",
          padding: "60px 100px",
          maxWidth: 1200,
        }}
      >
        {/* 左側色條 */}
        <div
          style={{
            width: 6,
            height: lineHeight,
            background: "linear-gradient(to bottom, #e94560, #ff6b8a)",
            borderRadius: 3,
            flexShrink: 0,
            marginTop: 8,
            boxShadow: "0 0 12px rgba(233,69,96,0.5)",
          }}
        />

        <div style={{ opacity, transform: `translateY(${textY}px)` }}>
          {/* 引號裝飾 */}
          <div
            style={{
              color: "#e94560",
              fontSize: 80,
              fontFamily: "Georgia, serif",
              lineHeight: 0.6,
              marginBottom: 16,
              opacity: 0.6,
            }}
          >
            "
          </div>
          <p
            style={{
              color: "#f0f0f8",
              fontSize: 42,
              fontStyle: "italic",
              lineHeight: 1.6,
              margin: 0,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 2px 12px rgba(0,0,0,0.9)",
            }}
          >
            {text}
          </p>
          {author && (
            <p
              style={{
                color: "#c0c0d8",
                fontSize: 28,
                marginTop: 24,
                fontFamily: "system-ui, sans-serif",
                textShadow: "0 1px 6px rgba(0,0,0,0.8)",
                letterSpacing: "0.05em",
              }}
            >
              — {author}
            </p>
          )}
        </div>
      </div>

      <SubtitleOverlay text={subtitleText} durationFrames={durationFrames} />
    </AbsoluteFill>
  );
};
