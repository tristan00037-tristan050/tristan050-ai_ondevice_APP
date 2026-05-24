param(
  [string]$Root = ".",
  [string]$DeviceId = "windows-physical-lab"
)

$ErrorActionPreference = "Stop"
Set-Location $Root

if ($env:GITHUB_ACTIONS -eq "true") {
  throw "PHYSICAL_LAB must not run on GitHub Actions."
}

python tools/collect_real_telemetry.py . --device-id $DeviceId --evidence-class physical_lab --physical-device-assertion
python tools/windows_real_telemetry_gate.py . --expected-evidence-class physical_lab --require-battery-present
python tools/evidence_taxonomy_gate.py .
python tools/all_platform_telemetry_gate.py . --require-platforms windows --strict --expected-evidence-class physical_lab --require-battery-present
python tools/claim_guard.py .

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force
python tools/clean_package_gate.py .
python tools/sha256_manifest.py .

Write-Output "WINDOWS_PHYSICAL_LAB_VALIDATION_OK"
