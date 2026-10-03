# CI/CD agent runner. One run = check changes -> run tests -> ask Claude to commit+push -> verify -> record state.
# Fixed flow lives in this script (code). Claude (claude -p, logged in with Pro) only does: write commit message, commit, push.
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads UTF-8 without BOM.

param(
    [string]$RepoPath   = $PSScriptRoot,   # the whole ResearchAI-AGENT folder is the repo
    [string]$Branch     = 'main',      # user approved direct pushes to main
    [string]$TestCmd    = '',          # e.g. 'npm test' or 'python -m pytest'; empty = skip tests
    [int]$MaxTurns      = 12,
    [int]$LockMaxMinutes = 60,
    [bool]$DeployCheck  = $true,       # wait for the GitHub Pages build after pushing
    [int]$DeployWaitMinutes = 8
)

$ErrorActionPreference = 'Stop'
$AgentDir  = $PSScriptRoot
$LogDir    = Join-Path $AgentDir 'logs'
$StateFile = Join-Path $AgentDir 'state.json'
$LockFile  = Join-Path $LogDir 'run.lock'
New-Item -ItemType Directory -Force $LogDir | Out-Null

$RunId   = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "run-$RunId.log"
function Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Host $line
}

function Save-State($result, $extra) {
    $state = [ordered]@{
        last_run    = (Get-Date).ToString('s')
        run_id      = $RunId
        last_result = $result
    }
    foreach ($k in $extra.Keys) { $state[$k] = $extra[$k] }
    $state | ConvertTo-Json | Set-Content -Path $StateFile -Encoding utf8
}

# Wait for the GitHub Pages build of $sha, then check the site answers.
# Uses the public GitHub API (no token needed for public repos, limit 60 requests/hour).
function Wait-PagesDeploy([string]$sha) {
    $remoteUrl = (git remote get-url origin).Trim()
    if ($remoteUrl -notmatch 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/]+?)(\.git)?$') {
        return @{ status = 'skipped'; url = ''; detail = "origin is not a github.com url" }
    }
    $owner = $Matches['owner']; $repo = $Matches['repo']
    $siteUrl = "https://$($owner.ToLower()).github.io/$repo/"
    $api = "https://api.github.com/repos/$owner/$repo/actions/runs?head_sha=$sha&per_page=20"
    $headers = @{ 'User-Agent' = 'cicd-agent' }
    $deadline = (Get-Date).AddMinutes($DeployWaitMinutes)
    $detail = 'no Pages build found for this commit (is GitHub Pages enabled?)'
    while ((Get-Date) -lt $deadline) {
        try {
            $runs = (Invoke-RestMethod $api -Headers $headers).workflow_runs |
                Where-Object { $_.name -eq 'pages build and deployment' } | Select-Object -First 1
            if ($runs) {
                if ($runs.status -eq 'completed') {
                    if ($runs.conclusion -ne 'success') {
                        return @{ status = 'failed'; url = $siteUrl; detail = "Pages build concluded: $($runs.conclusion) ($($runs.html_url))" }
                    }
                    try {
                        $code = (Invoke-WebRequest $siteUrl -UseBasicParsing).StatusCode
                        return @{ status = 'ok'; url = $siteUrl; detail = "Pages build success, site HTTP $code" }
                    } catch {
                        return @{ status = 'failed'; url = $siteUrl; detail = "Pages build success but site check failed: $($_.Exception.Message)" }
                    }
                }
                $detail = "Pages build still $($runs.status)"
            }
        } catch { $detail = "API error: $($_.Exception.Message)" }
        Start-Sleep -Seconds 15
    }
    return @{ status = 'timeout'; url = $siteUrl; detail = $detail }
}

# ---- lock: never two runs at once ----
if (Test-Path $LockFile) {
    $age = (Get-Date) - (Get-Item $LockFile).LastWriteTime
    if ($age.TotalMinutes -lt $LockMaxMinutes) {
        Log "SKIP: another run holds the lock ($([int]$age.TotalMinutes) min old)"
        exit 0
    }
    Log "WARN: stale lock ($([int]$age.TotalMinutes) min old), taking over"
}
Set-Content -Path $LockFile -Value $RunId

try {
    Set-Location $RepoPath
    if (-not (Test-Path '.git')) { throw "Not a git repo: $RepoPath" }
    git remote get-url origin *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Repo has no remote named origin' }

    # ---- step 1: any changes? (no changes = no LLM call = no quota used) ----
    $changes = git status --porcelain
    if (-not $changes) {
        Log 'No changes. Nothing to do.'
        Save-State 'no_changes' @{}
        exit 0
    }
    Log ("Changes detected:`n" + ($changes -join "`n"))

    # ---- step 2: tests (code decides, not the LLM) ----
    if ($TestCmd) {
        Log "Running tests: $TestCmd"
        $testOut = cmd /c $TestCmd 2>&1
        if ($LASTEXITCODE -ne 0) {
            Log "Tests FAILED. Not committing.`n$($testOut -join "`n")"
            Save-State 'tests_failed' @{ note = 'tests failed, no commit' }
            exit 1
        }
        Log 'Tests passed.'
    }

    # ---- step 3: work on the agent branch ----
    git fetch -q origin *> $null
    git rev-parse --verify --quiet $Branch *> $null
    if ($LASTEXITCODE -eq 0) {
        git checkout -q $Branch
    } else {
        git rev-parse --verify --quiet "origin/$Branch" *> $null
        if ($LASTEXITCODE -eq 0) { git checkout -q -b $Branch --track "origin/$Branch" }
        else { git checkout -q -b $Branch }
    }
    if ($LASTEXITCODE -ne 0) { throw "Cannot switch to branch $Branch" }
    $before = (git rev-parse HEAD).Trim()

    # ---- step 4: Claude writes the message, commits, pushes (limited tools) ----
    $prompt = "Follow the CI/CD rules in CLAUDE.md. Review the uncommitted changes in this repo, commit them with a Conventional Commits message, and push to origin $Branch."
    Log "Calling claude -p (max turns $MaxTurns)"
    $raw = claude -p $prompt `
        --allowedTools 'Read' 'Bash(git status *)' 'Bash(git diff *)' 'Bash(git add *)' 'Bash(git commit *)' "Bash(git push origin $Branch)" 'Bash(git log *)' `
        --max-turns $MaxTurns `
        --output-format json 2>&1
    $claudeExit = $LASTEXITCODE
    Add-Content -Path $LogFile -Value ("--- claude raw output ---`n" + ($raw -join "`n")) -Encoding utf8
    if ($claudeExit -ne 0) { throw "claude exited with code $claudeExit" }

    $info = $null
    try { $info = ($raw -join "`n") | ConvertFrom-Json } catch { Log 'WARN: could not parse claude JSON output' }

    # ---- step 5: verify the outcome ourselves, do not trust the model's words ----
    $after  = (git rev-parse HEAD).Trim()
    $remote = ((git ls-remote origin "refs/heads/$Branch") -split '\s+')[0]
    $left   = git status --porcelain
    $pushed = ($after -eq $remote)

    $extra = @{
        branch = $Branch; commit_before = $before; commit_after = $after
        pushed = $pushed
    }
    if ($info) {
        $extra.num_turns = $info.num_turns
        $extra.cost_usd  = $info.total_cost_usd
        $extra.summary   = $info.result
    }

    if ($after -ne $before -and $pushed -and -not $left) {
        Log "OK: committed $after and pushed to origin/$Branch"

        # ---- step 6: deploy check (GitHub Pages builds automatically on every push) ----
        if ($DeployCheck) {
            $dep = Wait-PagesDeploy $after
            $extra.deploy_status = $dep.status
            $extra.deploy_url    = $dep.url
            $extra.deploy_detail = $dep.detail
            Log "Deploy: $($dep.status) - $($dep.detail)"
            if ($dep.status -ne 'ok') {
                Save-State 'deploy_failed' $extra
                exit 1
            }
        }
        Save-State 'ok' $extra
        exit 0
    }
    Log "FAIL: committed=$($after -ne $before) pushed=$pushed leftover_changes=$([bool]$left)"
    Save-State 'failed_verification' $extra
    exit 1
}
catch {
    Log "ERROR: $($_.Exception.Message)"
    Save-State 'error' @{ error = $_.Exception.Message }
    exit 1
}
finally {
    Remove-Item $LockFile -ErrorAction SilentlyContinue
}
