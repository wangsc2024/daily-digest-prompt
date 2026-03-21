#!/usr/bin/env python3
"""Write the Phantom Butterfly Nebula game files."""
import os

GAME_DIR = "D:/Source/game/phantom-butterfly"
os.makedirs(f"{GAME_DIR}/js", exist_ok=True)
os.makedirs(f"{GAME_DIR}/assets", exist_ok=True)

# Read parts and combine
parts = []
for i in range(1, 10):
    path = f"D:/Source/daily-digest-prompt/tmp/game_part{i}.js"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            parts.append(f.read())

content = "\n".join(parts)
with open(f"{GAME_DIR}/js/game.js", "w", encoding="utf-8") as f:
    f.write(content)
print(f"game.js written ({len(content)} chars, {content.count(chr(10))} lines)")
