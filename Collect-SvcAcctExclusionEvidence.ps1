<#
.SYNOPSIS
    Collects Splunk evidence supporting the exclusion of service accounts (non-human
    identities) from the database change review population.

.DESCRIPTION
    Self-contained evidence script. Every Splunk query is written in full inside this
    script (no Splunk macros or lookups are used), so the script's SHA256 hash covers
    the exact logic that ran. The only input is server_sets.csv (in-scope SQL servers and
    databases), which is hashed and logged at run time. The accounts are NOT a typed list:
    every account active on the in-scope servers and databases in the period is discovered
    from Splunk (QP) and every query covers all of them.

    Queries run ONE AT A TIME (the Splunk account allows two concurrent searches; this
    leaves one free). Each query's Splunk search ID (SID) is recorded so it can be
    independently verified in Splunk's _audit index (query Q_AUDIT does this at the end).

    Output (one folder per run):
      Q0_Completeness.csv   in-scope SQL servers sending audit events, by day
      QP_Population.csv     every account active on in-scope servers/databases (the population assessed)
      QA_Profile.csv        activity overview per account
      QB_Connections.csv    every machine/program each account connected from; human tools flagged
      QC_Changes.csv        schema / permission / role / ownership changes (exceptions)
      QD_Pattern.csv        activity by weekday/weekend and hour
      QE_WinLogons.csv      Windows logons by the accounts, interactive ones flagged
      Q_AUDIT.csv           Splunk's own record of the searches above
      queries\*.spl         exact query text sent to Splunk
      RunManifest.csv/.json hashes, parameters, SIDs, row counts
      screenshots\*.png     Splunk Web showing each search (query text, time range, results)
      Screenshot.png        screen capture of the RUN SUMMARY
      SvcAcct_Exclusion_Evidence_<RunId>.xlsx   the workbook, filled in by this script
      Transcript.txt        full console log
      SHA256SUMS.txt        SHA256 of every file above

    Normally started from Run-Evidence.ps1, which holds the settings (URLs and dates).

.PARAMETER SplunkBaseUrl
    Splunk REST endpoint, e.g. https://yourcompany.splunkcloud.com:8089

.PARAMETER SplunkWebUrl
    Splunk Web address used in the browser, e.g. https://yourcompany.splunkcloud.com
    Each finished search is opened there and screenshotted.

.PARAMETER WorkbookTemplate
    Path to SvcAcct_Exclusion_Evidence_TEMPLATE.xlsx. The script opens it in Excel (desktop
    Excel required), fills in every Splunk tab and the run details, and saves a new workbook
    in the run folder. The template itself is not changed. Skipped if omitted.

.PARAMETER Preflight
    Quick check (about 2 minutes) that everything works, WITHOUT an evidence run: Splunk token
    and API, host names, field extraction, Splunk Web screenshot (browser maximized), Excel,
    and keep-awake. Writes to a SvcAcctPREFLIGHT_<time> folder, which is not evidence.

.PARAMETER WinEventIndex
    Index holding WinEventLog:Security (SQL audit EventCode 33205 and logon EventCode 4624).

.PARAMETER ServerSetsCsv
    Input file: server_set, host, in_scope_databases. See the Inputs tab of the workbook.

.PARAMETER StartDate / EndDate
    Review period, inclusive, in this computer's local time zone (yyyy-MM-dd).



.EXAMPLE
    .\Collect-SvcAcctExclusionEvidence.ps1 -SplunkBaseUrl https://acme.splunkcloud.com:8089 `
        -WinEventIndex wineventlog -ServerSetsCsv .\server_sets.csv `
        -StartDate 2026-09-01 -EndDate 2026-11-13
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $SplunkBaseUrl,
    [Parameter(Mandatory)] [string] $SplunkWebUrl,
    [Parameter(Mandatory)] [string] $WinEventIndex,
    [Parameter(Mandatory)] [string] $ServerSetsCsv,
    [Parameter(Mandatory)] [datetime] $StartDate,
    [Parameter(Mandatory)] [datetime] $EndDate,
    [string] $OutputRoot = '.',
    [int]    $JobTimeoutSeconds = 3600,
    [int]    $AuditIndexWaitSeconds = 90,
    [string] $WorkbookTemplate = '',
    [int]    $BrowserWaitSeconds = 25,
    [int]    $JobTtlSeconds = 604800,
    [switch] $NoScreenshot,
    [switch] $Preflight
)

$ErrorActionPreference = 'Stop'
$ScriptVersion = '3.1.0'

# =====================================================================================
# REGION: SPLUNK CONNECTION  (the only part that should need changes for your setup;
# compare with your previously working Splunk client and adjust here only)
# =====================================================================================
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:SplunkHeaders = $null

function Connect-Splunk {
    # Token comes from the SPLUNK_TOKEN environment variable (e.g. "Bearer eyJ...").
    # Used as-is if it already starts with "Bearer "; otherwise "Bearer " is added.
    # The token is never printed, logged, or written to any output file.
    $tok = $env:SPLUNK_TOKEN
    if (-not $tok) { throw 'Environment variable SPLUNK_TOKEN is not set. Set it in this PowerShell window, then run again.' }
    $tok = $tok.Trim()
    if ($tok -notmatch '^(?i)bearer\s') { $tok = "Bearer $tok" }
    $script:SplunkHeaders = @{ Authorization = $tok }
}

function Invoke-Splunk {
    param([string]$Method, [string]$Path, [hashtable]$Body)
    $uri = $SplunkBaseUrl.TrimEnd('/') + $Path
    $p = @{ Method = $Method; Uri = $uri; Headers = $script:SplunkHeaders; UseBasicParsing = $true }
    if ($Body) { $p.Body = $Body; $p.ContentType = 'application/x-www-form-urlencoded' }
    Invoke-RestMethod @p
}
# ============================ END REGION: SPLUNK CONNECTION ===========================

# ----------------------------------------------------------------------------- helpers
function Get-Sha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash }

function ConvertTo-SplString([string]$s) {
    # Quoted SPL string literal: escape backslash and double quote.
    '"' + $s.Replace('\', '\\').Replace('"', '\"') + '"'
}
function ConvertTo-SplList([string[]]$items) {
    $items = @($items | Where-Object { $_ } | Select-Object -Unique)
    if ($items.Count -eq 0) { $items = @('__none__') }
    ($items | ForEach-Object { ConvertTo-SplString $_ }) -join ','
}
# Screen capture of all monitors (one monitor is recommended). Built from text at run time so the script still
# loads on machines without System.Drawing (it only runs on Windows).
$shotCode = @'
param($Path)
if (-not ('DpiHelper' -as [type])) {
    Add-Type 'using System.Runtime.InteropServices; public class DpiHelper { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }'
}
[void][DpiHelper]::SetProcessDPIAware()
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b   = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g   = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
'@
# Win32 helpers: keep the PC awake, maximize / bring a window to the front, tiny mouse nudge.
if (-not ('EvidenceWin32' -as [type])) {
    Add-Type @'
using System; using System.Runtime.InteropServices;
public static class EvidenceWin32 {
    [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, int dx, int dy, uint data, UIntPtr extra);
}
'@
}
# Keeps the display on and stops sleep / screen-saver lock while the script runs (reset at the end).
function Enable-KeepAwake  { try { [EvidenceWin32]::SetThreadExecutionState([uint32]2147483651) -ne 0 } catch { $false } }   # ES_CONTINUOUS|ES_DISPLAY_REQUIRED|ES_SYSTEM_REQUIRED
function Disable-KeepAwake { try { [void][EvidenceWin32]::SetThreadExecutionState([uint32]2147483648) } catch { } }       # ES_CONTINUOUS (back to normal)
# Moves the mouse 1 pixel and back, so an "inactivity" lock policy sees activity. Invisible in practice.
$script:LastNudge = Get-Date
function Invoke-Nudge {
    if (((Get-Date) - $script:LastNudge).TotalSeconds -lt 30) { return }
    try { [EvidenceWin32]::mouse_event(1, 1, 0, 0, [UIntPtr]::Zero); [EvidenceWin32]::mouse_event(1, -1, 0, 0, [UIntPtr]::Zero) } catch { }
    $script:LastNudge = Get-Date
}
function Wait-Seconds([int]$Seconds) {
    for ($i = 0; $i -lt $Seconds; $i++) { Start-Sleep -Seconds 1; Invoke-Nudge }
}

function Save-Screenshot([string]$Path) {
    & ([scriptblock]::Create($shotCode)) $Path
    Get-Sha256 $Path
}

# Opens the finished search in Splunk Web and screenshots it: Splunk's own screen showing
# the search text, time range, result count and results, with the taskbar clock.
function Save-SplunkScreenshot([string]$Id, [string]$Sid) {
    $url = $SplunkWebUrl.TrimEnd('/') + '/app/search/search?sid=' + [uri]::EscapeDataString($Sid)
    Write-Host "    Opening in Splunk Web: $url"
    Start-Process $url
    # Wait until a browser window titled like Splunk's search page appears, then bring it to the front
    $found = $null
    $deadline = (Get-Date).AddSeconds($BrowserWaitSeconds)
    do {
        Wait-Seconds 2
        $found = Get-Process | Where-Object { $_.MainWindowTitle -like '*Search*Splunk*' } | Select-Object -First 1
    } while (-not $found -and (Get-Date) -lt $deadline)
    $activated = $false
    if ($found) {
        # Maximize (not F11 full screen: the address bar with the search ID and the taskbar clock stay visible)
        try { [void][EvidenceWin32]::ShowWindow($found.MainWindowHandle, 3); [void][EvidenceWin32]::SetForegroundWindow($found.MainWindowHandle) } catch { }
        try { $activated = (New-Object -ComObject WScript.Shell).AppActivate($found.Id) } catch { }
        Wait-Seconds 6     # let the results finish rendering
    }
    if (-not $activated) {
        Write-Host "    WARNING: could not confirm the Splunk search page was in front (still loading, or sign-in page?). Check this screenshot." -ForegroundColor Yellow
        $script:RunNotes = $true
    }
    $file = "screenshots\${Id}_splunk.png"
    $hash = Save-Screenshot (Join-Path $RunDir $file)
    Write-Host "    Splunk screenshot: $file  SHA256 $hash"
    @{ File = $file; Hash = $hash; Confirmed = $activated }
}

function Write-Banner([string]$text) {
    Write-Host ('=' * 90) -ForegroundColor Cyan
    Write-Host $text -ForegroundColor Cyan
    Write-Host ('=' * 90) -ForegroundColor Cyan
}

$MaxCount = 500000
$PageSize = 1000          # small pages keep each JSON response well under PowerShell 5.1's size limit
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Invoke-SplunkQuery {
    param([string]$Id, [string]$Spl, [string[]]$Columns, [string]$OutFile, [string]$PostProcessing = 'None')

    # Query text is saved byte-for-byte as sent (UTF-8, no BOM, no added newline), so its hash is the hash of the query string.
    $splFile = Join-Path $QueryDir "$Id.spl"
    [IO.File]::WriteAllText($splFile, $Spl, $Utf8NoBom)

    $started = Get-Date
    Write-Host ''
    Write-Host ("[{0}] {1} starting  (query SHA256 {2})" -f $started.ToString('yyyy-MM-dd HH:mm:ss zzz'), $Id, (Get-Sha256 $splFile))

    $job = Invoke-Splunk -Method Post -Path '/services/search/jobs' -Body @{
        search        = $Spl
        earliest_time = $EarliestEpoch
        latest_time   = $LatestEpoch
        exec_mode     = 'normal'
        max_count     = $MaxCount
        output_mode   = 'json'
    }
    $sid = $job.sid
    Write-Host "    SID: $sid"

    $deadline = (Get-Date).AddSeconds($JobTimeoutSeconds)
    do {
        Wait-Seconds 5
        $st = (Invoke-Splunk -Method Get -Path "/services/search/jobs/$sid`?output_mode=json").entry[0].content
        Write-Host ("    state={0} progress={1:P0}" -f $st.dispatchState, [double]$st.doneProgress)
        if ((Get-Date) -gt $deadline) {
            try { Invoke-Splunk -Method Delete -Path "/services/search/jobs/$sid" | Out-Null } catch { }   # free the search slot
            throw "$Id timed out after $JobTimeoutSeconds seconds (SID $sid); job cancelled"
        }
    } while ($st.dispatchState -notin @('DONE', 'FAILED'))

    if ($st.dispatchState -eq 'FAILED' -or $st.isFailed) {
        throw "$Id FAILED in Splunk (SID $sid): $($st.messages | ConvertTo-Json -Compress)"
    }
    $splunkCount = [int]$st.resultCount

    # Keep the finished search in Splunk (default is ~10 minutes) so it can be opened during review
    $ttlSet = 'N'
    try { Invoke-Splunk -Method Post -Path "/services/search/jobs/$sid/control" -Body @{ action = 'setttl'; ttl = $JobTtlSeconds } | Out-Null; $ttlSet = "Y ($JobTtlSeconds s)" }
    catch { Write-Host "    Could not extend job lifetime: $($_.Exception.Message)" -ForegroundColor Yellow }

    # Anything that could mean incomplete results: finalized (stopped early), Splunk warnings/errors, or the result cap reached.
    $issues = @()
    if ($st.isFinalized -eq $true -or "$($st.isFinalized)" -eq '1') { $issues += 'job was finalized (stopped early)' }
    foreach ($m in @($st.messages)) {
        if ($m -and $m.type -in @('WARN', 'ERROR', 'FATAL')) { $issues += "$($m.type): $($m.text)" }
    }
    if ($splunkCount -ge $MaxCount) { $issues += "result count reached max_count ($MaxCount)" }

    # Page through all results
    $rows = New-Object System.Collections.Generic.List[object]
    $offset = 0
    while ($offset -lt $splunkCount) {
        $page = Invoke-Splunk -Method Get -Path "/services/search/jobs/$sid/results?output_mode=json&count=$PageSize&offset=$offset"
        $got = @($page.results).Count
        if ($got -eq 0) { break }
        foreach ($r in @($page.results)) { $rows.Add($r) }
        $offset += $got
    }

    $data = foreach ($r in $rows) {
        $o = [ordered]@{}
        foreach ($c in $Columns) {
            $v = $r.$c
            if ($v -is [array]) { $v = $v -join '; ' }
            $o[$c] = $v
        }
        [pscustomobject]$o
    }

    [pscustomobject]@{
        Id = $Id; Sid = $sid; Started = $started; SplunkCount = $splunkCount
        EventCount = $st.eventCount; ScanCount = $st.scanCount; Issues = $issues; TtlSet = $ttlSet
        Data = @($data | Where-Object { $null -ne $_ }); Columns = $Columns; OutFile = $OutFile; SplFile = $splFile; PostProcessing = $PostProcessing
    }
}

function Save-Result($res, [object[]]$Data) {
    $path = Join-Path $RunDir $res.OutFile
    if ($Data.Count -gt 0) {
        $Data | Select-Object $res.Columns | Export-Csv -LiteralPath $path -NoTypeInformation -Encoding UTF8
    } else {
        # header only, so an empty result is still evidence
        ('"' + ($res.Columns -join '","') + '"') | Set-Content -LiteralPath $path -Encoding UTF8
    }
    $finished = Get-Date
    $hash = Get-Sha256 $path
    $check  = if ($res.SplunkCount -eq $res.Data.Count) { 'OK' } else { 'MISMATCH' }
    $status = if ($check -eq 'OK' -and $res.Issues.Count -eq 0) { 'OK' } else { 'FAILED' }
    if ($status -ne 'OK') { $script:RunFailed = $true }
    Write-Host ("    Splunk resultCount={0}  rows retrieved={1}  retrieval check={2}" -f $res.SplunkCount, $res.Data.Count, $check)
    foreach ($i in $res.Issues) { Write-Host "    SPLUNK ISSUE: $i" -ForegroundColor Red }
    Write-Host ("    rows written={0}  file={1}  status={2}" -f $Data.Count, $res.OutFile, $status)
    Write-Host ("    SHA256 {0}" -f $hash)
    $shot = @{ File = ''; Hash = '' }
    if (-not $NoScreenshot) {
        try { $shot = Save-SplunkScreenshot $res.Id $res.Sid }
        catch { Write-Host "    Splunk screenshot failed: $($_.Exception.Message)" -ForegroundColor Yellow; $script:RunNotes = $true }
    }
    $script:Manifest.Add([pscustomobject][ordered]@{
        query_id           = $res.Id
        source_query       = $res.Id
        status             = $status
        splunk_sid         = $res.Sid
        started_local      = $res.Started.ToString('yyyy-MM-dd HH:mm:ss zzz')
        finished_local     = $finished.ToString('yyyy-MM-dd HH:mm:ss zzz')
        splunk_eventcount  = $res.EventCount
        splunk_scancount   = $res.ScanCount
        splunk_resultcount = $res.SplunkCount
        rows_retrieved     = $res.Data.Count
        retrieval_check    = $check
        splunk_issues      = ($res.Issues -join ' | ')
        rows_written       = $Data.Count
        post_processing    = $res.PostProcessing
        output_file        = $res.OutFile
        output_sha256      = $hash
        query_file         = "queries\$($res.Id).spl"
        query_sha256       = Get-Sha256 $res.SplFile
        screenshot_file    = $shot.File
        screenshot_sha256  = $shot.Hash
        job_ttl_set        = $res.TtlSet
        audit_check        = ''
    })
}

# One output file cut from a combined search's results (rows where section = $Id). No calculation is done:
# the rows and columns are exactly as Splunk returned them, except where $Note says otherwise.
function Save-Derived([string]$ParentId, [string]$Id, [string]$OutFile, [string[]]$Columns, [object[]]$Data, [string]$Note) {
    $parent = $script:Manifest | Where-Object { $_.query_id -eq $ParentId } | Select-Object -First 1
    $path = Join-Path $RunDir $OutFile
    if ($Data.Count -gt 0) { $Data | Select-Object $Columns | Export-Csv -LiteralPath $path -NoTypeInformation -Encoding UTF8 }
    else { ('"' + ($Columns -join '","') + '"') | Set-Content -LiteralPath $path -Encoding UTF8 }
    $hash = Get-Sha256 $path
    Write-Host ("    {0,-3} rows={1,-6} file={2}  SHA256 {3}" -f $Id, $Data.Count, $OutFile, $hash)
    $script:Manifest.Add([pscustomobject][ordered]@{
        query_id = $Id; source_query = $ParentId; status = $parent.status; splunk_sid = $parent.splunk_sid
        started_local = $parent.started_local; finished_local = $parent.finished_local
        splunk_eventcount = ''; splunk_scancount = ''; splunk_resultcount = ''; rows_retrieved = ''; retrieval_check = ''
        splunk_issues = ''; rows_written = $Data.Count
        post_processing = $(if ($Note) { $Note } else { "Rows where section=$Id from $($parent.output_file); no calculation" })
        output_file = $OutFile; output_sha256 = $hash; query_file = $parent.query_file; query_sha256 = $parent.query_sha256
        screenshot_file = $parent.screenshot_file; screenshot_sha256 = $parent.screenshot_sha256; job_ttl_set = $parent.job_ttl_set; audit_check = ''
    })
}

function Add-FailedStep([string]$Id, [string]$Message, [string]$Sid = '') {
    $script:RunFailed = $true
    $script:Manifest.Add([pscustomobject][ordered]@{
        query_id = $Id; source_query = $Id; status = 'FAILED'; splunk_sid = $Sid; started_local = ''; finished_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
        splunk_eventcount = ''; splunk_scancount = ''; splunk_resultcount = ''; rows_retrieved = ''; retrieval_check = ''
        splunk_issues = $Message; rows_written = ''; post_processing = ''; output_file = ''; output_sha256 = ''; query_file = ''; query_sha256 = ''
        screenshot_file = ''; screenshot_sha256 = ''; job_ttl_set = ''; audit_check = ''
    })
}


# ------------------------------------------------------------------ workbook (Excel)
# Columns written as numbers; everything else is written as text, so Excel cannot
# re-interpret values (dates, leading '=' etc.).
$NumericCols = @('events','logins_succeeded','logins_failed','days_with_events','expected_days','change_actions')   # whole numbers only

function Write-CsvToSheet($Sheet, [string]$CsvPath, [int]$Row, [int]$Col) {
    if (-not (Test-Path -LiteralPath $CsvPath)) { return 0 }
    $rows = @(Import-Csv -LiteralPath $CsvPath)
    $cols = @(if ($rows.Count) { $rows[0].PSObject.Properties.Name }
              else { ((Get-Content -LiteralPath $CsvPath -TotalCount 1) -replace '"', '') -split ',' })
    $n = $rows.Count + 1; $m = $cols.Count
    # A column is written as numbers only if it is a known count column AND every value is a whole number;
    # everything else is written as text so Excel cannot re-interpret it (dates, '=', '1e5', etc.).
    $isNum = @(for ($j = 0; $j -lt $m; $j++) {
        $c = $cols[$j]
        ($c -in $NumericCols) -and (@($rows | Where-Object { [string]$_.$c -notmatch '^-?\d{1,15}$' }).Count -eq 0)
    })
    $arr = New-Object 'object[,]' $n, $m
    for ($j = 0; $j -lt $m; $j++) { $arr[0, $j] = [string]$cols[$j] }
    for ($i = 0; $i -lt $rows.Count; $i++) {
        for ($j = 0; $j -lt $m; $j++) {
            $v = [string]$rows[$i].($cols[$j])
            if ($isNum[$j]) { $arr[($i + 1), $j] = [double]$v } else { $arr[($i + 1), $j] = $v }
        }
    }
    for ($j = 0; $j -lt $m; $j++) {
        $colRange = $Sheet.Range($Sheet.Cells.Item($Row, $Col + $j), $Sheet.Cells.Item($Row + $n - 1, $Col + $j))
        $colRange.NumberFormat = '@'
        if ($isNum[$j] -and $n -gt 1) {
            $Sheet.Range($Sheet.Cells.Item($Row + 1, $Col + $j), $Sheet.Cells.Item($Row + $n - 1, $Col + $j)).NumberFormat = '0'
        }
    }
    $Sheet.Range($Sheet.Cells.Item($Row, $Col), $Sheet.Cells.Item($Row + $n - 1, $Col + $m - 1)).Value2 = $arr
    return $rows.Count
}

function Add-Picture($Sheet, [string]$Path, [int]$Row, [int]$Col, [double]$Width) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return }
    $anchor = $Sheet.Cells.Item($Row, $Col)
    $pic = $Sheet.Shapes.AddPicture($Path, 0, -1, $anchor.Left, $anchor.Top, -1, -1)
    $pic.LockAspectRatio = -1
    $pic.Width = $Width
}

function Build-Workbook {
    $tabs = @(
        @{ Id = 'Q0';      Sheet = '2. Log Completeness';      Csv = 'Q0_Completeness.csv'; PicCol = 10 },
        @{ Id = 'QP';      Sheet = '1. Accounts Found';        Csv = 'QP_Population.csv';   PicCol = 11 },
        @{ Id = 'QA';      Sheet = '3. Account Activity';           Csv = 'QA_Profile.csv';      PicCol = 14 },
        @{ Id = 'QB';      Sheet = '4. Connections';       Csv = 'QB_Connections.csv';  PicCol = 17 },
        @{ Id = 'QC';      Sheet = '5. Schema & Permission Changes';           Csv = 'QC_Changes.csv';      PicCol = 15 },
        @{ Id = 'QD';      Sheet = '6. Activity by Hour';           Csv = 'QD_Pattern.csv';      PicCol = 7  },
        @{ Id = 'QE';      Sheet = '7. Windows Logons';        Csv = 'QE_WinLogons.csv';    PicCol = 15 },
        @{ Id = 'Q_AUDIT'; Sheet = '8. Splunk Audit Check'; Csv = 'Q_AUDIT.csv';         PicCol = 9  }
    )
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
    $wbk = $null; $ws = $null
    try {
        $wbk = $xl.Workbooks.Open((Resolve-Path $WorkbookTemplate).Path, 0, $true)

        # Inputs (server_sets.csv exactly as read)
        $ws = $wbk.Worksheets.Item('Inputs')
        [void](Write-CsvToSheet $ws $ServerSetsPath 14 1)

        # Splunk evidence tabs
        foreach ($t in $tabs) {
            $m = $script:Manifest | Where-Object { $_.query_id -eq $t.Id } | Select-Object -First 1
            $ws = $wbk.Worksheets.Item($t.Sheet)
            if ((-not $m) -or (-not $m.output_file)) {
                $ws.Cells.Item(11, 2).Value2 = "NOT RUN / FAILED - see Run Manifest. $($m.splunk_issues)"
                continue
            }
            [void](Write-CsvToSheet $ws (Join-Path $RunDir $m.output_file) 14 1)
            $src = if ($m.source_query -and $m.source_query -ne $m.query_id) {
                $p = $script:Manifest | Where-Object { $_.query_id -eq $m.source_query } | Select-Object -First 1
                "This tab is section $($m.query_id) of combined search $($m.source_query) ($($p.splunk_resultcount) rows across all sections; $($p.post_processing)) | "
            } else { "Search $($m.query_id) | Rows: Splunk $($m.splunk_resultcount), written $($m.rows_written) | " }
            $ws.Cells.Item(11, 2).Value2 = ("Run {0} | Started {1} | Finished {2} | Splunk SID {3} | {4}Rows on this tab: {5} | Status {6} | " +
                "Query SHA256 {7} | Output {8} SHA256 {9} | Splunk screenshot {10} SHA256 {11} | Splunk audit log check: {12}") -f `
                $RunId, $m.started_local, $m.finished_local, $m.splunk_sid, $src, $m.rows_written, $m.status,
                $m.query_sha256, $m.output_file, $m.output_sha256, $m.screenshot_file, $m.screenshot_sha256, $(if ($m.audit_check) { $m.audit_check } else { 'n/a' })
            if ($m.screenshot_file) { Add-Picture $ws (Join-Path $RunDir $m.screenshot_file) 3 $t.PicCol 640 }
        }

        # AD tab (optional)

        # Run Manifest tab
        $ws = $wbk.Worksheets.Item('Run Manifest')
        $cells = @(
            @(11, $RunId),
            @(12, $banner['Run by']),
            @(13, $banner['Computer']),
            @(14, ("{0} / {1}" -f $banner['Run started (local)'], $banner['Run started (UTC)'])),
            @(15, $ScriptHash),
            @(16, [string]$banner['Accounts discovered (QP)']),
            @(17, $banner['Server sets CSV SHA256']),
            @(18, ($banner['Period (local)'] + ' | ' + $banner['Period (epoch sent)'])),
            @(19, ("{0} / {1}" -f $SplunkUser, $SplunkTz)),
            @(20, $overall),
            @(21, $banner['Template SHA256']),
            @(22, (Get-Sha256 $manifestCsv)),
            @(23, [string]$banner['Reconciliation'])
        )
        foreach ($c in $cells) {
            $cell = $ws.Cells.Item([int]$c[0], 2)
            $cell.NumberFormat = '@'
            $cell.Value2 = [string]$c[1]
        }
        [void](Write-CsvToSheet $ws $manifestCsv 27 1)
        Add-Picture $ws (Join-Path $RunDir 'Screenshot.png') 43 1 900

        $xl.CalculateFull()
        $out = Join-Path $RunDir "SvcAcct_Exclusion_Evidence_$RunId.xlsx"
        $wbk.SaveAs($out, 51)
        Write-Host "Workbook saved: $out"
    } finally {
        if ($wbk) { try { $wbk.Close($false) } catch { } }
        foreach ($o in @($ws, $wbk)) { if ($o) { try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($o) } catch { } } }
        $ws = $null; $wbk = $null
        [GC]::Collect(); [GC]::WaitForPendingFinalizers(); [GC]::Collect(); [GC]::WaitForPendingFinalizers()
        try { $xl.Quit() } catch { }
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
        $xl = $null
        [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    }
}

# --------------------------------------------------------------------- setup and inputs
$ScriptPath = $PSCommandPath
$ScriptHash = Get-Sha256 $ScriptPath
$RunStart   = Get-Date
$RunId      = $RunStart.ToString('yyyyMMdd_HHmmss')
try { $Host.UI.RawUI.WindowTitle = "SvcAcctEvidence_$RunId" } catch { }
$RunDir     = Join-Path (Resolve-Path $OutputRoot) $(if ($Preflight) { "SvcAcctPREFLIGHT_$RunId" } else { "SvcAcctEvidence_$RunId" })
$QueryDir   = Join-Path $RunDir 'queries'
New-Item -ItemType Directory -Path $QueryDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RunDir 'screenshots') -Force | Out-Null
Start-Transcript -Path (Join-Path $RunDir 'Transcript.txt') | Out-Null

$ServerSetsPath = (Resolve-Path $ServerSetsCsv).Path
$ServerSets = @(Import-Csv -LiteralPath $ServerSetsPath)
# Trim stray spaces in every value (a trailing space would silently match nothing in Splunk)
foreach ($row in @($ServerSets)) {
    foreach ($pr in $row.PSObject.Properties) { if ($pr.Value -is [string]) { $pr.Value = $pr.Value.Trim() } }
}

foreach ($col in 'server_set','host','in_scope_databases') {
    if ($col -notin $ServerSets[0].PSObject.Properties.Name) { throw "server sets CSV is missing column '$col'" }
}
$dupHosts = @($ServerSets | Group-Object { $_.host.ToLower() } | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name })
if ($dupHosts.Count) { throw "server sets CSV lists these hosts more than once: $($dupHosts -join ', '). Each host must be in exactly one row." }
# Period: StartDate 00:00 local to (EndDate + 1 day) 00:00 local, sent to Splunk as epoch seconds
$PeriodStart   = $StartDate.Date
$PeriodEnd     = $EndDate.Date.AddDays(1)
$EarliestEpoch = [int64]([DateTimeOffset]$PeriodStart).ToUnixTimeSeconds()
$LatestEpoch   = [int64]([DateTimeOffset]$PeriodEnd).ToUnixTimeSeconds()
$ExpectedDays  = [int]($PeriodEnd - $PeriodStart).TotalDays

# Lists built from the inputs
$Hosts      = @($ServerSets.host | Select-Object -Unique)
$HostDbPairs = foreach ($s in $ServerSets) {
    foreach ($db in ($s.in_scope_databases -split ';')) { if ($db.Trim()) { ("{0}|{1}" -f $s.host, $db.Trim()).ToLower() } }
}

$HostsSpl    = ConvertTo-SplList $Hosts
$HostDbSpl   = ConvertTo-SplList $HostDbPairs
# host -> server_set, as an SPL case() expression
$SetCaseSpl  = 'case(' + ((($ServerSets | Group-Object server_set) | ForEach-Object {
    'in(lower(host), {0}), {1}' -f (ConvertTo-SplList @($_.Group | ForEach-Object { $_.host.ToLower() })), (ConvertTo-SplString $_.Name) }) -join ', ') + ', true(), "")'

# ------------------------------------------------------------------------------ banner
Write-Banner "SERVICE ACCOUNT EXCLUSION EVIDENCE COLLECTION  v$ScriptVersion"
$banner = [ordered]@{
    'Run ID'                 = $RunId
    'Run started (local)'    = $RunStart.ToString('yyyy-MM-dd HH:mm:ss zzz')
    'Run started (UTC)'      = $RunStart.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss') + 'Z'
    'Run by'                 = "$env:USERDOMAIN\$env:USERNAME"
    'Computer'               = $env:COMPUTERNAME
    'PowerShell'             = $PSVersionTable.PSVersion.ToString()
    'Script'                 = $ScriptPath
    'Script SHA256'          = $ScriptHash
    'Server sets CSV'        = $ServerSetsPath
    'Server sets CSV SHA256' = Get-Sha256 $ServerSetsPath
    'In-scope SQL servers'   = ($Hosts -join ', ')
    'Period (local)'         = "{0} 00:00 to {1} 23:59:59 ({2} days)" -f $PeriodStart.ToString('yyyy-MM-dd'), $EndDate.ToString('yyyy-MM-dd'), $ExpectedDays
    'Period (epoch sent)'    = "earliest=$EarliestEpoch latest=$LatestEpoch"
    'Period (UTC)'           = "{0}Z to {1}Z" -f $PeriodStart.ToUniversalTime().ToString('yyyy-MM-dd HH:mm'), $PeriodEnd.ToUniversalTime().ToString('yyyy-MM-dd HH:mm')
    'Splunk API'             = $SplunkBaseUrl
    'Splunk Web'             = $SplunkWebUrl
    'Workbook template'      = $(if ($WorkbookTemplate) { (Resolve-Path $WorkbookTemplate).Path } else { '(workbook not built)' })
    'Template SHA256'        = $(if ($WorkbookTemplate) { Get-Sha256 (Resolve-Path $WorkbookTemplate).Path } else { '' })
    'Windows event index'    = $WinEventIndex
    'Output folder'          = $RunDir
}
$banner.GetEnumerator() | ForEach-Object { Write-Host ("{0,-24}: {1}" -f $_.Key, $_.Value) }
$script:Manifest  = New-Object System.Collections.Generic.List[object]
$script:RunFailed = $false
$script:RunNotes  = $false
try {
$KeepAwakeOk = Enable-KeepAwake
Write-Host ("{0,-24}: {1}" -f 'Keep screen awake', $(if ($KeepAwakeOk) { 'ON (display stays on; mouse nudged 1px every 30s while waiting)' } else { 'COULD NOT ENABLE - set your screen lock timeout longer than the run' }))
Connect-Splunk

# Record which Splunk user ran the searches and that user's time zone (Splunk formats times in it)
try {
    $ctx = (Invoke-Splunk -Method Get -Path '/services/authentication/current-context?output_mode=json').entry[0].content
    $SplunkUser = $ctx.username
    $tz = (Invoke-Splunk -Method Get -Path "/services/authentication/users/$([uri]::EscapeDataString($SplunkUser))?output_mode=json").entry[0].content.tz
    $SplunkTz = if ($tz) { $tz } else { '(not set: Splunk server default)' }
} catch { $SplunkUser = '(could not read)'; $SplunkTz = '(could not read)' }
$banner['Splunk user'] = $SplunkUser
$banner['Splunk user time zone'] = $SplunkTz
$banner['Local time zone'] = [TimeZoneInfo]::Local.Id
Write-Host ("{0,-24}: {1}" -f 'Splunk user', $SplunkUser)
Write-Host ("{0,-24}: {1}   (times in outputs use this; local zone is {2})" -f 'Splunk user time zone', $SplunkTz, [TimeZoneInfo]::Local.Id)

# =====================================================================================
# QUERIES
# Shared base: SQL Server audit records (EventCode 33205) from the in-scope servers,
# with the audit fields extracted from the Message text.
# =====================================================================================
$SqlBase = @'
search index=__IDX__ source="WinEventLog:Security" EventCode=33205 host IN (__HOSTS__)
| fields _time host Message
| rex field=Message "(?<![a-z_])action_id:(?<action_id>\S*)"
| rex field=Message "(?<![a-z_])server_principal_name:(?<server_principal_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])database_name:(?<database_name>.*?)(?=\s+[a-z_]+:|$)"
| where isnotnull(server_principal_name) AND server_principal_name!=""
| eval db_in_scope=case(isnull(database_name) OR database_name="", "Server-level", in(lower(host."|".database_name), __HOSTDB__), "Y", in(action_id,"LGIS","LGIF"), "Login", true(), "N")
| where db_in_scope!="N"
| rex field=Message "(?<![a-z_])succeeded:(?<succeeded>\S*)"
| rex field=Message "(?<![a-z_])class_type:(?<class_type>\S*)"
| rex field=Message "(?<![a-z_])object_name:(?<object_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])statement:(?<statement>[\s\S]*?)(?:\s+additional_information:|$)"
| rex field=Message "(?<![a-z_])client_ip:(?<client_ip>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])application_name:(?<application_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])host_name:(?<client_host>.*?)(?=\s+[a-z_]+:|$)"
| eval account=lower(server_principal_name), sql_server=host
'@
$SqlBase = $SqlBase.Replace('__IDX__', $WinEventIndex).Replace('__HOSTS__', $HostsSpl).Replace('__HOSTDB__', $HostDbSpl) + "`n"
$TimeFmt = '"%Y-%m-%d %H:%M:%S %z"'

# =====================================================================================
# PREFLIGHT (-Preflight): quick checks over the last 24 hours, then stop. Not evidence.
# =====================================================================================
if ($Preflight) {
    Write-Banner 'PREFLIGHT CHECKS - NOT EVIDENCE (last 24 hours only)'
    $pf = New-Object System.Collections.Generic.List[object]
    function Add-Check($Name, $Result, $Detail) { $pf.Add([pscustomobject]@{ Check = $Name; Result = $Result; Detail = $Detail }) }
    Add-Check 'Keep screen awake' $(if ($KeepAwakeOk) { 'PASS' } else { 'WARN' }) $(if ($KeepAwakeOk) { 'display kept on' } else { 'set screen lock timeout longer than the run' })
    Add-Check 'Splunk API + token' $(if ($SplunkUser -and $SplunkUser -ne '(could not read)') { 'PASS' } else { 'FAIL' }) "Splunk user: $SplunkUser, time zone: $SplunkTz"
    $EarliestEpoch = [int64]([DateTimeOffset](Get-Date).AddHours(-24)).ToUnixTimeSeconds()
    $LatestEpoch   = [int64]([DateTimeOffset](Get-Date)).ToUnixTimeSeconds()

    # 1. Host names: each in-scope server should have SQL audit (33205) and logon (4624) events
    $pf1 = @"
search index=$WinEventIndex source IN ("WinEventLog:Security","XmlWinEventLog:Security") EventCode IN (33205, 4624) host IN ($HostsSpl)
| stats count(eval(EventCode=33205)) AS sql_audit_events count(eval(EventCode=4624)) AS logon_events BY host
"@
    try {
        $r = Invoke-SplunkQuery -Id 'PF1_hosts' -Spl $pf1 -OutFile 'PF1_hosts.csv' -Columns @('host','sql_audit_events','logon_events')
        Save-Result $r $r.Data      # also opens it in Splunk Web and takes a screenshot (tests the browser step)
        foreach ($h in $Hosts) {
            $hit = $r.Data | Where-Object { $_.host -eq $h } | Select-Object -First 1
            if (-not $hit) { Add-Check "Host $h" 'FAIL' 'no events in 24h: name differs from the Splunk host field (short vs full name?) or not forwarding' }
            elseif ([int]$hit.sql_audit_events -eq 0) { Add-Check "Host $h" 'FAIL' "no SQL audit (33205) events; logon events: $($hit.logon_events)" }
            else { Add-Check "Host $h" 'PASS' "SQL audit events: $($hit.sql_audit_events), logon events: $($hit.logon_events)" }
        }
    } catch { Add-Check 'Host names' 'FAIL' $_.Exception.Message }

    # 2. Field extraction on a sample of in-scope SQL audit events
    $pf2 = $SqlBase + @"
| head 5000
| stats count AS sampled dc(account) AS accounts count(action_id) AS with_action_id count(database_name) AS with_database count(client_host) AS with_client_host count(application_name) AS with_application
"@
    try {
        $r = Invoke-SplunkQuery -Id 'PF2_fields' -Spl $pf2 -OutFile 'PF2_fields.csv' -Columns @('sampled','accounts','with_action_id','with_database','with_client_host','with_application')
        $NoScreenshotSave = $NoScreenshot; $NoScreenshot = $true; Save-Result $r $r.Data; $NoScreenshot = $NoScreenshotSave
        $x = $r.Data | Select-Object -First 1
        if (-not $x -or [int]$x.sampled -eq 0) { Add-Check 'Field extraction' 'FAIL' 'no in-scope events: check in_scope_databases names in server_sets.csv' }
        else {
            $ok = ([int]$x.with_action_id -eq [int]$x.sampled)
            Add-Check 'Field extraction' $(if ($ok) { 'PASS' } else { 'FAIL' }) ("sampled {0} events, {1} accounts; action_id {2}, database {3}, client host {4}, application {5}" -f $x.sampled, $x.accounts, $x.with_action_id, $x.with_database, $x.with_client_host, $x.with_application)
            if ([int]$x.with_client_host -eq 0) { Add-Check 'Client host field' 'WARN' 'not logged by this SQL version: QB rows will show REVIEW; QE carries the evidence' }
        }
    } catch { Add-Check 'Field extraction' 'FAIL' $_.Exception.Message }

    # 3. Splunk Web screenshot (taken in step 1)
    $shotRow = $script:Manifest | Where-Object { $_.query_id -eq 'PF1_hosts' } | Select-Object -First 1
    if ($NoScreenshot) { Add-Check 'Splunk Web screenshot' 'SKIPPED' '-NoScreenshot' }
    elseif ($shotRow -and $shotRow.screenshot_file) { Add-Check 'Splunk Web screenshot' $(if ($script:RunNotes) { 'WARN' } else { 'PASS' }) "open $($shotRow.screenshot_file) and confirm it shows the Splunk search page, maximized" }
    else { Add-Check 'Splunk Web screenshot' 'FAIL' 'no screenshot taken' }

    # 4. Excel can open the template
    if ($WorkbookTemplate) {
        $xlT = $null
        try {
            $xlT = New-Object -ComObject Excel.Application; $xlT.Visible = $false; $xlT.DisplayAlerts = $false
            $wbT = $xlT.Workbooks.Open((Resolve-Path $WorkbookTemplate).Path, 0, $true)
            $tabsOk = @('1. Accounts Found','2. Log Completeness','3. Account Activity','4. Connections','5. Schema & Permission Changes','6. Activity by Hour','7. Windows Logons','8. Splunk Audit Check','Run Manifest','Inputs') |
                      Where-Object { -not ($wbT.Worksheets | Where-Object Name -eq $_) }
            $wbT.Close($false)
            Add-Check 'Excel + template' $(if (@($tabsOk).Count -eq 0) { 'PASS' } else { 'FAIL' }) $(if (@($tabsOk).Count -eq 0) { 'template opens; all tabs present' } else { "missing tabs: $($tabsOk -join ', ')" })
        } catch { Add-Check 'Excel + template' 'FAIL' $_.Exception.Message }
        finally { if ($xlT) { try { $xlT.Quit() } catch { }; [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xlT) } }
    } else { Add-Check 'Excel + template' 'SKIPPED' 'no -WorkbookTemplate' }

    Write-Banner 'PREFLIGHT RESULTS'
    $pf | Format-Table -AutoSize -Wrap | Out-String -Width 250 | Write-Host
    $pf | Export-Csv -LiteralPath (Join-Path $RunDir 'PREFLIGHT_RESULTS.csv') -NoTypeInformation -Encoding UTF8
    if ($pf | Where-Object { $_.Result -eq 'FAIL' }) { Write-Host 'PREFLIGHT: FIX THE FAIL ITEMS BEFORE THE EVIDENCE RUN.' -ForegroundColor Red }
    else { Write-Host 'PREFLIGHT: READY FOR THE EVIDENCE RUN (check the screenshot in the screenshots folder).' -ForegroundColor Green }
    return
}

# =====================================================================================
# QS: ONE search over the SQL audit events (read once, to keep Splunk compute down).
# Step 1 summarizes every in-scope event once, at a fine grain (account x server x database x client
# x program x action x weekday/weekend x hour; schema/permission changes kept one row per change).
# Blank values are stored as '-' so no event can drop out of the summary (stats skips null keys).
# Step 2 cuts each evidence tab from that summary with appendpipe, inside the same search:
#   TOTAL  total in-scope events (the control total)
#   Q0     events and days with events per SQL server (completeness of the audit data)
#   QP     every account active in scope (the population assessed)
#   QA     activity profile per account
#   QB     connection sources per account; human tools flagged
#   QC     schema / permission / role / ownership / audit changes (one row per change)
#   QD     activity by weekday/weekend and hour per account
# The script only splits the result by its 'section' column into one CSV per tab, and checks that
# Q0, QP, QA, QB and QD each add up to TOTAL (accuracy / completeness reconciliation).
# =====================================================================================
$ChangeCodes = '"CR","AL","DR","G","GWG","R","D","APRL","DPRL","AUSC","IMP","TO"'
$HumanTools  = '(?i)management studio|ssms|sqlcmd|azure data studio|dbeaver|excel|toad|datagrip|powershell|python|linqpad|heidisql'
$qs = $SqlBase + @"
| eval client_host=coalesce(nullif(client_host,""),"-"), client_ip=coalesce(nullif(client_ip,""),"-"), application_name=coalesce(nullif(application_name,""),"-"), database_name=coalesce(nullif(database_name,""),"-"), action_id=coalesce(nullif(action_id,""),"-")
| eval server_set=coalesce(nullif($SetCaseSpl,""),"-")
| eval is_change=if(in(action_id, $ChangeCodes), 1, 0)
| eval human_tool=if(match(application_name, "$HumanTools"), "Y", "N")
| eval day_n=min(floor((_time - $EarliestEpoch) / 86400), $($ExpectedDays - 1))
| eval wd=tonumber(strftime(_time,"%w")), day_type=if(wd>=1 AND wd<=5, "Weekday", "Weekend"), hour=strftime(_time,"%H")
| eval c_time=if(is_change=1, strftime(_time,$TimeFmt), "-"), c_object=if(is_change=1, coalesce(object_name,""), "-"), c_class=if(is_change=1, coalesce(class_type,""), "-"),
       c_succeeded=if(is_change=1, coalesce(succeeded,""), "-"), c_statement=if(is_change=1, substr(coalesce(statement,""),1,1000), "-")
| stats count AS events min(_time) AS first_t max(_time) AS last_t values(day_n) AS days
        BY account server_set sql_server database_name db_in_scope client_host client_ip application_name action_id is_change human_tool day_type hour c_time c_object c_class c_succeeded c_statement
| appendpipe [ where isnull(section) | stats sum(events) AS events | eval section="TOTAL" ]
| appendpipe [ where isnull(section) | stats sum(events) AS events dc(days) AS days_with_events min(days) AS first_day_n max(days) AS last_day_n BY sql_server
               | rename sql_server AS host | eval section="Q0" ]
| appendpipe [ where isnull(section) | eval db=if(database_name="-", null(), database_name)
               | stats sum(events) AS events sum(eval(if(is_change=1, events, 0))) AS change_actions values(server_set) AS server_sets values(sql_server) AS sql_servers values(db) AS databases min(first_t) AS first_t max(last_t) AS last_t BY account
               | eval server_sets=mvjoin(server_sets,"; "), sql_servers=mvjoin(sql_servers,"; "), databases=mvjoin(databases,"; "), first_seen=strftime(first_t,$TimeFmt), last_seen=strftime(last_t,$TimeFmt), section="QP" ]
| appendpipe [ where isnull(section) | eval db=if(database_name="-", null(), database_name), ch=if(client_host="-", null(), client_host), ci=if(client_ip="-", null(), client_ip), app=if(application_name="-", null(), application_name)
               | stats sum(events) AS events sum(eval(if(action_id="LGIS", events, 0))) AS logins_succeeded sum(eval(if(action_id="LGIF", events, 0))) AS logins_failed
                       values(sql_server) AS sql_servers values(db) AS databases values(ch) AS client_hosts values(ci) AS client_ips values(app) AS applications values(action_id) AS action_ids min(first_t) AS first_t max(last_t) AS last_t BY account
               | eval sql_servers=mvjoin(sql_servers,"; "), databases=mvjoin(databases,"; "), client_hosts=mvjoin(client_hosts,"; "), client_ips=mvjoin(client_ips,"; "),
                      applications=mvjoin(applications,"; "), action_ids=mvjoin(action_ids,"; "), first_seen=strftime(first_t,$TimeFmt), last_seen=strftime(last_t,$TimeFmt), section="QA" ]
| appendpipe [ where isnull(section) | stats sum(events) AS events min(first_t) AS first_t max(last_t) AS last_t BY account sql_server database_name db_in_scope client_host client_ip application_name human_tool
               | eval result=case(human_tool="Y", "EXCEPTION: human tool", client_host="-" AND client_ip="-", "REVIEW: client not logged", true(), "OK")
               | eval first_seen=strftime(first_t,$TimeFmt), last_seen=strftime(last_t,$TimeFmt), section="QB"
               | rename database_name AS database, application_name AS application ]
| appendpipe [ where isnull(section) AND is_change=1 | stats sum(events) AS events BY c_time account sql_server database_name db_in_scope action_id c_class c_object c_succeeded c_statement
               | rename c_time AS time, database_name AS database, c_class AS class_type, c_object AS object_name, c_succeeded AS succeeded, c_statement AS statement
               | eval result="EXCEPTION", section="QC" ]
| appendpipe [ where isnull(section) | stats sum(events) AS events BY account day_type hour
               | eval business_hours=if(day_type="Weekday" AND tonumber(hour)>=8 AND tonumber(hour)<18, "Y", "N"), section="QD" ]
| where isnotnull(section)
| table section account host server_set server_sets events days_with_events first_day_n last_day_n change_actions sql_server sql_servers database databases db_in_scope
        client_host client_hosts client_ip client_ips application applications action_id action_ids logins_succeeded logins_failed human_tool
        time class_type object_name succeeded statement day_type hour business_hours first_seen last_seen result
"@
$qsCols = @('section','account','host','server_set','server_sets','events','days_with_events','first_day_n','last_day_n','change_actions','sql_server','sql_servers',
            'database','databases','db_in_scope','client_host','client_hosts','client_ip','client_ips','application','applications','action_id','action_ids',
            'logins_succeeded','logins_failed','human_tool','time','class_type','object_name','succeeded','statement','day_type','hour','business_hours',
            'first_seen','last_seen','result')
$rS = Invoke-SplunkQuery -Id 'QS' -Spl $qs -OutFile 'QS_SqlAudit_AllSections.csv' -Columns $qsCols `
      -PostProcessing 'Combined search: split by section into Q0/QP/QA/QB/QC/QD CSVs; sections reconciled to TOTAL.'
Save-Result $rS $rS.Data
$sec = @{}
foreach ($k in 'TOTAL','Q0','QP','QA','QB','QC','QD') { $sec[$k] = @($rS.Data | Where-Object { $_.section -eq $k }) }

# Q0: add in-scope servers with no events, server_set, expected days, dates and the gap flag
$q0data = foreach ($sv in $ServerSets | Sort-Object host, server_set -Unique) {
    $hit = $sec['Q0'] | Where-Object { $_.host -eq $sv.host } | Select-Object -First 1
    $days = if ($hit) { [int]$hit.days_with_events } else { 0 }
    [pscustomobject][ordered]@{
        host = $sv.host; server_set = $sv.server_set
        events = $(if ($hit) { $hit.events } else { 0 })
        days_with_events = $days; expected_days = $ExpectedDays
        first_event_day = $(if ($hit) { $PeriodStart.AddDays([int]$hit.first_day_n).ToString('yyyy-MM-dd') } else { '' })
        last_event_day  = $(if ($hit) { $PeriodStart.AddDays([int]$hit.last_day_n).ToString('yyyy-MM-dd') } else { '' })
        result = $(if ($days -eq 0) { 'EXCEPTION: no events' } elseif ($days -lt $ExpectedDays) { 'EXCEPTION: missing days' } else { 'OK' })
    }
}
Write-Host '    Split by section:'
Save-Derived 'QS' 'Q0' 'Q0_Completeness.csv' @('host','server_set','events','days_with_events','expected_days','first_event_day','last_event_day','result') @($q0data) `
    'Rows where section=Q0, plus in-scope servers with no events (0); server_set, expected_days, dates (from day numbers) and result added by the script'
Save-Derived 'QS' 'QP' 'QP_Population.csv' @('account','server_sets','events','change_actions','sql_servers','databases','first_seen','last_seen') $sec['QP'] ''
Save-Derived 'QS' 'QA' 'QA_Profile.csv' @('account','events','logins_succeeded','logins_failed','sql_servers','databases','client_hosts','client_ips','applications','action_ids','first_seen','last_seen') $sec['QA'] ''
Save-Derived 'QS' 'QB' 'QB_Connections.csv' @('account','sql_server','database','db_in_scope','client_host','client_ip','application','events','first_seen','last_seen','human_tool','result') $sec['QB'] ''
Save-Derived 'QS' 'QC' 'QC_Changes.csv' @('time','account','sql_server','database','db_in_scope','action_id','class_type','object_name','succeeded','statement','result','events') $sec['QC'] ''
Save-Derived 'QS' 'QD' 'QD_Pattern.csv' @('account','day_type','hour','business_hours','events') $sec['QD'] ''

# Accuracy / completeness: every section must add up to the same control total
$total = if ($sec['TOTAL'].Count) { [int64]$sec['TOTAL'][0].events } else { -1 }
$recon = foreach ($k in 'Q0','QP','QA','QB','QD') {
    $sum = [int64](($sec[$k] | Measure-Object -Property events -Sum).Sum)
    [pscustomobject]@{ section = $k; events = $sum; matches_total = ($sum -eq $total) }
}
$qcSum = [int64](($sec['QC'] | Measure-Object -Property events -Sum).Sum)
$qpChanges = [int64](($sec['QP'] | Measure-Object -Property change_actions -Sum).Sum)
$reconOk = (-not ($recon | Where-Object { -not $_.matches_total })) -and ($qcSum -eq $qpChanges)
$reconText = "TOTAL in-scope events $total; " + (($recon | ForEach-Object { "{0}={1}" -f $_.section, $_.events }) -join ', ') +
             "; changes QC=$qcSum vs QP change_actions=$qpChanges" + $(if ($reconOk) { ' - all match' } else { ' - MISMATCH' })
Write-Host ("    Reconciliation: {0}" -f $reconText) -ForegroundColor $(if ($reconOk) { 'Green' } else { 'Red' })
($script:Manifest | Where-Object { $_.query_id -eq 'QS' }).post_processing += " Reconciliation: $reconText"
if (-not $reconOk) { $script:RunFailed = $true }

$rP = [pscustomobject]@{ Data = $sec['QP'] }
if (@($rP.Data).Count -eq 0) { throw 'No accounts found in scope. Check host names in server_sets.csv against Q0 and the in-scope databases.' }
$banner['Accounts discovered (QP)'] = @($rP.Data).Count
$banner['Reconciliation'] = $reconText
Write-Host ("    Accounts discovered: {0}" -f @($rP.Data).Count)

# Windows logons (QE) are matched on the user name without the domain (Windows logs DOMAIN separately).
# Built-in Windows identities (NT AUTHORITY\SYSTEM, NT SERVICE\..., BUILTIN\...) are skipped: their bare names
# (e.g. 'system') would match large numbers of unrelated logons. Every skipped account is printed and recorded.
$AdNames = @(); $QeSkipped = @()
foreach ($acct in @($rP.Data | ForEach-Object { [string]$_.account })) {
    if ($acct -match '^(nt authority|nt service|builtin|iis apppool|window manager|font driver host)\\') { $QeSkipped += "$acct (built-in Windows identity)" }
    elseif ($acct -match '\\([^\\]+)$' -and $Matches[1] -notmatch '\$$') { $AdNames += $Matches[1].ToLower() }
    else { $QeSkipped += "$acct (SQL login or computer account: no Windows logon check)" }
}
$AdNames = @($AdNames | Select-Object -Unique)
Write-Host ("    Windows logon check (QE) will cover {0} account name(s); not covered: {1}" -f $AdNames.Count, $QeSkipped.Count)
foreach ($k in $QeSkipped) { Write-Host "      not covered by QE: $k" }
$AdSpl   = ConvertTo-SplList $AdNames
$AdTerms = if ($AdNames.Count) { '(' + (($AdNames | ForEach-Object { ConvertTo-SplString $_ }) -join ' OR ') + ')' } else { '"__none__"' }

# ---- QE Windows logons (EventCode 4624) on the in-scope SQL servers by the discovered accounts, interactive types flagged.
#      Windows logs the user name without the domain, so the name after DOMAIN\ is used (text only, no AD lookup).
$qe = @"
search index=$WinEventIndex source IN ("WinEventLog:Security","XmlWinEventLog:Security") EventCode=4624 host IN ($HostsSpl) $AdTerms
| eval account=lower(coalesce(TargetUserName, mvindex(Account_Name,-1)))
| eval account_domain=coalesce(TargetDomainName, mvindex(Account_Domain,-1), "")
| eval account=replace(account, "^.*\\\\", "")
| where in(account, $AdSpl)
| eval logon_type=coalesce(Logon_Type, LogonType, "unknown"), target_host=coalesce(ComputerName, Computer, host),
       source_workstation=coalesce(Workstation_Name, WorkstationName, ""), source_ip=coalesce(Source_Network_Address, IpAddress, "")
| stats count AS events min(_time) AS first_t max(_time) AS last_t BY account account_domain logon_type target_host source_workstation source_ip
| eval logon_type_name=case(logon_type="2","Interactive (console)", logon_type="3","Network", logon_type="4","Batch", logon_type="5","Service",
                            logon_type="7","Unlock", logon_type="8","NetworkCleartext", logon_type="9","NewCredentials",
                            logon_type="10","RemoteInteractive (RDP)", logon_type="11","CachedInteractive", true(),"Other")
| eval result=case(in(logon_type,"2","7","10","11"), "EXCEPTION: interactive logon", logon_type="unknown", "REVIEW: logon type not extracted", true(), "OK")
| eval first_seen=strftime(first_t,$TimeFmt), last_seen=strftime(last_t,$TimeFmt)
| table account logon_type logon_type_name target_host source_workstation source_ip events first_seen last_seen result account_domain
"@
$qeNote = "Names matched: {0}. Not covered by QE ({1}): {2}" -f $AdNames.Count, $QeSkipped.Count, ($QeSkipped -join '; ')
$rE = Invoke-SplunkQuery -Id 'QE' -Spl $qe -OutFile 'QE_WinLogons.csv' -PostProcessing $qeNote `
      -Columns @('account','logon_type','logon_type_name','target_host','source_workstation','source_ip','events','first_seen','last_seen','result','account_domain')
Save-Result $rE $rE.Data

# ---- Q_AUDIT: Splunk's own record of the searches above (independent verification)
Write-Host ''
Write-Host "Waiting $AuditIndexWaitSeconds seconds for Splunk to index the search audit records..."
Wait-Seconds $AuditIndexWaitSeconds
$sids = @($script:Manifest | Where-Object { $_.splunk_sid } | ForEach-Object { $_.splunk_sid } | Select-Object -Unique)
$sidSpl = ConvertTo-SplList $sids
$qAudit = @"
search index=_audit action=search info=completed
| eval sid=trim(search_id, "'")
| where in(sid, $sidSpl)
| eval time=strftime(_time,$TimeFmt)
| table time user sid event_count result_count total_run_time search
"@
try {
    $saveEarliest = $EarliestEpoch; $saveLatest = $LatestEpoch
    $EarliestEpoch = [int64]([DateTimeOffset]$RunStart.AddMinutes(-5)).ToUnixTimeSeconds()
    $LatestEpoch   = [int64]([DateTimeOffset](Get-Date).AddMinutes(5)).ToUnixTimeSeconds()
    $rAudit = Invoke-SplunkQuery -Id 'Q_AUDIT' -Spl $qAudit -OutFile 'Q_AUDIT.csv' `
              -Columns @('time','user','sid','event_count','result_count','total_run_time','search')
    Save-Result $rAudit $rAudit.Data
    # Reconcile each SID: found in _audit, and Splunk's recorded result_count equals what the script received
    foreach ($m in $script:Manifest) {
        if (-not $m.splunk_sid -or $m.query_id -eq 'Q_AUDIT' -or $m.source_query -ne $m.query_id) { continue }
        $hit = $rAudit.Data | Where-Object { $_.sid -eq $m.splunk_sid } | Select-Object -First 1
        $m.audit_check = if (-not $hit) { 'NOT FOUND in _audit (re-run Q_AUDIT later if indexing was delayed)' }
                         elseif ([int]$hit.result_count -eq [int]$m.splunk_resultcount) { 'OK' }
                         else { "RESULT COUNT DIFFERS (_audit $($hit.result_count))" }
        if ($m.audit_check -ne 'OK') { $script:RunNotes = $true }
        Write-Host ("    {0} {1}: {2}" -f $m.query_id, $m.splunk_sid, $m.audit_check)
    }
    foreach ($m in $script:Manifest | Where-Object { $_.source_query -ne $_.query_id }) {
        $m.audit_check = ($script:Manifest | Where-Object { $_.query_id -eq $m.source_query } | Select-Object -First 1).audit_check
    }
} catch {
    Write-Host "    Q_AUDIT failed (you may not have access to index=_audit): $($_.Exception.Message)" -ForegroundColor Yellow
    Add-FailedStep 'Q_AUDIT' "Q_AUDIT failed: $($_.Exception.Message)"
} finally {
    $EarliestEpoch = $saveEarliest; $LatestEpoch = $saveLatest
}

} catch {
    Write-Host "RUN STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    Add-FailedStep 'RUN' "Run stopped: $($_.Exception.Message)"
} finally {
# ------------------------------------------------------------------------------ manifest
$runEnd = Get-Date
$overall = if ($script:RunFailed) { 'FAILED - do not use as evidence; see status / splunk_issues columns' }
           elseif ($script:RunNotes) { 'OK WITH NOTES - see audit_check column; explain or re-run Q_AUDIT' } else { 'OK' }
$manifestCsv  = Join-Path $RunDir 'RunManifest.csv'
$manifestJson = Join-Path $RunDir 'RunManifest.json'
$script:Manifest | Export-Csv -LiteralPath $manifestCsv -NoTypeInformation -Encoding UTF8
[ordered]@{
    run = $banner; overall_status = $overall
    run_finished_local = $runEnd.ToString('yyyy-MM-dd HH:mm:ss zzz')
    run_finished_utc   = $runEnd.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss') + 'Z'
    queries = $script:Manifest
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestJson -Encoding UTF8

Write-Banner 'RUN SUMMARY'
$script:Manifest | Format-Table query_id, status, splunk_sid, rows_written, retrieval_check, audit_check, output_sha256 -AutoSize | Out-String -Width 300 | Write-Host
Write-Host ("OVERALL STATUS       : {0}" -f $overall) -ForegroundColor $(if ($script:RunFailed) { 'Red' } else { 'Green' })
Write-Host ("Script SHA256        : {0}" -f $ScriptHash)
Write-Host ("server_sets.csv SHA256: {0}" -f (Get-Sha256 $ServerSetsPath))
Write-Host ("RunManifest.csv SHA256: {0}" -f (Get-Sha256 $manifestCsv))
Write-Host ("Run finished         : {0}  /  {1}Z" -f $runEnd.ToString('yyyy-MM-dd HH:mm:ss zzz'), $runEnd.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))
Write-Host ("Get-Date             : {0}" -f (Get-Date -Format 'dddd, MMMM d, yyyy h:mm:ss tt K'))
Write-Host ''
if (-not $NoScreenshot) {
    Write-Host 'Run summary screenshot in 5 seconds. Take your own screenshot at the very end, after the SHA256SUMS line.' -ForegroundColor Green
    Start-Sleep -Seconds 5
}

# ------------------------------------------------------------------------------ screenshot
if (-not $NoScreenshot) {
    try {
        # Bring this console back in front of the browser before capturing the RUN SUMMARY
        $back = $false
        try { $back = (New-Object -ComObject WScript.Shell).AppActivate("SvcAcctEvidence_$RunId") } catch { }
        if (-not $back) { Write-Host 'Click this window now so the summary screenshot shows it.' -ForegroundColor Yellow }
        Start-Sleep -Seconds 3
        $h = Save-Screenshot (Join-Path $RunDir 'Screenshot.png')
        Write-Host "Run summary screenshot saved: Screenshot.png  SHA256 $h"
    } catch {
        Write-Host "Automatic screenshot failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# ------------------------------------------------------------------------------ workbook
$ranQueries = @($script:Manifest | Where-Object { $_.splunk_sid }).Count -gt 0
if ($WorkbookTemplate -and $ranQueries -and -not $Preflight) {
    Write-Host ''
    Write-Host 'Building the workbook in Excel (do not use Excel until this finishes)...'
    try { Build-Workbook } catch {
        Write-Host "Workbook build failed: $($_.Exception.Message). The CSV evidence is unaffected; paste it manually if needed." -ForegroundColor Yellow
    }
}

Disable-KeepAwake
Stop-Transcript | Out-Null

# Hash every file in the run folder (including transcript and screenshot) into SHA256SUMS.txt.
# Its hash is printed last, so your manual screenshot ties to every file.
$sumsFile = Join-Path $RunDir 'SHA256SUMS.txt'
$sums = Get-ChildItem -LiteralPath $RunDir -Recurse -File | Where-Object { $_.FullName -ne $sumsFile } | Sort-Object FullName | ForEach-Object {
    "{0}  {1}" -f (Get-Sha256 $_.FullName), $_.FullName.Substring($RunDir.Length + 1)
}
[IO.File]::WriteAllLines($sumsFile, [string[]]$sums, $Utf8NoBom)
Write-Host ''
Write-Host ("SHA256SUMS.txt SHA256: {0}" -f (Get-Sha256 $sumsFile)) -ForegroundColor Cyan
Write-Host ("OVERALL STATUS       : {0}" -f $overall) -ForegroundColor $(if ($script:RunFailed) { 'Red' } else { 'Green' })
Write-Host ("Get-Date             : {0}" -f (Get-Date -Format 'dddd, MMMM d, yyyy h:mm:ss tt K'))
Write-Host 'TAKE YOUR FULL-SCREEN SCREENSHOT NOW (include the taskbar clock).' -ForegroundColor Green
}
