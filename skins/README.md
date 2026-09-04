# 스킨

배너 히어로 아트와 팔레트를 바꾼다. **upstream을 수정하지 않는다** —
`hermes_cli/skin_engine.py`가 제공하는 정식 확장점(`banner_hero`)을 쓴다.

## 설치

```bash
cp skins/aing.yaml ~/.hermes-poc/skins/
./hermess skin use aing
```

`./hermess skin list` 로 확인. 되돌리려면 `./hermess skin use default`.

## aing

`~/Project/psw/mascot/motion/wave.webp` 첫 프레임을 반블록(`▀`/`▄`) 컬러 아트로 변환했다.
세로 해상도를 2배로 쓰려고 한 칸에 두 픽셀(전경=위, 배경=아래)을 넣는다.

기본 카두케우스(⚕) 대신 마스코트가 뜨고, tool prefix는 `🐾`다.

## 다시 생성하기

마스코트를 바꾸거나 다른 포즈(`idle` `type` `jump` `think` `celebrate`)로 갈아끼울 때:

```bash
uv run --project hermes-agent python skins/make_skin.py \
    ~/Project/psw/mascot/motion/wave.webp aing
```
