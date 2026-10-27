# 모바일 앱 테스트 재료

대시보드에서 **모바일 앱** 업로드를 손으로 시험해 볼 때 쓰는 파일들이다. E2E(`python -m app.e2e`)도 이 APK 를 기본으로 쓴다.

| 파일 | 용도 |
|---|---|
| `science26-test.apk` | 업로드 검사(서명·패키지명)를 통과하는 최소 APK. **휴대폰에 설치되는 앱은 아니다** |
| `screenshot-1~3.png` | 스크린샷 (540×1170) |
| `demo.mp4` | 5초 시연 영상 (테스트 패턴) |
| `make_test_apk.py` | APK 다시 만들기 (JDK 의 keytool·jarsigner 필요) |

TestFlight 칸에는 형식만 맞는 `https://testflight.apple.com/join/Test1234` 를 넣으면 된다 (실제로 열리지는 않음).
