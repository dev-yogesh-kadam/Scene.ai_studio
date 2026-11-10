<#
.SYNOPSIS
  The whole gate in one command: types, lint, design tokens, unit tests, pytest, the test order check, the agent's
  evals (replay), the web build with its bundle budget, Playwright, the smoke test, and (with -Models) check_models.py.
  One summary table at the end. scripts/gate.sh is the same for bash.

.DESCRIPTION
  It refuses to run without SCENE_TEST_DATABASE_URL, or when it names the studio's own database `scene`: the tests
  empty every table they find. Two gates never share a test database: each takes a lock for its database (a folder in
  the temp folder, with its process id) and a second one on the same database stops at once. The URL is never printed;
  each step's output is kept in a log, with the URL and its password taken out.
  SCENE_TEST_PORT_BASE (default 8100) is passed on to the test studios: smoke uses base+81/+90/+99, Playwright
  base+181/+190/+199. A base whose ports land on the live studio's (8080, 8081, 8090), PostgreSQL's (5432), the
  render PC's (8188) or 3000 is refused.

.EXAMPLE
  . testenv.sh scene_test_me; $env:SCENE_TEST_PORT_BASE = 18900; .\scripts\gate.ps1
  .\scripts\gate.ps1 -Only pytest,evals
  .\scripts\gate.ps1 -Skip playwright,smoke -Coverage
  .\scripts\gate.ps1 -Models        # also scripts/check_models.py: it calls Claude for real
#>
param(
  [string[]]$Only = @(),
  [string[]]$Skip = @(),
  [switch]$Models,
  [switch]$Coverage,
  [switch]$StopOnFailure,
  [string]$LogDir = ""
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Steps = 'typecheck', 'lint', 'tokens', 'unit', 'pytest', 'order', 'evals', 'build', 'mobile', 'playwright', 'smoke', 'models'
foreach ($name in @($Only + $Skip)) {
  if ($Steps -notcontains $name) { Write-Error "No step '$name'. The steps: $($Steps -join ', ')"; exit 2 }
}

# ------------------------------------------------------------------ the test database: never the live one, one gate at a time
$Url = $env:SCENE_TEST_DATABASE_URL
if (-not $Url) {
  Write-Host 'The gate needs SCENE_TEST_DATABASE_URL: a test database it may empty, postgresql://scene_test:<password>@localhost:5432/scene_test_<name> (docs/database.md).' -ForegroundColor Red
  exit 2
}
try { $Parsed = [System.Uri]$Url } catch { Write-Host 'SCENE_TEST_DATABASE_URL is not a URL.' -ForegroundColor Red; exit 2 }
$Database = $Parsed.AbsolutePath.TrimStart('/').Split('?')[0]
if (-not $Database -or $Database -eq 'scene') {
  Write-Host "SCENE_TEST_DATABASE_URL names the studio's live database (or none). The gate empties every table: point it at a test database." -ForegroundColor Red
  exit 2
}
$PortBase = if ($env:SCENE_TEST_PORT_BASE) { [int]$env:SCENE_TEST_PORT_BASE } else { 8100 }
$Forbidden = 8080, 8081, 8090, 3000, 5432, 8188
$Used = 81, 90, 99, 181, 190, 199 | ForEach-Object { $PortBase + $_ }
$Clash = $Used | Where-Object { $Forbidden -contains $_ }
if ($Clash) { Write-Host "SCENE_TEST_PORT_BASE $PortBase puts a test studio on $($Clash -join ', '), which the live studio or its services use." -ForegroundColor Red; exit 2 }
$env:SCENE_TEST_PORT_BASE = "$PortBase"

$Key = ('{0}_{1}_{2}' -f $Parsed.Host, $Parsed.Port, $Database) -replace '[^A-Za-z0-9_.-]', '_'
$LockRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'scene-gate-locks'
New-Item -ItemType Directory -Force $LockRoot | Out-Null
$Lock = Join-Path $LockRoot "$Key.lock"
function Take-Lock {
  try { New-Item -ItemType Directory $Lock -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}
if (-not (Take-Lock)) {
  $holder = Get-Content (Join-Path $Lock 'pid') -ErrorAction SilentlyContinue
  $alive = $holder -and (Get-Process -Id ([int]$holder) -ErrorAction SilentlyContinue)
  if ($alive) {
    Write-Host "Another gate (process $holder) is using the database $Database. Wait for it, or give this one a database of its own." -ForegroundColor Red
    exit 3
  }
  Remove-Item -Recurse -Force $Lock -ErrorAction SilentlyContinue   # left by a gate that is gone
  if (-not (Take-Lock)) { Write-Host "Another gate took the database $Database just now." -ForegroundColor Red; exit 3 }
}
Set-Content -Path (Join-Path $Lock 'pid') -Value $PID -Encoding ascii

# ------------------------------------------------------------------ the steps
$Python = if (Test-Path (Join-Path $Root '.venv/Scripts/python.exe')) { Join-Path $Root '.venv/Scripts/python.exe' } else { Join-Path $Root '.venv/bin/python' }
if (-not $LogDir) { $LogDir = Join-Path ([System.IO.Path]::GetTempPath()) ("scene-gate/{0}/{1}" -f $Key, (Get-Date -Format 'yyyyMMdd-HHmmss')) }
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Secret = $Parsed.UserInfo.Split(':') | Select-Object -Skip 1
$pytestArgs = @('-m', 'pytest', '-q', '-p', 'no:cacheprovider')
if ($Coverage) { $pytestArgs += @('--cov=scene', '--cov=evals', '--cov-report=term', "--cov-report=json:$LogDir/coverage.json") }

$Plan = @(
  @{ Name = 'typecheck';  Dir = $Root;            Exe = 'npm';   Args = @('run', 'typecheck') }
  @{ Name = 'lint';       Dir = $Root;            Exe = 'npm';   Args = @('run', 'lint') }
  @{ Name = 'tokens';     Dir = $Root;            Exe = 'npm';   Args = @('run', 'tokens:check') }
  @{ Name = 'unit';       Dir = $Root;            Exe = 'npm';   Args = @('test') }
  @{ Name = 'pytest';     Dir = "$Root/backend";  Exe = $Python; Args = $pytestArgs }
  # one file's tests must never depend on another's having run first: these two, in the order that once failed
  @{ Name = 'order';      Dir = "$Root/backend";  Exe = $Python; Args = @('-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/test_claude_sdk.py', 'tests/test_claude.py') }
  @{ Name = 'evals';      Dir = "$Root/backend";  Exe = $Python; Args = @('-m', 'evals.run', '--json', "$LogDir/evals.json") }
  @{ Name = 'build';      Dir = $Root;            Exe = 'npm';   Args = @('run', 'build', '-w', 'apps/web') }
  @{ Name = 'mobile';     Dir = $Root;            Exe = 'npm';   Args = @('run', 'build', '-w', 'apps/mobile'); IfMissing = "$Root/apps/mobile/dist/index.html" }
  @{ Name = 'playwright'; Dir = "$Root/apps/web"; Exe = 'npx';   Args = @('playwright', 'test') }
  @{ Name = 'smoke';      Dir = $Root;            Exe = 'node';  Args = @('apps/web/tests/smoke/smoke.mjs', '--fake-comfy') }
  @{ Name = 'models';     Dir = $Root;            Exe = $Python; Args = @('scripts/check_models.py'); OptIn = $true }
)

function Scrub([string]$text) {
  $text = $text.Replace($Url, '<SCENE_TEST_DATABASE_URL>')
  if ($Secret) { $text = $text.Replace($Secret, '<password>') }
  return $text
}

function Last-Line([string]$text, [string]$pattern) {
  $line = $text -split "`n" | Where-Object { $_ -match $pattern } | Select-Object -Last 1
  if ($line) { return $line.Trim().Trim('=').Trim() }
  return ''
}

function Count-Of([string]$name, [string]$text) {
  switch ($name) {
    'pytest' { return Last-Line $text '\d+ (passed|failed)' }
    'order' { return Last-Line $text '\d+ (passed|failed)' }
    'evals' { return Last-Line $text '^evals: ' }
    'unit' {
      $parts = [regex]::Matches($text, 'Tests:?\s+(?:\d+ failed, )?(\d+) passed') | ForEach-Object { $_.Groups[1].Value }
      if ($parts) { return 'passed: ' + ($parts -join ' / ') }
    }
    'build' { return Last-Line $text 'First-load JavaScript' }
    'playwright' { return Last-Line $text '^\s*\d+ (passed|failed)' }
    'smoke' { return Last-Line $text '\d+ passed, \d+ failed' }
  }
  return ''
}

$Results = @()
$failed = $false
try {
  foreach ($step in $Plan) {
    $name = $step.Name
    $why = ''
    if ($Only.Count -and $Only -notcontains $name) { $why = 'not asked' }
    elseif ($Skip -contains $name) { $why = 'skipped (-Skip)' }
    elseif ($step.OptIn -and -not $Models) { $why = 'off (-Models: it calls Claude for real)' }
    elseif ($step.IfMissing -and (Test-Path $step.IfMissing)) { $why = 'already built' }
    elseif ($failed -and $StopOnFailure) { $why = 'not run (a step before failed)' }
    if ($why) { $Results += [pscustomobject]@{ Step = $name; Result = 'SKIP'; Seconds = ''; Says = $why }; continue }

    Write-Host ("==> {0}" -f $name) -ForegroundColor Cyan
    $log = Join-Path $LogDir "$name.log"
    $started = Get-Date
    Push-Location $step.Dir
    $ErrorActionPreference = 'Continue'   # a program writing to stderr is not a failure: its exit code says
    try {
      $output = & $step.Exe @($step.Args) 2>&1 | ForEach-Object { "$_" }
      $code = $LASTEXITCODE
    } catch {
      $output = @("$_"); $code = 1
    } finally {
      $ErrorActionPreference = 'Stop'
      Pop-Location
    }
    $text = Scrub (($output -join "`n"))
    Set-Content -Path $log -Value $text -Encoding utf8
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    $ok = ($code -eq 0)
    if (-not $ok) { $failed = $true; Write-Host (($text -split "`n" | Select-Object -Last 25) -join "`n") }
    $says = Count-Of $name $text
    if (-not $ok) { $says = ("exit {0}; {1} (log: {2})" -f $code, $says, $log) }
    $Results += [pscustomobject]@{ Step = $name; Result = $(if ($ok) { 'PASS' } else { 'FAIL' }); Seconds = $seconds; Says = $says }
  }
} finally {
  Remove-Item -Recurse -Force $Lock -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host ("Gate on database {0}, ports from {1}; logs in {2}" -f $Database, $PortBase, $LogDir)
$Results | Format-Table -AutoSize Step, Result, Seconds, Says | Out-String -Width 200 | Write-Host
if ($failed) { Write-Host 'The gate FAILED.' -ForegroundColor Red; exit 1 }
Write-Host 'The gate passed.' -ForegroundColor Green
exit 0
