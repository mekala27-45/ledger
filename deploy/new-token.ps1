# Make the API's write token on this machine: 32 random bytes, written to deploy\write-token.txt
# (ignored by git) and put on the clipboard, so it can be pasted into the host's environment
# variable LEDGER_API_TOKEN. The token is never printed.
#
#   powershell -ExecutionPolicy Bypass -File "C:\Project FullTime\ledger\deploy\new-token.ps1"

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$path = Join-Path $repo "deploy\write-token.txt"
if (Test-Path $path) {
    Write-Host "deploy\write-token.txt already exists; delete it first to make a new token"
    exit 1
}
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = ([Convert]::ToBase64String($bytes)).TrimEnd("=").Replace("+", "-").Replace("/", "_")
Set-Content -Path $path -Value $token -NoNewline
Set-Clipboard -Value $token
Write-Host "a new token is in deploy\write-token.txt and on the clipboard; paste it as LEDGER_API_TOKEN"
