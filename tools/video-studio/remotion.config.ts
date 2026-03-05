import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

// Windows 相容性：使用 ANGLE OpenGL 渲染，避免 EPERM kill 錯誤
Config.setChromiumOpenGlRenderer("angle");

// 預設並行數設為 1，降低 Windows 上多 Chrome 實例衝突機率
Config.setConcurrency(1);
