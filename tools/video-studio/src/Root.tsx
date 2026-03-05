import { Composition } from "remotion";
import { Article } from "./compositions/Article";
import remotionData from "./data/remotion-data.json";

export const RemotionRoot: React.FC = () => {
  const { fps, width, height, totalFrames } = remotionData.meta;

  return (
    <Composition
      id="Article"
      component={Article}
      durationInFrames={totalFrames}
      fps={fps}
      width={width}
      height={height}
    />
  );
};
