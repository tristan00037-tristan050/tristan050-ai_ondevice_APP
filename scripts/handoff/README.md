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

### 판정 규칙

| 대상 | 권한 |
|---|---|
| 디렉터리 | 755 |
| 문서·데이터(기본값) | 644 |
| `.sh` `.py` `.command` `.pl` `.rb` `.bash` `.zsh` | 755 |
| `*/Contents/MacOS/*` `*/bin/*` `*/sbin/*` `*/libexec/*` `*/binaries/*` | 755 |
| 내용이 Mach-O·ELF·shebang 인 파일(확장자 없거나 `.dylib` `.so` `.bundle` `.node` `.bin` `.out`) | 755 |

마지막 규칙이 **확장자 없는 실행 파일**(`Butler.app/Contents/MacOS/butler-desktop` 등)을 살린다.
2026-07-17 그룹A 지적의 원인이 이 규칙의 부재였다.

실행이 끝나면 `*/Contents/MacOS/*` 가 전부 실행 가능한지 자기 점검하고, 하나라도 아니면
성공으로 끝내지 않고 실패로 알린다.

회귀 시험: `tests/test_handoff_restore_permissions.py`
