import React from "react";
import { AbsoluteFill, Audio, staticFile, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import Prism from "prismjs";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-python";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-json";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-jsx";
import { SceneBackground } from "../components/SceneBackground";

/** Dracula 風格 token 顏色對應 */
const TOKEN_COLORS: Record<string, string> = {
  keyword: "#ff79c6",
  "keyword control-flow": "#ff79c6",
  builtin: "#8be9fd",
  "class-name": "#8be9fd",
  function: "#50fa7b",
  string: "#f1fa8c",
  "template-string": "#f1fa8c",
  number: "#bd93f9",
  boolean: "#bd93f9",
  comment: "#6272a4",
  operator: "#ff79c6",
  punctuation: "#f8f8f2",
  property: "#66d9ef",
  tag: "#ff79c6",
  "attr-name": "#50fa7b",
  "attr-value": "#f1fa8c",
  regex: "#ff5555",
  important: "#ffb86c",
  variable: "#f8f8f2",
  parameter: "#ffb86c",
  default: "#cdd6f4",
};

function getTokenColor(types: string): string {
  for (const key of Object.keys(TOKEN_COLORS)) {
    if (types.includes(key)) return TOKEN_COLORS[key];
  }
  return TOKEN_COLORS.default;
}

/** 將 Prism token 遞迴轉為帶色 span 的 React 元素 */
function renderTokens(tokens: (string | Prism.Token)[], depth = 0): React.ReactNode[] {
  return tokens.map((token, i) => {
    if (typeof token === "string") {
      return <span key={`${depth}-${i}`}>{token}</span>;
    }
    const color = getTokenColor(
      Array.isArray(token.type) ? token.type.join(" ") : token.type
    );
    const children: React.ReactNode = Array.isArray(token.content)
      ? renderTokens(token.content as (string | Prism.Token)[], depth + 1)
      : typeof token.content === "string"
      ? token.content
      : null;
    return (
      <span key={`${depth}-${i}`} style={{ color }}>
        {children}
      </span>
    );
  });
}

interface CodeHighlightProps {
  heading?: string;
  code: string;
  language?: string;
  audioFile?: string;
  imageFile?: string;
  sceneIndex?: number;
}

export const CodeHighlight: React.FC<CodeHighlightProps> = ({
  heading,
  code,
  language = "typescript",
  audioFile,
  imageFile,
  sceneIndex = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Prism 語法染色
  const grammar = Prism.languages[language] || Prism.languages.typescript;
  const tokens = Prism.tokenize(code, grammar);
  const highlighted = renderTokens(tokens);

  return (
    <AbsoluteFill style={{ flexDirection: "column", justifyContent: "center" }}>
      <SceneBackground imageFile={imageFile} sceneIndex={sceneIndex} />

      {audioFile && <Audio src={staticFile(audioFile)} />}

      <div
        style={{
          position: "relative",
          zIndex: 10,
          padding: "50px 80px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          opacity,
        }}
      >
        {heading && (
          <h2
            style={{
              color: "#e94560",
              fontSize: 40,
              fontWeight: 700,
              margin: 0,
              marginBottom: 32,
              fontFamily: "system-ui, sans-serif",
              textShadow: "0 2px 8px rgba(0,0,0,0.8)",
            }}
          >
            {heading}
          </h2>
        )}

        <div
          style={{
            backgroundColor: "rgba(15,15,26,0.85)",
            borderRadius: 12,
            padding: "32px 40px",
            border: "1px solid rgba(233,69,96,0.3)",
            backdropFilter: "blur(4px)",
            position: "relative",
          }}
        >
          {/* 語言標籤 */}
          <div
            style={{
              position: "absolute",
              top: 12,
              right: 20,
              color: "#e94560",
              fontSize: 18,
              fontFamily: "monospace",
              fontWeight: 600,
              opacity: 0.8,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
            }}
          >
            {language}
          </div>

          {/* 三色圓點（macOS 視窗風格） */}
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((color) => (
              <div
                key={color}
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  backgroundColor: color,
                  opacity: 0.8,
                }}
              />
            ))}
          </div>

          <pre
            style={{
              margin: 0,
              lineHeight: 1.7,
              overflowX: "hidden",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontSize: 26,
              fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
            }}
          >
            {highlighted}
          </pre>
        </div>
      </div>
    </AbsoluteFill>
  );
};
