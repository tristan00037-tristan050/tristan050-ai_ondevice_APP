# 인계 패키지 도구

## restore_permissions.sh — 권한복구

T7 외장(exFAT, noowners)으로 전달한 인계 폴더를 맥 내장 디스크로 복사하면 파일 권한이
700 으로 따라붙어 앱·스크립트가 열리지 않는다. 이 스크립트가 정상값으로 되돌린다.

### 인계 패키지에 넣는 방법

그룹A 안내문이 `bash 권한복구.sh` 로 되어 있으므로, **패키지에는 같은 이름으로 복사**한다.

```bash
cp scripts/handoff/restore_permissions.sh "<인계폴더>/권한복구.sh"
```

패키지 루트에 두면 인자 없이 실행할 때 자기 폴더를 대상으로 삼는다.
다른 폴더를 지정하려면 `bash 권한복구.sh <대상폴더>`.

### 대상 검증 (먼저 걸린다)

재귀 `chmod` 는 잘못된 대상에 걸리면 사용자 파일 권한을 광범위하게 파괴하거나 노출한다
(644 는 다른 사용자에게 읽기를 허용한다). 그래서 대상을 좁게 강제한다. 하나라도 어긋나면
**아무것도 바꾸지 않고 거부**한다.

- 심볼릭 링크가 아닐 것
- `/` 가 아닐 것 · 최상위 디렉터리(`/Users` 등)가 아닐 것
- `$HOME` 자체가 아닐 것
- git 저장소 루트(`.git` 보유)가 아닐 것
- **인계 패키지 표식이 대상 폴더 바로 아래에 있을 것** — `<대상>/Butler.app/Contents/MacOS`
  디렉터리, 또는 `<대상>/HANDOFF_MANIFEST.json`

  ★표식은 **하위 트리를 뒤져서 찾지 않는다.** 재귀 검색을 하면 인계 폴더의 한 칸 위를
  대상으로 넣어도 아래쪽 `Butler.app` 때문에 통과해 버리고, 그 위 폴더 전체가 `chmod` 된다
  (옆에 있던 개인 자료가 `0644` 로 열린다).

  그래서 **앱이 하위 폴더에 있는 패키지**(예: `01_앱/Butler.app`)는 패키지 최상위에
  `HANDOFF_MANIFEST.json` 을 두어야 한다. 패키지를 만들 때 함께 넣는다.

  ```bash
  cp scripts/handoff/restore_permissions.sh "<인계폴더>/권한복구.sh"
  printf '{"package":"butler-handoff","created":"%s"}\n' "$(date -u +%FT%TZ)" \
    > "<인계폴더>/HANDOFF_MANIFEST.json"
  ```

### 판정 규칙

| 대상 | 권한 |
|---|---|
| 디렉터리 | 755 |
| 문서·데이터(기본값) | 644 |
| `.sh` `.py` `.command` `.pl` `.rb` `.bash` `.zsh` | 755 |
| `*/Contents/MacOS/*` `*/bin/*` `*/sbin/*` `*/libexec/*` `*/binaries/*` | 755 |
| 내용이 Mach-O·universal(fat, 32/64비트)·ELF·shebang 인 파일(확장자 없거나 `.dylib` `.so` `.bundle` `.node` `.bin` `.out`) | 755 |

마지막 규칙이 **확장자 없는 실행 파일**(`Butler.app/Contents/MacOS/butler-desktop` 등)을 살린다.
2026-07-17 그룹A 지적의 원인이 이 규칙의 부재였다.

실행이 끝나면 `*/Contents/MacOS/*` 가 전부 실행 가능한지 자기 점검하고, 하나라도 아니면
성공으로 끝내지 않고 실패로 알린다.

회귀 시험: `tests/test_handoff_restore_permissions.py`
