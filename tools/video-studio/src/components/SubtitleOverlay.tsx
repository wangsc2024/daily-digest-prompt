import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

interface SubtitleOverlayProps {
  /** TTS 原文（從 storyboard tts_text 帶入） */
  text?: string;
  /** 場景總幀數 */
  durationFrames: number;
}

/**
 * SubtitleOverlay：底部逐組顯示字幕
 * 將文字依空格切分為 tokens，每組 2~3 個 token 為一單位，
 * 依幀數等比例切換，形成同步字幕效果。
 */
export const SubtitleOverlay: React.FC<SubtitleOverlayProps> = ({
  text,
  durationFrames,
}) => {
  const frame = useCurrentFrame();

  if (!text || text.trim().length === 0) return null;

  const tokens = text.trim().split(/\s+/);
  if (tokens.length === 0) return null;

  // 每組 3 個 token（中文字幕較短，3個約 6~9 字）
  const GROUP_SIZE = 3;
  const groups: string[] = [];
  for (let i = 0; i < tokens.length; i += GROUP_SIZE) {
    groups.push(tokens.slice(i, i + GROUP_SIZE).join(" "));
  }

  const framesPerGroup = durationFrames / groups.length;
  const currentGroup = Math.min(
    Math.floor(frame / framesPerGroup),
    groups.length - 1
  );

  // 每組切換時有短暫淡入效果
  const groupStartFrame = currentGroup * framesPerGroup;
  const opacity = interpolate(
    frame,
    [groupStartFrame, groupStartFrame + 6],
    [0.6, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const currentText = groups[currentGroup];

  return (
    <div
      style={{
        position: "absolute",
        bottom: 36,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        zIndex: 90,
        opacity,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0,0,0,0.65)",
          borderRadius: 8,
          padding: "10px 28px",
          maxWidth: "80%",
          textAlign: "center",
        }}
      >
        <span
          style={{
            color: "#f0f0f8",
            fontSize: 28,
            fontFamily: "system-ui, sans-serif",
            lineHeight: 1.4,
            letterSpacing: "0.02em",
          }}
        >
          {currentText}
        </span>
      </div>
    </div>
  );
};
