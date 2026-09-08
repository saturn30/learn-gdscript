# 한국어 Web 운영 가이드

이 문서는 `localization/ko`의 한국어 카탈로그로 완전한 한국어 Web 빌드를
재현하고 GitHub Pages에 게시하는 절차를 정리합니다. 한국어 번역 원본은
개인 관리용 `localization/ko/*.po`이고, Godot가 읽는 `i18n/ko/*.po`는 CI의
임시 checkout에서만 materialize합니다.

## 로컬에서 할 수 있는 검사

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/validate_korean_translations.py \
  --source-dir localization/ko \
  --reference-dir i18n/ko
```

검사기는 세 카탈로그의 키, 번역 완성도, fuzzy 플래그, BBCode 태그, 코드
블록, URL, glossary term, `%s`와 `{name}` 형식의 치환자를 확인합니다.
검사에 통과한 카탈로그만 다음 명령으로 일회성 생성 경로에 복사할 수
있습니다.

```sh
.venv/bin/python tools/prepare_korean_translations.py \
  --source-dir localization/ko \
  --reference-dir i18n/ko \
  --target-dir i18n/ko
```

## Web 빌드 재현

Web export는 프로젝트가 고정한 Linux x86_64 Godot 4.6.3 custom binary와
export template을 사용합니다. macOS arm64 개발 환경에서는 해당 바이너리를
직접 실행하지 말고 GitHub Actions의 `Publish Korean Web` workflow를
사용합니다.

CI와 같은 순서는 다음과 같습니다.

```sh
python3 tools/prepare_korean_translations.py \
  --source-dir localization/ko \
  --reference-dir i18n/ko \
  --target-dir i18n/ko
python3 build.py prepare ci-web
./godot_server.x86_64 --headless --path . \
  res://tests/integration_test_course.tscn -- \
  --test-profile=KoreanPublishIntegration --test-locale=ko
./godot_server.x86_64 --headless --path . \
  res://tests/validate_translated_lessons.tscn
python3 build.py export web \
  --output-dir build/korean-web \
  --base-url ""
python3 tools/verify_korean_web_build.py \
  --build-dir build/korean-web \
  --source-commit "$(git rev-parse HEAD)" \
  --report-json build/korean-web-report.json
(cd build && zip -r korean-web.zip korean-web)
```

`--base-url ""`은 output을 특정 브랜치 경로에 묶지 않고 상대 자산 경로로
만듭니다. `verify_korean_web_build.py`는 `index.html`, JavaScript, WASM,
PCK, 로컬 자산 참조, 한국어 HTML, export token 잔존 여부와 원작·한글 폰트
라이선스 파일을 검사하고 `build/korean-web/build-info.json`에 commit·시간·파일
수·전체 크기를 기록합니다. Web 루트에는 `KOREAN-EDITION.md`, `LICENSE`,
`NotoSansKR-LICENSE.txt`도 함께 포함됩니다.

간단한 로컬 미리보기는 `file://` 대신 HTTP 서버를 사용합니다.

```sh
python3 -m http.server 8000 --directory build/korean-web
```

## GitHub Pages 게시

`.github/workflows/PublishKoreanWeb.yaml`은 `main` push 또는 수동
`workflow_dispatch`로 실행됩니다.

1. 번역 원본을 검증하고 checkout 안의 `i18n/ko`에 복사합니다.
2. 한국어 통합 테스트와 모든 번역 lesson 파싱 검사를 실행합니다.
3. 한국어 Web을 export하고 상대 경로·자산·템플릿 token을 검사합니다.
4. `korean-web-output` 디렉터리 artifact와 `korean-web-zip` artifact를
   보존합니다.
5. 전체 export를 `gh-pages` 브랜치의 저장소 루트에 복사하고 commit합니다.

기존 `gh-pages` 브랜치가 있으면 그 브랜치를 기준으로 갱신하고, 없으면
orphan 브랜치를 만들어 첫 게시를 수행합니다. 게시 후 시작점은
`https://<owner>.github.io/<repository>/`이며, 저장소의 Pages 설정에서
배포 소스를 `gh-pages` 브랜치의 root로 한 번 지정해야 합니다. workflow는
Cloudflare 계정, Workers, R2, Wrangler, itch.io 또는 GitHub Release를
사용하지 않습니다.

artifact의 `build-info.json`과 workflow summary에서 실제 source commit과
파일 크기를 확인합니다. Web export가 커지면 summary의 25 MiB 초과 경고와
`total_bytes`를 먼저 확인하고, GitHub Pages 및 저장소 artifact 보존 정책을
검토합니다.

## Cloudflare를 함께 사용할 때

Cloudflare를 사용해야 하는 경우에도 CI에서 자격 증명을 관리하지 않습니다.
먼저 `korean-web-zip`을 내려받아 `build/korean-web`의 정적 파일을
Cloudflare Pages의 수동 배포 화면에 업로드하거나, `gh-pages` root를 별도
정적 호스팅 원본으로 연결합니다. 이후 custom domain, HTTPS, 캐시 정책은
Cloudflare 대시보드에서 수동으로 설정하고, `index.html`과 `.wasm` 응답이
정상인지 브라우저에서 확인합니다.
