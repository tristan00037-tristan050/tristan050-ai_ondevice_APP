param(
  [string]$Root = ".",
  [string]$DeviceId = "windows-vm-lab"
)

$ErrorActionPreference = "Stop"
Set-Location $Root

python tools/collect_real_telemetry.py . --device-id $DeviceId --evidence-class vm_lab
python tools/windows_real_telemetry_gate.py . --expected-evidence-class vm_lab
python tools/evidence_taxonomy_gate.py .
python tools/all_platform_telemetry_gate.py . --require-platforms windows --strict --expected-evidence-class vm_lab
python tools/claim_guard.py .

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force
python tools/clean_package_gate.py .
python tools/sha256_manifest.py .

Write-Output "WINDOWS_VM_LAB_VALIDATION_OK"
