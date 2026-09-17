# 启动「吃什么？」服务：在新窗口里跑 run.py，并把 PID 记到 .csm.pid，
# 这样「停止.bat」不依赖 WMI 也能精确结束进程。
# 用法： powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_server.ps1 -Python "C:\path\python.exe"

param(
    [Parameter(Mandatory = $true)][string]$Python,
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Python)) {
    Write-Host "  [错误] 找不到 Python：$Python"
    exit 1
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$proc = Start-Process -FilePath $Python -ArgumentList "run.py" -WorkingDirectory $root -PassThru
$proc.Id | Set-Content -Path (Join-Path $root ".csm.pid") -Encoding ascii

Write-Host "  服务已在新窗口启动（PID $($proc.Id)，端口 $Port）"
Write-Host "  停止服务：双击 停止.bat，或直接关掉那个新窗口"
exit 0
