#Requires -Version 5.1
<#
.SYNOPSIS
  Pulls the latest work from the upstream repo (where Claude Code pushes)
  into this fork and pushes it to origin, which is what makes the
  self-hosted runner registered on the fork actually run the pipeline.

  Replaces typing these by hand every time:
    git fetch upstream
    git merge upstream/<branch>
    git push origin <branch>

.DESCRIPTION
  After pushing, the Game Factory Pipeline needs to actually start. A push
  only auto-triggers it when GameSpecs/** changed (see game-factory.yml),
  so when the incoming commits only touched C#/docs this script triggers
  the workflow explicitly via `gh` instead - either way exactly one run
  starts, and never a pointless one when nothing changed.

.PARAMETER Silent
  No popups: write to Logs/auto-sync.log and exit with a status code.
  This is what the scheduled task (register-auto-sync.ps1) uses.

.PARAMETER NoTrigger
  Sync only - never start a pipeline run.

.PARAMETER SkipErrorReport
  Don't collect/commit Unity's compile errors (scripts/dev/collect-errors.ps1).

.NOTES
  Requires the GitHub CLI (`gh`) installed and logged in once beforehand:
    winget install --id GitHub.cli
    gh auth login
  Aborts (without touching anything) if the working tree has uncommitted
  changes, so it can never throw away local work.
#>

[CmdletBinding()]
param(
    [string]$RepoPath = "C:\Dory_tycoon",
    [string]$Branch = "claude/delete-current-content-mgn4xm",
    [string]$UpstreamRemote = "upstream",
    [string]$OriginRemote = "origin",
    [string]$GameId = "game01",
    [string]$Workflow = "game-factory.yml",
    [string]$RepoSlug = "gojo3105/Dory_tycoon",
    [switch]$Silent,
    [switch]$NoTrigger,
    [switch]$SkipErrorReport
)

$ErrorActionPreference = "Stop"

$script:LogPath = Join-Path $RepoPath "Logs\auto-sync.log"

function Write-Log([string]$message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Write-Host $line

    try {
        $logDir = Split-Path $script:LogPath -Parent
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        Add-Content -Path $script:LogPath -Value $line -Encoding UTF8
    }
    catch {
        # Logging must never be the reason a sync fails.
    }
}

function Show-Result([string]$message, [string]$icon) {
    Write-Log $message
    if ($Silent) { return }

    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message, "Game Factory Sync", "OK", $icon) | Out-Null
}

# git writes progress to stderr, so this deliberately captures both streams
# and judges success by the exit code only. Network-ish operations get the
# 2s/4s/8s/16s retry ladder the project uses everywhere else.
function Invoke-Git {
    param([Parameter(Mandatory = $true)][string[]]$Arguments, [int]$Retries = 0)

    $ErrorActionPreference = "Continue"
    $attempt = 0

    while ($true) {
        $output = & git -C $RepoPath @Arguments 2>&1
        if ($LASTEXITCODE -eq 0) { return ($output | Out-String).Trim() }

        if ($attempt -ge $Retries) {
            throw "git $($Arguments -join ' ') failed (exit $LASTEXITCODE):`n$(($output | Out-String).Trim())"
        }

        $delay = [Math]::Pow(2, $attempt + 1)
        Write-Log "git $($Arguments -join ' ') failed; retrying in ${delay}s"
        Start-Sleep -Seconds $delay
        $attempt++
    }
}

try {
    if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
        throw "'$RepoPath' is not a git repository. Pass -RepoPath <path to the clone>."
    }

    $remotes = (Invoke-Git @("remote")) -split "\r?\n"
    foreach ($required in @($UpstreamRemote, $OriginRemote)) {
        if ($remotes -notcontains $required) {
            throw "Remote '$required' is not configured in $RepoPath (found: $($remotes -join ', '))."
        }
    }

    # Collect Unity's errors into a committed report BEFORE the dirty check
    # below - writing the report is itself a tracked-file change, so it has
    # to be committed here rather than left to trip that check. This is the
    # whole point of the loop: Claude Code has no Unity and no access to this
    # PC, so the errors have to reach it through the repo.
    if (-not $SkipErrorReport) {
        try {
            $collectScript = Join-Path (Split-Path $PSScriptRoot -Parent) "dev\collect-errors.ps1"
            & $collectScript -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote -Commit -NoPush
        }
        catch {
            # Never let error reporting be the reason a sync fails.
            Write-Log "Error report step failed (continuing with the sync): $_"
        }
    }

    # Refuse to merge over uncommitted edits to tracked files rather than
    # risk losing them. Untracked files are deliberately tolerated: running
    # the generator locally leaves Assets/GeneratedGames and friends lying
    # around, and treating that as "dirty" would block every scheduled sync
    # from then on. A merge that would actually overwrite an untracked file
    # fails on its own, and the handler below restores the original state.
    $dirty = Invoke-Git @("status", "--porcelain", "--untracked-files=no")
    if ($dirty) {
        throw "추적 중인 파일에 커밋되지 않은 변경이 있어 중단했습니다. 먼저 커밋하거나 stash 해주세요:`n`n$dirty"
    }

    $currentBranch = Invoke-Git @("rev-parse", "--abbrev-ref", "HEAD")
    if ($currentBranch -ne $Branch) {
        Write-Log "Switching from '$currentBranch' to '$Branch'"
        Invoke-Git @("checkout", $Branch) | Out-Null
    }

    Write-Log "Fetching $UpstreamRemote and $OriginRemote"
    Invoke-Git @("fetch", $UpstreamRemote) -Retries 4 | Out-Null
    Invoke-Git @("fetch", $OriginRemote) -Retries 4 | Out-Null

    # What the fork already has is the baseline that decides whether a
    # pipeline run is warranted - not local HEAD. Local commits that were
    # never pushed (say, assets added by hand) are new to CI too.
    $originRef = "$OriginRemote/$Branch"
    $forkHead = $null
    try { $forkHead = Invoke-Git @("rev-parse", "--verify", "--quiet", $originRef) }
    catch { Write-Log "'$originRef' does not exist yet; treating everything as new." }

    Write-Log "Merging $UpstreamRemote/$Branch"
    try {
        Invoke-Git @("merge", "--no-edit", "$UpstreamRemote/$Branch") | Out-Null
    }
    catch {
        $mergeError = $_

        # Leave the repo exactly as it was so a human can resolve it calmly.
        # A failed abort must not mask why the merge failed in the first place.
        try { Invoke-Git @("merge", "--abort") | Out-Null } catch { Write-Log "merge --abort also failed: $_" }

        throw "병합에 실패해서 중단했습니다 (저장소를 원래 상태로 되돌리려고 시도했습니다). 직접 확인이 필요합니다:`n`n$mergeError"
    }

    $after = Invoke-Git @("rev-parse", "HEAD")

    Write-Log "Pushing to $originRef"
    Write-Log (Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4)

    if ($forkHead -eq $after) {
        Show-Result "이미 최신 상태입니다. 포크에 새로 올라간 변경이 없어서 파이프라인도 실행하지 않았습니다." "Information"
        exit 0
    }

    if ($forkHead) {
        $commitCount = Invoke-Git @("rev-list", "--count", "$forkHead..$after")
        $summary = "새 커밋 $commitCount개를 포크에 push했습니다."

        $changedPaths = (Invoke-Git @("diff", "--name-only", $forkHead, $after)) -split "\r?\n" | Where-Object { $_ }
        $specChanges = $changedPaths | Where-Object { $_ -like "GameSpecs/*" }

        # An error-report-only push must not start a build: the report is a
        # diagnostic written by this very script, so triggering on it would
        # queue a pointless pipeline run on every scheduled sync that picks
        # up new Unity errors.
        $buildRelevant = $changedPaths | Where-Object { $_ -notlike "Reports/*" }
        if (-not $buildRelevant) {
            Show-Result "$summary`n`n오류 리포트만 갱신되어 파이프라인은 실행하지 않았습니다." "Information"
            exit 0
        }
    }
    else {
        $summary = "브랜치를 포크에 처음 push했습니다."
        $specChanges = $null
    }

    if ($NoTrigger) {
        Show-Result "$summary`n`n(-NoTrigger 지정으로 파이프라인은 실행하지 않았습니다.)" "Information"
        exit 0
    }

    # A push already starts game-factory.yml when GameSpecs/** changed;
    # triggering again here would just queue a duplicate run.
    if ($specChanges) {
        Show-Result "$summary`n`nGameSpecs 변경이 포함되어 파이프라인이 자동으로 시작됩니다.`n`n진행 상황: https://github.com/$RepoSlug/actions" "Information"
        exit 0
    }

    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Show-Result "$summary`n`n다만 GitHub CLI(gh)가 없어서 파이프라인을 자동 실행하지 못했습니다. 아래로 설치 후 'gh auth login' 해주세요:`n`nwinget install --id GitHub.cli" "Warning"
        exit 1
    }

    Write-Log "Triggering $Workflow for '$GameId'"
    $ErrorActionPreference = "Continue"
    $ghOutput = & gh workflow run $Workflow --repo $RepoSlug --ref $Branch -f "game_id=$GameId" 2>&1
    $ghExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"

    if ($ghExit -ne 0) {
        Show-Result "$summary`n`n하지만 파이프라인 실행 요청이 실패했습니다 (exit $ghExit):`n$(($ghOutput | Out-String).Trim())`n`n'gh auth login' 상태를 확인해주세요." "Error"
        exit 1
    }

    Show-Result "$summary`n`n'$GameId' 파이프라인 실행을 요청했습니다.`n`n진행 상황: https://github.com/$RepoSlug/actions" "Information"
    exit 0
}
catch {
    Show-Result "동기화에 실패했습니다:`n`n$_" "Error"
    exit 1
}
