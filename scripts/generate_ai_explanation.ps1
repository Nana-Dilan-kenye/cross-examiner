$ErrorActionPreference = "Stop"

$ns = Join-Path $env:LOCALAPPDATA "Nightshift\cli\ns.cmd"
$projectRoot = Split-Path -Parent $PSScriptRoot
$resultsPath = Join-Path $projectRoot "reports\cameroon_mcv1_results.json"
$outputPath = Join-Path $projectRoot "reports\cameroon_mcv1_ai_explanation.md"

if (-not (Test-Path $ns)) {
    throw "Nightshift CLI not found: $ns"
}
if (-not (Test-Path $resultsPath)) {
    throw "Results JSON not found. Run the deterministic demo first: $resultsPath"
}

$results = Get-Content -Raw -Path $resultsPath | ConvertFrom-Json

$evidence = [ordered]@{
    source        = $results.source
    records_loaded = $results.records_loaded
    threshold_percentage_points = $results.threshold_percentage_points
    findings      = $results.findings
    decisions     = $results.decisions
} | ConvertTo-Json -Depth 12

$prompt = @"
Write a Markdown report titled "AI Explanation of Cameroon MCV1 Coverage Findings".

Use exactly these sections:
1. Summary
2. Findings
3. What REVIEW Means
4. Follow-up Checks
5. Limitations

Use only these facts:
- 2020: administrative coverage 74%, WUENIC estimate 63%, gap 11 percentage points.
- 2023: administrative coverage 82%, WUENIC estimate 71%, gap 11 percentage points.
- Both deterministic decisions are REVIEW.
- The gaps alone do not show which figure is correct.
- Follow-up checks: definitions, target populations and denominators, reporting quality, and estimation methodology.
- Source URLs are references; this analysis has not independently verified their contents.

Do not invent facts, causes, citations, or statistics.
Do not change or reinterpret the deterministic decisions.
Keep the report under 300 words.
Return only the Markdown report.

DATA:
$evidence
"@

Write-Host "Submitting findings to Nightshift/Nemotron..."

$promptPath = Join-Path $env:TEMP "cross-examiner-nemotron-prompt.txt"
Set-Content -LiteralPath $promptPath -Value $prompt -Encoding UTF8

$generationLines = @(
    & $ns generate --file $promptPath --n 1 --privacy cloud-ok --budget low --wait --json
)
if ($LASTEXITCODE -ne 0) {
    throw "Nightshift generation failed."
}

$jobId = $null
foreach ($line in $generationLines) {
    try {
        $event = ([string]$line) | ConvertFrom-Json
        if ($event.command -eq "generate" -and $event.data.job_id) {
            $jobId = [string]$event.data.job_id
        }
    } catch {
        # Ignore non-JSON progress output.
    }
}

if (-not $jobId) {
    throw "Generation finished without a job ID. Deterministic results remain unchanged."
}

Write-Host "Generation job: $jobId"
$attemptLines = @(& $ns context attempt $jobId 1 --raw --json 2>&1)

$attemptEnvelope = $null
foreach ($line in $attemptLines) {
    try {
        $candidate = ([string]$line) | ConvertFrom-Json
        if ($candidate.command -eq "context attempt") {
            $attemptEnvelope = $candidate
        }
    } catch {
        # Ignore non-JSON output.
    }
}

if (-not $attemptEnvelope) {
    throw "Nightshift returned no readable attempt envelope."
}

$generatedText = [string]$attemptEnvelope.data.raw
if ([string]::IsNullOrWhiteSpace($generatedText)) {
    $generatedText = [string]$attemptEnvelope.data.attempt.text
}
if ([string]::IsNullOrWhiteSpace($generatedText)) {
    throw "The model returned empty text. Deterministic results remain unchanged."
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $outputPath,
    $generatedText.Trim() + [Environment]::NewLine,
    $utf8NoBom
)

Write-Host "AI explanation saved to: $outputPath"
Write-Host "Job ID: $jobId"
Write-Host "Model: $($attemptEnvelope.data.attempt.model.resolved)"
