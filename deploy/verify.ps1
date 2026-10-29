# Verify the live API from a separate client (a Windows machine, not the server, not the build
# sandbox): health, the desk's stream, a scorecard decision with its reasons, an alert the replay
# wrote, a case opened on it and read back, and the audit row for that case. Writes the transcript
# to deploy\verify-log.txt and the observation, with no secrets in it, to
# results\deploy\verification.json so the build can quote it.
#
# deploy\live-url.txt holds the base URL (for example https://ledger-harborline-api.vercel.app) and
# deploy\write-token.txt the token set as LEDGER_API_TOKEN on the host (deploy\new-token.ps1 makes one).
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\ledger\deploy\verify.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Start-Transcript -Path (Join-Path $repo "deploy\verify-log.txt") -Force | Out-Null
$base = (Get-Content (Join-Path $repo "deploy\live-url.txt") -Raw).Trim().TrimEnd("/")
$token = (Get-Content (Join-Path $repo "deploy\write-token.txt") -Raw).Trim()
$headers = @{ Authorization = "Bearer $token"; "x-ledger-actor" = "verification" }

Write-Host "client: $env:COMPUTERNAME ($([Environment]::OSVersion.VersionString)), PowerShell $($PSVersionTable.PSVersion)"
Write-Host "server: $base"

# The first request after idle wakes the instance.
$started = Get-Date
$health = Invoke-RestMethod -Uri "$base/v1/health" -TimeoutSec 90
$wakeSeconds = [Math]::Round(((Get-Date) - $started).TotalSeconds, 1)
Write-Host "health: status=$($health.status) fraud_model=$($health.fraud_model_loaded) scorecard=$($health.scorecard_loaded) desk_loaded=$($health.desk.loaded) desk_running=$($health.desk.running) (answered in $wakeSeconds s)"

# The desk's stream: a hello and then batches of transactions, as server sent events.
$request = [System.Net.HttpWebRequest]::Create("$base/v1/desk/stream?limit=4&batch_ms=500")
$request.Timeout = 90000
$request.ReadWriteTimeout = 60000
$response = $request.GetResponse()
$reader = New-Object System.IO.StreamReader($response.GetResponseStream())
$names = @()
$messages = @()
while ($messages.Count -lt 4) {
    $line = $reader.ReadLine()
    if ($null -eq $line) { break }
    if ($line.StartsWith("event: ")) { $names += $line.Substring(7) }
    elseif ($line.StartsWith("data: ")) { $messages += ($line.Substring(6) | ConvertFrom-Json) }
}
$reader.Close()
$response.Close()
$streamed = ($messages | Where-Object { $_.type -eq "transactions" } | ForEach-Object { $_.events.Count } | Measure-Object -Sum).Sum
$hello = $messages | Where-Object { $_.type -eq "hello" } | Select-Object -First 1
Write-Host "stream: events $($names -join ', '), $streamed transactions, desk clock $($hello.desk.clock)"

# A scorecard decision with the adverse action reasons.
$applicant = @{
    revolving_utilization = 0.95; bureau_score = 610; dti = 0.55; employment_months = 3
    oldest_trade_months = 14; purpose = "other"; inquiries_6m = 6; loan_amount = 30000
}
$scored = Invoke-RestMethod -Method Post -Uri "$base/v1/scorecard/score" -Headers $headers -ContentType "application/json" -TimeoutSec 60 -Body (@{ applicant = $applicant } | ConvertTo-Json)
Write-Host "scorecard: decision $($scored.decision), score $($scored.score), $($scored.reasons.Count) reasons"

# An alert the replay wrote, a case on it, and the case read back through its own request.
$alert = $null
for ($i = 0; $i -lt 30 -and $null -eq $alert; $i++) {
    $open = Invoke-RestMethod -Uri "$base/v1/desk/alerts?limit=5" -Headers $headers -TimeoutSec 60
    $alert = $open.alerts | Select-Object -First 1
    if ($null -eq $alert) { Start-Sleep -Seconds 2 }
}
if ($null -eq $alert) { throw "the replay wrote no alert in a minute" }
$case = (Invoke-RestMethod -Method Post -Uri "$base/v1/cases" -Headers $headers -ContentType "application/json" -TimeoutSec 60 -Body (@{ alert_id = $alert.id; note = "verification from a separate client" } | ConvertTo-Json)).case
$read = Invoke-RestMethod -Uri "$base/v1/cases/$($case.id)" -Headers $headers -TimeoutSec 60
$audit = Invoke-RestMethod -Uri "$base/v1/audit?limit=50" -Headers $headers -TimeoutSec 60
$opened = $audit.audit | Where-Object { $_.action -eq "open" -and $_.resource -eq "case" -and $_.resource_id -eq "$($case.id)" } | Select-Object -First 1
Write-Host "case $($case.id) on alert $($alert.id) (txn $($alert.txn_id), $($alert.decision), score $($alert.score)): read back $($read.case.id), alert status $($read.alert.status), audit row $($null -ne $opened)"

$statement = ($null -ne $hello.statements.demonstration) -and ($null -ne $scored.statements.not_a_decision)
$ok = ($health.status -eq "ok") -and $health.fraud_model_loaded -and $health.desk.loaded -and ($null -ne $hello) `
    -and ($scored.decision -eq "decline") -and ($scored.reasons.Count -ge 1) -and ($read.case.id -eq $case.id) `
    -and ($read.alert.status -eq "in_case") -and ($null -ne $opened) -and $statement
$result = [ordered]@{
    base_url = $base
    client = "$env:COMPUTERNAME, Windows, PowerShell $($PSVersionTable.PSVersion)"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    health_seconds = $wakeSeconds
    health = @{ status = $health.status; fraud_model_loaded = $health.fraud_model_loaded; scorecard_loaded = $health.scorecard_loaded; desk_loaded = $health.desk.loaded; desk_running = $health.desk.running }
    stream_events = $names
    stream_transactions = $streamed
    desk_clock = $hello.desk.clock
    scorecard_decision = $scored.decision
    scorecard_reasons = $scored.reasons.Count
    alert_id = $alert.id
    alert_decision = $alert.decision
    case_id = $case.id
    case_read_back = ($read.case.id -eq $case.id)
    alert_status_after = $read.alert.status
    audit_row_found = ($null -ne $opened)
    statements_present = $statement
    passed = $ok
}
New-Item -ItemType Directory -Force -Path (Join-Path $repo "results\deploy") | Out-Null
$result | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $repo "results\deploy\verification.json")
$result | ConvertTo-Json -Depth 5
Stop-Transcript | Out-Null
if (-not $ok) { throw "verification failed" }
Write-Host "verified from a separate client: health, the stream, a decision, a case and its audit row"
