# never-sleep.ps1
# ป้องกันไม่ให้ Windows เข้าสู่โหมด Sleep / Hibernate
# วิธีใช้: คลิกขวา > Run with PowerShell หรือรันผ่าน never-sleep.bat

# --- Windows API: SetThreadExecutionState ---
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class SleepPreventer {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);

    public const uint ES_CONTINUOUS        = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED   = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED  = 0x00000002;
}
"@

# --- Configuration ---
$pingIntervalMinutes = if ($env:PING_INTERVAL_MINUTES) { [int]$env:PING_INTERVAL_MINUTES } else { 5 }
$pingUrls = @()
if ($env:PING_URLS) {
    $pingUrls = $env:PING_URLS -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }
}

# --- Start ---
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  never-sleep is running" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Interval: every $pingIntervalMinutes minute(s)"
if ($pingUrls.Count -gt 0) {
    Write-Host "Ping targets ($($pingUrls.Count)):"
    $pingUrls | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "Ping targets: (none)"
}
Write-Host ""
Write-Host "DO NOT close this window. Minimize it instead." -ForegroundColor Yellow
Write-Host ""

# --- Main Loop ---
while ($true) {
    $now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    # Tell Windows: don't sleep, keep system & display on
    $result = [SleepPreventer]::SetThreadExecutionState(
        [SleepPreventer]::ES_CONTINUOUS -bor
        [SleepPreventer]::ES_SYSTEM_REQUIRED -bor
        [SleepPreventer]::ES_DISPLAY_REQUIRED
    )

    if ($result -ne 0) {
        Write-Host "[$now] OK - Windows sleep prevented" -ForegroundColor Green
    } else {
        Write-Host "[$now] WARNING - SetThreadExecutionState failed" -ForegroundColor Red
    }

    # Ping target URLs
    foreach ($url in $pingUrls) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 15 -ErrorAction Stop
            Write-Host "[$now] PING $url -> $($response.StatusCode)" -ForegroundColor Gray
        } catch {
            Write-Host "[$now] PING $url -> ERROR: $($_.Exception.Message)" -ForegroundColor DarkYellow
        }
    }

    Start-Sleep -Seconds ($pingIntervalMinutes * 60)
}
