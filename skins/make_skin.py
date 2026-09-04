#!/usr/bin/env python3
"""마스코트 이미지를 Hermes 스킨(banner_hero)으로 변환한다.

    python skins/make_skin.py <이미지경로> [스킨이름] [폭]

반블록 문자로 한 칸에 두 픽셀을 담아 세로 해상도를 2배로 쓴다
(전경색 = 위 픽셀, 배경색 = 아래 픽셀).
"""
import sys, pathlib, yaml
from PIL import Image

PALETTE = {
    "background": "#0e0f16",
    "banner_border": "#8fb8d8", "banner_title": "#bfe0f5", "banner_accent": "#a9d5ee",
    "banner_dim": "#6f8aa3", "banner_text": "#e8f4fb",
    "ui_accent": "#a9d5ee", "ui_label": "#8fb8d8",
    "ui_ok": "#7fd6a6", "ui_error": "#ef7b8b", "ui_warn": "#f2c46b",
    "ui_tool": "#c3b6ee", "ui_thinking": "#8f9fc0",
    "prompt": "#e8f4fb", "input_rule": "#8fb8d8",
    "syntax_string": "#a9d5ee", "syntax_keyword": "#c3b6ee", "syntax_comment": "#6f8aa3",
}
ALPHA_CUTOFF = 40


def to_art(src: str, width: int = 38) -> str:
    height = width if width % 2 == 0 else width + 1
    im = Image.open(src)
    im.seek(0)                      # 애니메이션이면 첫 프레임
    im = im.convert("RGBA")
    bbox = im.split()[3].getbbox()  # 투명 여백 제거
    if bbox:
        im = im.crop(bbox)
    im = im.resize((width, height), Image.LANCZOS)
    px = im.load()

    def rgb(p):
        r, g, b, a = p
        return None if a < ALPHA_CUTOFF else (r, g, b)

    rows = []
    for y in range(0, height, 2):
        line = ""
        for x in range(width):
            top = rgb(px[x, y])
            bot = rgb(px[x, y + 1]) if y + 1 < height else None
            if top is None and bot is None:
                line += " "
            elif top and bot:
                line += f"[#{top[0]:02x}{top[1]:02x}{top[2]:02x} on #{bot[0]:02x}{bot[1]:02x}{bot[2]:02x}]▀[/]"
            elif top:
                line += f"[#{top[0]:02x}{top[1]:02x}{top[2]:02x}]▀[/]"
            else:
                line += f"[#{bot[0]:02x}{bot[1]:02x}{bot[2]:02x}]▄[/]"
        rows.append(line.rstrip())
    return "\n".join(rows)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    src = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "aing"
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 38

    skin = {
        "name": name,
        "description": f"{name} 마스코트 — 고양이 히어로 아트 + 파스텔 팔레트",
        "colors": PALETTE,
        "tool_prefix": "🐾",
        "banner_hero": to_art(src, width),
    }
    body = yaml.safe_dump(skin, allow_unicode=True, sort_keys=False, width=10**6)

    out = pathlib.Path(__file__).parent / f"{name}.yaml"
    out.write_text(body, encoding="utf-8")
    print(f"작성: {out}")
    for home in (pathlib.Path.home() / ".hermes-poc", pathlib.Path.home() / ".hermes"):
        d = home / "skins"
        if d.parent.exists():
            d.mkdir(exist_ok=True)
            (d / f"{name}.yaml").write_text(body, encoding="utf-8")
            print(f"설치: {d / (name + '.yaml')}")
    print(f"\n활성화:  ./hermess skin use {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
