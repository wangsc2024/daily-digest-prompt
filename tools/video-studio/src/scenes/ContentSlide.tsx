import React from "react";
import { AbsoluteFill, Audio, staticFile, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import {
  CheckCircle2,
  Zap,
  Brain,
  Code2,
  ArrowRight,
  Star,
  Target,
  Lightbulb,
  Shield,
  Database,
  Globe,
  Settings,
} from "lucide-react";
import { SceneBackground } from "../components/SceneBackground";
import { SubtitleOverlay } from "../components/SubtitleOverlay";

const ICONS = [CheckCircle2, Zap, Brain, ArrowRight, Star, Target, Lightbulb, Shield, Database, Globe, Settings, Code2];

interface ContentSlideProps {
  heading: string;
  bullet_points: string[];
  audioFile?: string;
  imageFile?: string;
  sceneIndex?: number;
  subtitleText?: string;
  durationFrames?: number;
}

export const ContentSlide: React.FC<ContentSlideProps> = ({
  heading,
  bullet_points,
  audioFile,
  imageFile,
  sceneIndex = 0,
  subtitleText,
  durationFrames = 150,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const isGrid = bullet_points.length >= 4;

  const headingOpacity = interpolate(frame, [0, fps * 0.4], [0, 1], {
    extrapolateRight: "clamp",
  });
  const headingY = interpolate(frame, [0, fps * 0.4], [20, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ flexDirection: "column", justifyContent: "center" }}>
      <SceneBackground imageFile={imageFile} sceneIndex={sceneIndex} />

      {audioFile && <Audio src={staticFile(audioFile)} />}

      <div
        style={{
          position: "relative",
          zIndex: 10,
          padding: isGrid ? "50px 70px" : "60px 80px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          flex: 1,
        }}
      >
        {/* 章節標題 */}
        <h2
          style={{
            color: "#ffffff",
            fontSize: isGrid ? 42 : 48,
            fontWeight: 700,
            margin: 0,
            marginBottom: 36,
            opacity: headingOpacity,
            transform: `translateY(${headingY}px)`,
            fontFamily: "system-ui, sans-serif",
            borderLeft: "6px solid #e94560",
            paddingLeft: 24,
            textShadow: "0 2px 12px rgba(0,0,0,0.9)",
          }}
        >
          {heading}
        </h2>

        {isGrid ? (
          /* 4+ 項目：2 欄卡片 Grid */
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 20,
            }}
          >
            {bullet_points.map((point, idx) => (
              <BulletCard
                key={idx}
                text={point}
                idx={idx}
                frame={frame}
                fps={fps}
                icon={ICONS[idx % ICONS.length]}
              />
            ))}
          </div>
        ) : (
          /* ≤3 項目：大字垂直排列 */
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {bullet_points.map((point, idx) => (
              <BulletRow
                key={idx}
                text={point}
                idx={idx}
                frame={frame}
                fps={fps}
                icon={ICONS[idx % ICONS.length]}
              />
            ))}
          </ul>
        )}
      </div>

      <SubtitleOverlay text={subtitleText} durationFrames={durationFrames} />
    </AbsoluteFill>
  );
};

/** 卡片形式條列項（4+ 項目時用） */
const BulletCard: React.FC<{
  text: string;
  idx: number;
  frame: number;
  fps: number;
  icon: React.ElementType;
}> = ({ text, idx, frame, fps, icon: Icon }) => {
  const col = idx % 2;
  const row = Math.floor(idx / 2);
  const delay = fps * 0.3 + (row * 2 + col) * fps * 0.15;

  const opacity = interpolate(frame, [delay, delay + fps * 0.25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [delay, delay + fps * 0.25], [0.92, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `scale(${scale})`,
        backgroundColor: "rgba(255,255,255,0.07)",
        border: "1px solid rgba(233,69,96,0.25)",
        borderRadius: 12,
        padding: "22px 26px",
        display: "flex",
        alignItems: "flex-start",
        gap: 16,
        backdropFilter: "blur(4px)",
      }}
    >
      <Icon
        size={28}
        color="#e94560"
        style={{ flexShrink: 0, marginTop: 2 }}
      />
      <span
        style={{
          color: "#e8e8f4",
          fontSize: 26,
          lineHeight: 1.45,
          fontFamily: "system-ui, sans-serif",
          textShadow: "0 1px 4px rgba(0,0,0,0.6)",
        }}
      >
        {text}
      </span>
    </div>
  );
};

/** 行形式條列項（≤3 項目時用） */
const BulletRow: React.FC<{
  text: string;
  idx: number;
  frame: number;
  fps: number;
  icon: React.ElementType;
}> = ({ text, idx, frame, fps, icon: Icon }) => {
  const delay = fps * 0.4 + idx * fps * 0.3;

  const opacity = interpolate(frame, [delay, delay + fps * 0.3], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const translateX = interpolate(frame, [delay, delay + fps * 0.3], [-40, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <li
      style={{
        color: "#e0e0f0",
        fontSize: 38,
        marginBottom: 28,
        opacity,
        transform: `translateX(${translateX}px)`,
        fontFamily: "system-ui, sans-serif",
        display: "flex",
        alignItems: "center",
        gap: 20,
        textShadow: "0 2px 8px rgba(0,0,0,0.8)",
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(233,69,96,0.15)",
          borderRadius: "50%",
          padding: 8,
          display: "flex",
          border: "1px solid rgba(233,69,96,0.4)",
          flexShrink: 0,
        }}
      >
        <Icon size={24} color="#e94560" />
      </div>
      {text}
    </li>
  );
};
