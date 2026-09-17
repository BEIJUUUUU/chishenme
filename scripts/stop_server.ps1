# 停止「吃什么？」服务。三级保险，从最精确到最宽松：
#   1) .csm.pid 里记录的进程号（启动脚本写的，最可靠，不需要 WMI）
#   2) 正在监听该端口的 python 进程
#   3) 命令行里带 run.py 的 python 进程（WMI 不可用时自动跳过）
# 只结束 python 进程，绝不误伤占用同一端口的其他程序。
# 用法： powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop_server.ps1 -Port 8080

param(
    [int]$Port = 8080,
    [string]$Match = "run.py"
)

$ErrorActionPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".csm.pid"
$killed = New-Object System.Collections.Generic.List[int]

function Stop-PythonProcess {
    param([int]$ProcessId)

    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return }
    if ($proc.ProcessName -notlike "python*") {
        Write-Host ("  [跳过] PID " + $ProcessId + " 是 " + $proc.ProcessName + "，不是本程序")
        return
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    $killed.Add([int]$ProcessId)
}

# ---- 1) PID 文件 ----
if (Test-Path $pidFile) {
    $raw = (Get-Content -Path $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $recorded = 0
    if ([int]::TryParse($raw, [ref]$recorded) -and $recorded -gt 0) {
        Stop-PythonProcess -ProcessId $recorded
    }
    Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
}

# ---- 2) 监听端口 ----
if ($killed.Count -eq 0) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        if ($conn.OwningProcess) { Stop-PythonProcess -ProcessId ([int]$conn.OwningProcess) }
    }
}

# ---- 3) 命令行匹配 ----
if ($killed.Count -eq 0) {
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*$Match*" }
    foreach ($proc in $procs) {
        Stop-PythonProcess -ProcessId ([int]$proc.ProcessId)
    }
}

if ($killed.Count -gt 0) {
    $ids = ($killed | Sort-Object -Unique) -join ", "
    Write-Host ("  [完成] 已停止服务进程 PID: " + $ids)
} else {
    Write-Host "  [提示] 没有发现正在运行的服务进程（可能已经关了）"
}
