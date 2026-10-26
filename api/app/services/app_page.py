"""앱 타입: APK·스크린샷·설명으로 소개 페이지를 만든다 (F-04). 결과물은 정적 사이트로 배포된다."""

import html
import json
import shutil
from pathlib import Path

import segno


def build_site(release_dir: Path, site: Path, page_url: str) -> None:
    meta = json.loads((release_dir / "meta.json").read_text())
    site.mkdir(parents=True, exist_ok=True)
    shutil.copy(release_dir / "app.apk", site / "app.apk")
    shots_dir = site / "shots"
    shots_dir.mkdir(exist_ok=True)
    shots = []
    for shot in sorted((release_dir / "shots").iterdir()):
        shutil.copy(shot, shots_dir / shot.name)
        shots.append(f"shots/{shot.name}")

    qr = segno.make(page_url + "app.apk", error="m")
    qr_svg = qr.svg_inline(scale=5, dark="#111", light="#fff")

    esc = html.escape
    shots_html = "".join(f'<img src="{s}" alt="스크린샷" loading="lazy">' for s in shots)
    desc = esc(meta["description"]).replace("\n", "<br>")
    version = esc(meta.get("version_name") or "")
    (site / "index.html").write_text(f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(meta["title"])}</title>
<style>
:root{{--bg:#f6f7f9;--fg:#1a1a1a;--muted:#666;--card:#fff;--accent:#16a34a}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--muted:#aaa;--card:#1c1c1c}}}}
*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg)}}
main{{max-width:880px;margin:0 auto;padding:32px 16px}}h1{{margin:0 0 4px;font-size:28px}}
.meta{{color:var(--muted);font-size:14px}}.desc{{line-height:1.7;margin:20px 0}}
.dl{{display:flex;gap:24px;align-items:center;flex-wrap:wrap;background:var(--card);padding:20px;border-radius:14px}}
.btn{{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:14px 22px;
border-radius:10px;font-weight:600}}.qr svg{{width:140px;height:140px;border-radius:8px}}
.shots{{display:flex;gap:12px;overflow-x:auto;padding:20px 0}}.shots img{{height:420px;max-width:80vw;
object-fit:contain;border-radius:12px;background:var(--card)}}
.note{{color:var(--muted);font-size:13px}}
</style></head><body><main>
<h1>{esc(meta["title"])}</h1>
<div class="meta">{esc(meta["package"])}{" · v" + version if version else ""}</div>
<div class="desc">{desc}</div>
<div class="dl">
  <div><a class="btn" href="app.apk" download>APK 다운로드</a>
  <p class="note">안드로이드 기기에서 "출처를 알 수 없는 앱" 설치를 허용해야 합니다.</p></div>
  <div class="qr" title="휴대폰으로 스캔해 다운로드">{qr_svg}</div>
</div>
<div class="shots">{shots_html}</div>
</main></body></html>
""")
