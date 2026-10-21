param([string]$BatchId = 'int_01_pilot_guarded_v1')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $projectRoot "outputs\v2\batches\$BatchId\manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$pending = @($manifest.samples | Where-Object { -not $_.selected -and $_.attempts.Count -gt 0 })
$activeAttempt = if ($pending.Count) { $pending[-1].attempts[-1].path } else { $null }
if (-not $activeAttempt -and $manifest.status -eq 'running' -and @($manifest.baseline_repeats).Count) {
    $activeAttempt = $manifest.baseline_repeats[-1]
}
$episodes = @{}
$gpu = $null
if ($activeAttempt) {
    foreach ($branch in @('R','CF')) {
        $episodePath = Join-Path $activeAttempt "$branch\episode.json"
        $episodes[$branch] = if (Test-Path -LiteralPath $episodePath) {
            (Get-Content -LiteralPath $episodePath -Raw | ConvertFrom-Json).status
        } else { 'not_started' }
    }
    $latest = Get-ChildItem -LiteralPath $activeAttempt -Filter '*.telemetry.jsonl' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest -and $latest.Length) {
        try { $gpu = Get-Content -LiteralPath $latest.FullName -Tail 1 | ConvertFrom-Json } catch { $gpu = $null }
    }
}
[pscustomobject]@{
    batch_id = $manifest.batch_id
    status = $manifest.status
    accepted_pairs = @($manifest.samples | Where-Object { $_.selected }).Count
    planned_pairs = $manifest.samples.Count
    baseline_repeat_attempts = @($manifest.baseline_repeats).Count
    active_attempt = $activeAttempt
    episodes = $episodes
    latest_gpu = $gpu
} | ConvertTo-Json -Depth 6 -Compress
