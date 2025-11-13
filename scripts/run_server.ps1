$ErrorActionPreference = "Stop"

Set-Variable -Name EnvMap -Value @{
    "PYTHONUNBUFFERED"    = "1"
    "UVICORN_RELOAD"      = if ($env:UVICORN_RELOAD) { $env:UVICORN_RELOAD } else { "1" }
    "RECURDEFEND_TOOLSPECS" = if ($env:RECURDEFEND_TOOLSPECS) { $env:RECURDEFEND_TOOLSPECS } else { "data/raw/toolspecs.json" }
}

foreach ($pair in $EnvMap.GetEnumerator()) {
    $env[$pair.Key] = $pair.Value
}

# 가상환경 우선순위: .venv → venv
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
    . ".\venv\Scripts\Activate.ps1"
}

# 작업 폴더 준비
New-Item -ItemType Directory -Force -Path "data\processed" | Out-Null
New-Item -ItemType Directory -Force -Path "logs\runtime" | Out-Null
New-Item -ItemType Directory -Force -Path "logs\training" | Out-Null
New-Item -ItemType Directory -Force -Path "results\logs" | Out-Null

$port = if ($env:PORT) { $env:PORT } else { "8000" }

python -m uvicorn src.app:app --host "0.0.0.0" --port $port `
    $(if ($env:UVICORN_RELOAD -and $env:UVICORN_RELOAD -ne "0") { "--reload" })

