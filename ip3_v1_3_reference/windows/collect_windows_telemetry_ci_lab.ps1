param(
  [string]$Root = ".",
  [string]$DeviceId = "github-actions-windows-latest"
)

$ErrorActionPreference = "Stop"
Set-Location $Root

if ($env:GITHUB_ACTIONS -ne "true") {
  throw "CI_LAB runner requires GitHub Actions. Use vm_lab or physical_lab runner outside CI."
}

python tools/collect_real_telemetry.py . --device-id $DeviceId --evidence-class ci_lab
python tools/windows_real_telemetry_gate.py . --expected-evidence-class ci_lab
python tools/evidence_taxonomy_gate.py .
python tools/all_platform_telemetry_gate.py . --require-platforms windows --strict --expected-evidence-class ci_lab
python tools/claim_guard.py .

Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" | Remove-Item -Force
python tools/clean_package_gate.py .

Write-Output "WINDOWS_CI_LAB_VALIDATION_OK"
