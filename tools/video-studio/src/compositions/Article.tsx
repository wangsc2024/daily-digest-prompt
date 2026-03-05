import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { CodeHighlight } from "../scenes/CodeHighlight";
import { ContentSlide } from "../scenes/ContentSlide";
import { Outro } from "../scenes/Outro";
import { Quote } from "../scenes/Quote";
import { SplitView } from "../scenes/SplitView";
import { TitleCard } from "../scenes/TitleCard";
import { ProgressBar } from "../components/ProgressBar";
import remotionData from "../data/remotion-data.json";

const TRANSITION_FRAMES = 15; // 0.5s @ 30fps

type SceneType =
  | "title_card"
  | "content_slide"
  | "code_highlight"
  | "quote"
  | "split_view"
  | "outro";

interface SceneData {
  id: string;
  type: SceneType;
  durationFrames: number;
  audioFile?: string;
  imageFile?: string | null;
  props: Record<string, unknown>;
}

function renderScene(scene: SceneData, sceneIndex: number) {
  const audio = scene.audioFile || undefined;
  const image = scene.imageFile || undefined;
  const p = scene.props;

  switch (scene.type) {
    case "title_card":
      return (
        <TitleCard
          title={String(p.title ?? "")}
          subtitle={p.subtitle ? String(p.subtitle) : undefined}
          audioFile={audio}
          imageFile={image}
          sceneIndex={sceneIndex}
        />
      );
    case "content_slide":
      return (
        <ContentSlide
          heading={String(p.heading ?? "")}
          bullet_points={Array.isArray(p.bullet_points) ? p.bullet_points.map(String) : []}
          audioFile={audio}
          imageFile={image}
          sceneIndex={sceneIndex}
        />
      );
    case "code_highlight":
      return (
        <CodeHighlight
          heading={p.heading ? String(p.heading) : undefined}
          code={String(p.code ?? "")}
          language={p.language ? String(p.language) : "typescript"}
          audioFile={audio}
          imageFile={image}
          sceneIndex={sceneIndex}
        />
      );
    case "quote":
      return (
        <Quote
          text={String(p.text ?? "")}
          author={p.author ? String(p.author) : undefined}
          audioFile={audio}
          imageFile={image}
          sceneIndex={sceneIndex}
        />
      );
    case "split_view":
      return (
        <SplitView
          heading={String(p.heading ?? "")}
          body_text={String(p.body_text ?? "")}
          note={p.note ? String(p.note) : undefined}
          audioFile={audio}
          imageFile={image}
          sceneIndex={sceneIndex}
        />
      );
    case "outro":
      return (
        <Outro
          title={p.title ? String(p.title) : undefined}
          call_to_action={p.call_to_action ? String(p.call_to_action) : undefined}
          audioFile={audio}
          imageFile={image}
          sceneIndex={sceneIndex}
        />
      );
    default:
      return <AbsoluteFill style={{ backgroundColor: "#0f0f1a" }} />;
  }
}

/** 右上角章節標記 */
const ChapterIndicator: React.FC<{
  current: number;
  total: number;
  durationFrames: number;
}> = ({ current, total, durationFrames }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(
    frame,
    [0, 15, durationFrames - 15, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        position: "absolute",
        top: 20,
        right: 28,
        opacity,
        zIndex: 90,
        display: "flex",
        alignItems: "center",
        gap: 6,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(0,0,0,0.50)",
          borderRadius: 20,
          padding: "5px 14px",
          border: "1px solid rgba(233,69,96,0.4)",
        }}
      >
        <span
          style={{
            color: "#e94560",
            fontSize: 20,
            fontFamily: "system-ui, sans-serif",
            fontWeight: 600,
            letterSpacing: "0.05em",
          }}
        >
          {current}
        </span>
        <span
          style={{
            color: "#a0a0b8",
            fontSize: 20,
            fontFamily: "system-ui, sans-serif",
          }}
        >
          {" "}/ {total}
        </span>
      </div>
    </div>
  );
};

export const Article: React.FC = () => {
  const scenes = remotionData.scenes as SceneData[];
  const totalScenes = scenes.length;

  return (
    <AbsoluteFill>
      {/* 頂部全域進度條 */}
      <ProgressBar />

      {/* 場景序列（TransitionSeries 支援淡入淡出過渡） */}
      <TransitionSeries>
        {scenes.map((scene, index) => (
          <React.Fragment key={scene.id}>
            <TransitionSeries.Sequence
              durationInFrames={scene.durationFrames}
            >
              <AbsoluteFill>
                {renderScene(scene, index)}
                {/* 右上角章節標記 */}
                <ChapterIndicator
                  current={index + 1}
                  total={totalScenes}
                  durationFrames={scene.durationFrames}
                />
              </AbsoluteFill>
            </TransitionSeries.Sequence>

            {/* 最後一個場景後不加過渡 */}
            {index < scenes.length - 1 && (
              <TransitionSeries.Transition
                presentation={fade()}
                timing={linearTiming({ durationInFrames: TRANSITION_FRAMES })}
              />
            )}
          </React.Fragment>
        ))}
      </TransitionSeries>
    </AbsoluteFill>
  );
};
