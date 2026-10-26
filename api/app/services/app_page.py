"""모바일 앱 타입: APK(안드로이드)·TestFlight 링크(iOS)·시연 영상·스크린샷으로 소개 페이지를 만든다 (F-04).

결과물은 정적 사이트로 배포된다. 세 가지 중 올린 것만 페이지에 나온다.
"""

import html
import json
import shutil
from pathlib import Path

import segno

VIDEO_TYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}


def _qr(url: str) -> str:
    return segno.make(url, error="m").svg_inline(scale=5, dark="#111", light="#fff")


def build_site(release_dir: Path, site: Path, page_url: str) -> None:
    meta = json.loads((release_dir / "meta.json").read_text())
    site.mkdir(parents=True, exist_ok=True)
    esc = html.escape

    shots_dir = site / "shots"
    shots_dir.mkdir(exist_ok=True)
    shots = []
    for shot in sorted((release_dir / "shots").iterdir()):
        shutil.copy(shot, shots_dir / shot.name)
        shots.append(f"shots/{shot.name}")

    blocks = []
    # 예전 릴리스는 meta 에 apk 키가 없고 app.apk 만 있다
    if meta.get("apk") or (release_dir / "app.apk").exists():
        shutil.copy(release_dir / "app.apk", site / "app.apk")
        blocks.append(f"""
<section class="dl">
  <div><h2>Android</h2>
  <a class="btn" href="app.apk" download>APK 다운로드</a>
  <p class="note">안드로이드에서 "출처를 알 수 없는 앱" 설치를 허용해야 해요.</p></div>
  <div class="qr" title="휴대폰으로 스캔해 다운로드">{_qr(page_url + "app.apk")}</div>
</section>""")
    if meta.get("testflight_url"):
        url = meta["testflight_url"]
        blocks.append(f"""
<section class="dl">
  <div><h2>iPhone · iPad</h2>
  <a class="btn" href="{esc(url)}" target="_blank" rel="noopener">TestFlight로 설치</a>
  <p class="note">App Store 에서 TestFlight 앱을 먼저 설치한 뒤 링크를 열어 주세요.</p></div>
  <div class="qr" title="iPhone 카메라로 스캔">{_qr(url)}</div>
</section>""")

    video_html = ""
    if meta.get("video"):
        name = meta["video"]
        shutil.copy(release_dir / name, site / name)
        mime = VIDEO_TYPES.get(Path(name).suffix, "video/mp4")
        video_html = f"""
<section class="video"><h2>시연 영상</h2>
<video controls playsinline preload="metadata"><source src="{esc(name)}" type="{mime}">
이 브라우저는 영상을 재생할 수 없어요. <a href="{esc(name)}">영상 받기</a></video></section>"""

    shots_html = "".join(f'<img src="{s}" alt="스크린샷" loading="lazy">' for s in shots)
    desc = esc(meta["description"]).replace("\n", "<br>")
    version = esc(meta.get("version_name") or "")
    sub = esc(meta.get("package") or "")
    if sub and version:
        sub += f" · v{version}"

    (site / "index.html").write_text(f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(meta["title"])}</title>
<style>
:root{{--bg:#f4f4f5;--fg:#18181b;--muted:#62626b;--card:#fcfcfc;--border:#e4e4e7;--accent:#047857;--on:#f8fffc}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f0f11;--fg:#f2f2f3;--muted:#a1a1aa;--card:#18181b;--border:#2a2a2f;--accent:#34d399;--on:#062b1f}}}}
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif;background:var(--bg);color:var(--fg)}}
main{{max-width:880px;margin:0 auto;padding:36px 16px 64px}}h1{{margin:0 0 4px;font-size:30px;letter-spacing:-.8px}}
h2{{margin:0 0 12px;font-size:16px}}.meta{{color:var(--muted);font-size:14px}}.desc{{line-height:1.7;margin:20px 0}}
section{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:20px;margin-top:14px}}
.dl{{display:flex;gap:24px;align-items:center;justify-content:space-between;flex-wrap:wrap}}
.btn{{display:inline-block;background:var(--accent);color:var(--on);text-decoration:none;padding:13px 20px;border-radius:10px;font-weight:700}}
.qr svg{{width:130px;height:130px;border-radius:8px}}.note{{color:var(--muted);font-size:13px;margin:10px 0 0}}
video{{width:100%;max-height:70vh;border-radius:10px;background:#000}}
.shots{{display:flex;gap:12px;overflow-x:auto;padding:20px 0}}.shots img{{height:420px;max-width:80vw;object-fit:contain;border-radius:12px;background:var(--card)}}
</style></head><body><main>
<h1>{esc(meta["title"])}</h1>
{f'<div class="meta">{sub}</div>' if sub else ''}
<div class="desc">{desc}</div>
{"".join(blocks)}
{video_html}
<div class="shots">{shots_html}</div>
</main></body></html>
""")
