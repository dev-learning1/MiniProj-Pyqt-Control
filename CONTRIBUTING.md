# 커밋 메시지 규칙

이 프로젝트의 커밋 메시지는 [Conventional Commits](https://www.conventionalcommits.org/)를 따릅니다.
(참고로 이 프로젝트는 Node.js 툴체인을 쓰지 않아 commitlint를 통한 자동 검증은 하지 않습니다. 아래 규칙을 수동으로 지켜주세요.)

## 형식

```
<type>(<scope>): <subject>

<body(선택)>
```

- `type`은 아래 목록 중 하나만 사용합니다.
- `scope`는 선택 사항입니다. 변경 범위가 명확할 때만 붙입니다. 예: `feat(dashboard): ...`, `fix(nav): ...`
- `subject`(제목)는 100자 이내, 마침표(`.`)로 끝내지 않습니다.
- `body`를 쓸 경우 제목과 body 사이에 빈 줄을 하나 둡니다.

## 허용 타입

| type       | 의미                        |
|------------|-----------------------------|
| `feat`     | 새 기능 추가                |
| `fix`      | 버그 수정                   |
| `docs`     | 문서 변경                   |
| `style`    | 코드 포맷 변경 (기능 변화 없음) |
| `refactor` | 리팩토링                    |
| `test`     | 테스트 추가/수정             |
| `chore`    | 빌드/설정 변경               |
| `revert`   | 커밋 되돌리기                |

## 예시

```
feat: 키워드 선택 UI 구현
fix: 토큰 생성 API 오류 수정
docs: API 명세서 업데이트
refactor: 컴포넌트 구조 개선
feat(dashboard): 연결 상태 3단계(정상/불안정/끊김) 표시
fix(ros_bridge): 미연결 상태에서 끊김 로그가 안 남는 문제 수정
```
