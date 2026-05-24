# IP3 Windows Validation Levels

## ci_lab

GitHub Actions `windows-latest`에서 생성된 Windows telemetry입니다. Windows OS runner에서 수집된 runtime telemetry로 인정하지만, 물리 Windows 노트북 또는 운영 환경 증빙은 아닙니다.

성공 label:

```text
WINDOWS_REAL_TELEMETRY_OK_CI_LAB
ALL_PLATFORM_TELEMETRY_OK_CI_LAB
APPROVED_FOR_AI_ONDEVICE13_HANDOFF_CI_LAB
```

## vm_lab

MacBook 위 Windows VM 또는 클라우드 VM에서 생성된 telemetry입니다. Windows OS telemetry로 인정하지만 physical_lab은 아닙니다.

성공 label:

```text
WINDOWS_REAL_TELEMETRY_OK_VM_LAB
ALL_PLATFORM_TELEMETRY_OK_VM_LAB
APPROVED_FOR_AI_ONDEVICE13_HANDOFF_VM_LAB
```

## physical_lab

별도 Windows 노트북 또는 데스크톱에서 생성된 telemetry입니다. 본 패키지는 Windows notebook 경로를 더 엄격하게 보기 위해 physical runner에서 battery present gate를 기본 요구합니다.

성공 label:

```text
WINDOWS_REAL_TELEMETRY_OK_PHYSICAL_LAB
ALL_PLATFORM_TELEMETRY_OK_PHYSICAL_LAB
APPROVED_FOR_AI_ONDEVICE13_HANDOFF_PHYSICAL_WINDOWS_LAB
```

## production

실제 Butler 앱, 정책 서버, 모델 bridge, 운영 배포 환경에서 생성된 증빙입니다. v1.3 telemetry lab pack에서는 production claim이 비활성화되어 있습니다.
