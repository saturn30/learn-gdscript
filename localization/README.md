# 개인 한국어 번역 원본

이 디렉터리는 이 저장소의 한국어 학습판이 사용하는 번역 원본입니다.

- localization/ko/*.po가 편집 대상인 개인판 카탈로그입니다.
- i18n/ko/*.po는 Godot가 읽는 생성 스냅샷이며, 개발 checkout에서 수동으로 편집하지 않습니다.
- tools/validate_korean_translations.py는 원문 카탈로그와 키·BBCode·코드·치환자를 비교합니다.
- tools/prepare_korean_translations.py는 검증에 성공한 카탈로그만 명시한 일회성 CI 경로에 복사합니다.

## 로컬 검사

프로젝트 의존성을 먼저 설치합니다.

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt

개인판 카탈로그만 검사할 때는 다음 명령을 실행합니다.

    .venv/bin/python tools/validate_korean_translations.py \
      --source-dir localization/ko \
      --reference-dir i18n/ko \
      --report-json build/korean-translation-report.json

CI checkout에서만 다음처럼 materialize합니다. 이 명령은 명시한 --target-dir에
세 카탈로그를 복사하며 현재 개인판 원본을 덮어쓰지 않습니다.

    .venv/bin/python tools/prepare_korean_translations.py \
      --source-dir localization/ko \
      --reference-dir i18n/ko \
      --target-dir i18n/ko

번역 문자열을 바꿀 때는 코드 블록, 수업·실습 ID, glossary의 term, URL,
%s와 같은 치환자를 함께 수정하지 않습니다. 원문 그대로 두어야 하는 항목은
preserved-strings.json에 이유를 기록합니다.

카탈로그에는 기존 번역을 바탕으로 한 번역 보조 결과가 포함되어 있습니다.
자동 검사는 구조적 안전성을 보장하지만 자연스러운 문체와 화면 배치는 별도의
검수 기록(review-status.csv)과 실제 Web 검증으로 확인합니다.

## 글꼴

한국어 본문·굵은 글씨·코드 주석은 `ui/assets/fonts/NotoSansKR-*.ttf`를
fallback으로 사용합니다. 글꼴은 SIL Open Font License 1.1로 배포되며,
동일 디렉터리의 `NotoSansKR-LICENSE.txt`에 고지문을 둡니다.
