$python = "C:\Program Files\Blender Foundation\Blender 4.5\4.5\python\bin\python.exe"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $projectRoot
$env:PYTHONPATH = (Join-Path $projectRoot ".packages")

& $python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
