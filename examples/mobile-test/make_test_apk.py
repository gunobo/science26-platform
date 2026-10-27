"""플랫폼 테스트용 최소 APK 를 만든다 (휴대폰에 설치되는 앱이 아니다).

모바일 앱 업로드 검사(서명 여부, AndroidManifest 의 패키지명)를 통과하는지만 확인하는 용도라
classes.dex 나 리소스 없이 바이너리 AndroidManifest.xml 과 v1(JAR) 서명만 넣는다.
JDK 의 keytool·jarsigner 가 필요하다.

    python3 make_test_apk.py            # → science26-test.apk
"""

import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

PACKAGE = "kr.bssm.science26.test"
VERSION_CODE = 1
VERSION_NAME = "1.0"
ANDROID_NS = "http://schemas.android.com/apk/res/android"

# 리소스 ID 가 있는 속성 이름은 문자열 풀 앞쪽에 와야 한다 (리소스 맵과 인덱스가 맞물림)
STRINGS = ["versionCode", "versionName", "android", ANDROID_NS, "package", "manifest", PACKAGE, VERSION_NAME]
RES_IDS = [0x0101021B, 0x0101021C]  # android:versionCode, android:versionName
S = {s: i for i, s in enumerate(STRINGS)}
NO = 0xFFFFFFFF
TYPE_STRING, TYPE_INT_DEC = 0x03, 0x10


def chunk(ctype: int, header_size: int, body: bytes) -> bytes:
    return struct.pack("<HHI", ctype, header_size, 8 + len(body)) + body


def string_pool() -> bytes:
    data = b""
    offsets = []
    for s in STRINGS:
        offsets.append(len(data))
        enc = s.encode("utf-16-le")
        data += struct.pack("<H", len(s)) + enc + b"\x00\x00"
    data += b"\x00" * (-len(data) % 4)
    strings_start = 28 + 4 * len(STRINGS)
    header = struct.pack("<IIIII", len(STRINGS), 0, 0, strings_start, 0)
    return chunk(0x0001, 28, header + b"".join(struct.pack("<I", o) for o in offsets) + data)


def node(ctype: int, body: bytes) -> bytes:
    # 줄 번호 1, 주석 없음
    return chunk(ctype, 16, struct.pack("<II", 1, NO) + body)


def attr(ns: int, name: int, raw: int, dtype: int, data: int) -> bytes:
    return struct.pack("<IIIHBBI", ns, name, raw, 8, 0, dtype, data)


def manifest_xml() -> bytes:
    attrs = [
        attr(S[ANDROID_NS], S["versionCode"], NO, TYPE_INT_DEC, VERSION_CODE),
        attr(S[ANDROID_NS], S["versionName"], S[VERSION_NAME], TYPE_STRING, S[VERSION_NAME]),
        attr(NO, S["package"], S[PACKAGE], TYPE_STRING, S[PACKAGE]),
    ]
    start = node(0x0102, struct.pack("<IIHHHHHH", NO, S["manifest"], 20, 20, len(attrs), 0, 0, 0) + b"".join(attrs))
    body = (
        string_pool()
        + chunk(0x0180, 8, b"".join(struct.pack("<I", r) for r in RES_IDS))
        + node(0x0100, struct.pack("<II", S["android"], S[ANDROID_NS]))
        + start
        + node(0x0103, struct.pack("<II", NO, S["manifest"]))
        + node(0x0101, struct.pack("<II", S["android"], S[ANDROID_NS]))
    )
    return chunk(0x0003, 8, body)


def main() -> None:
    out = Path(__file__).with_name("science26-test.apk")
    with tempfile.TemporaryDirectory() as tmp:
        unsigned = Path(tmp) / "unsigned.apk"
        with zipfile.ZipFile(unsigned, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("AndroidManifest.xml", manifest_xml())
        # 매번 새로 만드는 일회용 테스트 키 (저장소에 남기지 않음)
        ks = Path(tmp) / "test.keystore"
        subprocess.run(
            ["keytool", "-genkeypair", "-keystore", str(ks), "-storepass", "science26", "-keypass", "science26",
             "-alias", "science26", "-keyalg", "RSA", "-keysize", "2048", "-validity", "3650",
             "-dname", "CN=science26 test"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["jarsigner", "-keystore", str(ks), "-storepass", "science26", "-keypass", "science26",
             str(unsigned), "science26"],
            check=True, capture_output=True,
        )
        shutil.copy(unsigned, out)
    print(f"만듦: {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
