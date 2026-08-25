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
  so when the incoming commits only touched C#/docs this script needs
  another way to start it. It prefers `gh workflow run` when the GitHub
  CLI is installed and logged in, but that is optional, not required: when
  it is missing (or fails), this instead commits a one-line bump to
  GameSpecs/.ci-trigger and pushes it, which reaches the exact same
  `on: push: paths: GameSpecs/**` trigger game-factory.yml already reacts
  to - no CLI, no token, no extra setup on this machine, ever. Either way,
  exactly one run starts, and never a pointless one when nothing changed.

.PARAMETER Silent
  No popups: write to Logs/auto-sync.log and exit with a status code.
  This is what the scheduled task (register-auto-sync.ps1) uses.

.PARAMETER NoTrigger
  Sync only - never start a pipeline run.

.PARAMETER SkipErrorReport
  Don't collect/commit Unity's compile errors (scripts/dev/collect-errors.ps1).

.NOTES
  The GitHub CLI (`gh`) is optional - see .DESCRIPTION. If you do want it
  for the nicer no-extra-commit path:
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
        Start-Sleep -Seconds ([int]$delay)
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

    # Collect Unity's errors and check Builds/ for real output into
    # committed reports BEFORE the dirty check below - writing them is
    # itself a tracked-file change, so it has to be committed here rather
    # than left to trip that check. This is the whole point of the loop:
    # Claude Code has no Unity, no GitHub Actions API access, and no other
    # way to see this PC, so both have to reach it through the repo.
    if (-not $SkipErrorReport) {
        $devDir = Join-Path (Split-Path $PSScriptRoot -Parent) "dev"

        try {
            & (Join-Path $devDir "collect-errors.ps1") -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote -Commit -NoPush
        }
        catch {
            # Never let error reporting be the reason a sync fails.
            Write-Log "Error report step failed (continuing with the sync): $_"
        }

        try {
            & (Join-Path $devDir "report-build-status.ps1") -RepoPath $RepoPath -Branch $Branch -OriginRemote $OriginRemote -Commit -NoPush
        }
        catch {
            Write-Log "Build status report step failed (continuing with the sync): $_"
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
        throw "Uncommitted changes to tracked files - stopping. Commit or stash them first:`n`n$dirty"
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

        throw "Merge failed - stopping (tried to restore the original state). This needs a human:`n`n$mergeError"
    }

    $after = Invoke-Git @("rev-parse", "HEAD")

    Write-Log "Pushing to $originRef"
    Write-Log (Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4)

    if ($forkHead -eq $after) {
        Show-Result "Already up to date. Nothing new reached the fork, so no pipeline run was started." "Information"
        exit 0
    }

    if ($forkHead) {
        $commitCount = Invoke-Git @("rev-list", "--count", "$forkHead..$after")
        $summary = "Pushed $commitCount new commit(s) to the fork."

        $changedPaths = (Invoke-Git @("diff", "--name-only", $forkHead, $after)) -split "\r?\n" | Where-Object { $_ }
        $specChanges = $changedPaths | Where-Object { $_ -like "GameSpecs/*" }

        # An error-report-only push must not start a build: the report is a
        # diagnostic written by this very script, so triggering on it would
        # queue a pointless pipeline run on every scheduled sync that picks
        # up new Unity errors.
        $buildRelevant = $changedPaths | Where-Object { $_ -notlike "Reports/*" }
        if (-not $buildRelevant) {
            Show-Result "$summary`n`nOnly the error report changed, so no pipeline run was started." "Information"
            exit 0
        }
    }
    else {
        $summary = "Pushed the branch to the fork for the first time."
        $specChanges = $null
    }

    if ($NoTrigger) {
        Show-Result "$summary`n`n(-NoTrigger was set, so no pipeline run was started.)" "Information"
        exit 0
    }

    # A push already starts game-factory.yml when GameSpecs/** changed;
    # triggering again here would just queue a duplicate run.
    if ($specChanges) {
        Show-Result "$summary`n`nGameSpecs changed, so the push starts the pipeline on its own.`n`nProgress: https://github.com/$RepoSlug/actions" "Information"
        exit 0
    }

    if (Get-Command gh -ErrorAction SilentlyContinue) {
        Write-Log "Triggering $Workflow for '$GameId' via gh"
        $ErrorActionPreference = "Continue"
        $ghOutput = & gh workflow run $Workflow --repo $RepoSlug --ref $Branch -f "game_id=$GameId" 2>&1
        $ghExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"

        if ($ghExit -eq 0) {
            Show-Result "$summary`n`nRequested a pipeline run for '$GameId'.`n`nProgress: https://github.com/$RepoSlug/actions" "Information"
            exit 0
        }

        Write-Log "gh workflow run failed (exit $ghExit): $(($ghOutput | Out-String).Trim()) - falling back to a trigger-file push."
    }
    else {
        Write-Log "GitHub CLI not found - using the trigger-file push instead."
    }

    # No CLI, no token: bumping a file under GameSpecs/ and pushing it hits
    # the same push-triggered path a real GameSpec edit would, which is how
    # game-factory.yml is already wired to start on its own (see the .yml's
    # `on: push: paths: GameSpecs/**`). Currently always targets game01,
    # since that push trigger only ever runs with the workflow's default
    # game_id input - fine for now since it is the only game that exists.
    $triggerPath = Join-Path $RepoPath "GameSpecs\.ci-trigger"
    $triggerContent = "Bumped $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') to start the Game Factory Pipeline for '$GameId' without the GitHub CLI. Not a GameSpec - GameValidator only reads *.json here."
    Set-Content -Path $triggerPath -Value $triggerContent -Encoding UTF8

    Invoke-Git @("add", "GameSpecs/.ci-trigger") | Out-Null
    Invoke-Git @("commit", "-m", "chore: trigger Game Factory Pipeline for $GameId") | Out-Null
    Invoke-Git @("push", $OriginRemote, $Branch) -Retries 4 | Out-Null

    Show-Result "$summary`n`nPushed a trigger-file bump to start the pipeline for '$GameId' (no GitHub CLI needed).`n`nProgress: https://github.com/$RepoSlug/actions" "Information"
    exit 0
}
catch {
    Show-Result "Sync failed:`n`n$_" "Error"
    exit 1
}
