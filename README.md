# Feeltech Quiz

Flask + SQLite 기반 퀴즈 MVP입니다.

## 빠른 시작

1) 의존성 설치

```bash
pip install flask
```

2) 시드 데이터 적재

```bash
python3 scripts/seed_db.py
```

3) 서버 실행

```bash
python3 -m app.main
```

브라우저에서 `http://127.0.0.1:5000` 접속

## 데이터 구조
- `data/seed_questions.json`: 문제 시드
- `data/seed_videos.json`: 개념 태그별 유튜브 링크

## 확장 아이디어
- 주제별 카테고리 확장
- 관리자 페이지(문제/영상 CRUD)
- 로그인/점수 이력 페이지
