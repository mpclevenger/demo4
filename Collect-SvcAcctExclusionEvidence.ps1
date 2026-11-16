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
      QD_Pattern.csv        activity by weekday and hour
      QE_WinLogons.csv      Windows logons by the accounts, interactive ones flagged
      Q_AUDIT.csv           Splunk's own record of the searches above
      queries\*.spl         exact query text sent to Splunk
      RunManifest.csv/.json hashes, parameters, SIDs, row counts
      screenshots\*.png     Splunk Web showing each search (query text, time range, results)
      Screenshot.png        screen capture of the RUN SUMMARY
      SvcAcct_Exclusion_Evidence_<RunId>.xlsx   the workbook, filled in by this script
      Transcript.txt        full console log
      SHA256SUMS.txt        SHA256 of every file above

    Normally started from Run-Evidence.ps1, which holds the settings (URLs, dates, approved hash).

.PARAMETER SplunkBaseUrl
    Splunk REST endpoint, e.g. https://yourcompany.splunkcloud.com:8089

.PARAMETER SplunkWebUrl
    Splunk Web address used in the browser, e.g. https://yourcompany.splunkcloud.com
    Each finished search is opened there and screenshotted.

.PARAMETER WorkbookTemplate
    Path to SvcAcct_Exclusion_Evidence_TEMPLATE.xlsx. The script opens it in Excel (desktop
    Excel required), fills in every Splunk tab and the run details, and saves a new workbook
    in the run folder. The template itself is not changed. Skipped if omitted.

.PARAMETER WinEventIndex
    Index holding WinEventLog:Security (SQL audit EventCode 33205 and logon EventCode 4624).

.PARAMETER ServerSetsCsv
    Input file: server_set, host, in_scope_databases. See the Inputs tab of the workbook.

.PARAMETER StartDate / EndDate
    Review period, inclusive, in this computer's local time zone (yyyy-MM-dd).

.PARAMETER ApprovedSha256
    Optional. The approved hash of this script (from the workbook's Run Manifest tab).
    If given, the banner shows MATCH or MISMATCH.


.EXAMPLE
    .\Collect-SvcAcctExclusionEvidence.ps1 -SplunkBaseUrl https://acme.splunkcloud.com:8089 `
        -WinEventIndex wineventlog -ServerSetsCsv .\server_sets.csv `
        -StartDate 2026-09-01 -EndDate 2026-11-13 -ApprovedSha256 <hash>
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $SplunkBaseUrl,
    [Parameter(Mandatory)] [string] $SplunkWebUrl,
    [Parameter(Mandatory)] [string] $WinEventIndex,
    [Parameter(Mandatory)] [string] $ServerSetsCsv,
    [Parameter(Mandatory)] [datetime] $StartDate,
    [Parameter(Mandatory)] [datetime] $EndDate,
    [string] $ApprovedSha256 = '',
    [string] $OutputRoot = '.',
    [int]    $JobTimeoutSeconds = 3600,
    [int]    $AuditIndexWaitSeconds = 90,
    [string] $WorkbookTemplate = '',
    [int]    $BrowserWaitSeconds = 25,
    [int]    $JobTtlSeconds = 604800,
    [switch] $NoScreenshot
)

$ErrorActionPreference = 'Stop'
$ScriptVersion = '2.0.1'

# =====================================================================================
# REGION: SPLUNK CONNECTION  (the only part that should need changes for your setup;
# compare with your previously working Splunk client and adjust here only)
# =====================================================================================
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:SplunkHeaders = $null

function Connect-Splunk {
    # Token (Bearer) authentication. The token is never written to the transcript or output.
    $secure = Read-Host -AsSecureString -Prompt 'Splunk authentication token'
    $bstr   = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try   { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    $script:SplunkHeaders = @{ Authorization = "Bearer $plain" }
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
        Start-Sleep -Seconds 2
        $found = Get-Process | Where-Object { $_.MainWindowTitle -like '*Search*Splunk*' } | Select-Object -First 1
    } while (-not $found -and (Get-Date) -lt $deadline)
    $activated = $false
    if ($found) {
        try { $activated = (New-Object -ComObject WScript.Shell).AppActivate($found.Id) } catch { }
        Start-Sleep -Seconds 6     # let the results finish rendering
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
        Start-Sleep -Seconds 5
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

function Add-FailedStep([string]$Id, [string]$Message, [string]$Sid = '') {
    $script:RunFailed = $true
    $script:Manifest.Add([pscustomobject][ordered]@{
        query_id = $Id; status = 'FAILED'; splunk_sid = $Sid; started_local = ''; finished_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
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
        @{ Id = 'Q0';      Sheet = 'Q0 Completeness';      Csv = 'Q0_Completeness.csv'; PicCol = 10 },
        @{ Id = 'QP';      Sheet = 'QP Population';        Csv = 'QP_Population.csv';   PicCol = 11 },
        @{ Id = 'QA';      Sheet = 'QA Profile';           Csv = 'QA_Profile.csv';      PicCol = 14 },
        @{ Id = 'QB';      Sheet = 'QB Connections';       Csv = 'QB_Connections.csv';  PicCol = 17 },
        @{ Id = 'QC';      Sheet = 'QC Changes';           Csv = 'QC_Changes.csv';      PicCol = 15 },
        @{ Id = 'QD';      Sheet = 'QD Pattern';           Csv = 'QD_Pattern.csv';      PicCol = 7  },
        @{ Id = 'QE';      Sheet = 'QE Win Logons';        Csv = 'QE_WinLogons.csv';    PicCol = 15 },
        @{ Id = 'Q_AUDIT'; Sheet = 'Q_AUDIT Verification'; Csv = 'Q_AUDIT.csv';         PicCol = 9  }
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
            $ws.Cells.Item(11, 2).Value2 = ("Run {0} | Started {1} | Finished {2} | Splunk SID {3} | Rows: Splunk {4}, written {5} | Status {6} | " +
                "Query SHA256 {7} | Output {8} SHA256 {9} | Splunk screenshot {10} SHA256 {11} | Splunk audit log check: {12}") -f `
                $RunId, $m.started_local, $m.finished_local, $m.splunk_sid, $m.splunk_resultcount, $m.rows_written, $m.status,
                $m.query_sha256, $m.output_file, $m.output_sha256, $m.screenshot_file, $m.screenshot_sha256, $(if ($m.audit_check) { $m.audit_check } else { 'n/a' })
            if ($m.screenshot_file) { Add-Picture $ws (Join-Path $RunDir $m.screenshot_file) 3 $t.PicCol 640 }
        }

        # AD tab (optional)

        # Run Manifest tab
        $ws = $wbk.Worksheets.Item('Run Manifest')
        $cells = @(
            @(6,  $(if ($ApprovedSha256) { $ApprovedSha256.Trim().ToUpper() } else { '' })),
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
            @(22, (Get-Sha256 $manifestCsv))
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
$RunDir     = Join-Path (Resolve-Path $OutputRoot) "SvcAcctEvidence_$RunId"
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
$hashStatus = if (-not $ApprovedSha256) { 'NOT CHECKED (no -ApprovedSha256 given)' }
              elseif ($ApprovedSha256.Trim().ToUpper() -eq $ScriptHash) { 'MATCH' } else { 'MISMATCH' }
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
    'Approved SHA256'        = $(if ($ApprovedSha256) { $ApprovedSha256.ToUpper() } else { '(not given)' })
    'Hash check'             = $hashStatus
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
if ($hashStatus -eq 'MISMATCH') {
    throw 'Script hash does not match the approved hash. Run stopped; nothing was sent to Splunk.'
}
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
| rex field=Message "(?<![a-z_])action_id:(?<action_id>\S*)"
| rex field=Message "(?<![a-z_])succeeded:(?<succeeded>\S*)"
| rex field=Message "(?<![a-z_])class_type:(?<class_type>\S*)"
| rex field=Message "(?<![a-z_])server_principal_name:(?<server_principal_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])database_name:(?<database_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])object_name:(?<object_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])statement:(?<statement>[\s\S]*?)\s+additional_information:"
| rex field=Message "(?<![a-z_])client_ip:(?<client_ip>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])application_name:(?<application_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])host_name:(?<client_host>.*?)(?=\s+[a-z_]+:|$)"
| where isnotnull(server_principal_name) AND server_principal_name!=""
| eval account=lower(server_principal_name), sql_server=host
| eval db_in_scope=case(isnull(database_name) OR database_name="", "Server-level", in(lower(host."|".database_name), __HOSTDB__), "Y", in(action_id,"LGIS","LGIF"), "Login", true(), "N")
| where db_in_scope!="N"
'@
$SqlBase = $SqlBase.Replace('__IDX__', $WinEventIndex).Replace('__HOSTS__', $HostsSpl).Replace('__HOSTDB__', $HostDbSpl) + "`n"
$TimeFmt = '"%Y-%m-%d %H:%M:%S %z"'

# ---- Q0 Completeness: does every in-scope server send audit events every day?
$q0 = @"
search index=$WinEventIndex source="WinEventLog:Security" EventCode=33205 host IN ($HostsSpl)
| eval day_n=min(floor((_time - $EarliestEpoch) / 86400), $($ExpectedDays - 1))
| stats count AS events dc(day_n) AS days_with_events min(day_n) AS first_day_n max(day_n) AS last_day_n BY host
| table host events days_with_events first_day_n last_day_n
"@
$r0 = Invoke-SplunkQuery -Id 'Q0' -Spl $q0 -OutFile 'Q0_Completeness.csv' `
      -Columns @('host','events','days_with_events','first_day_n','last_day_n') `
      -PostProcessing 'Script adds in-scope servers with no events (0), adds server_set and expected_days, converts day numbers to dates, and sets result (OK / missing days / no events).'
$r0.Columns = @('host','server_set','events','days_with_events','expected_days','first_event_day','last_event_day','result')
# Add in-scope servers that returned nothing, and the gap flag
$q0data = foreach ($s in $ServerSets | Sort-Object host, server_set -Unique) {
    $hit = $r0.Data | Where-Object { $_.host -eq $s.host } | Select-Object -First 1
    $days = if ($hit) { [int]$hit.days_with_events } else { 0 }
    [pscustomobject][ordered]@{
        host = $s.host; server_set = $s.server_set
        events = $(if ($hit) { $hit.events } else { 0 })
        days_with_events = $days; expected_days = $ExpectedDays
        first_event_day = $(if ($hit) { $PeriodStart.AddDays([int]$hit.first_day_n).ToString('yyyy-MM-dd') } else { '' })
        last_event_day  = $(if ($hit) { $PeriodStart.AddDays([int]$hit.last_day_n).ToString('yyyy-MM-dd') } else { '' })
        result = $(if ($days -eq 0) { 'EXCEPTION: no events' } elseif ($days -lt $ExpectedDays) { 'EXCEPTION: missing days' } else { 'OK' })
    }
}
Save-Result $r0 @($q0data)

# ---- QP Population: every account active on the in-scope servers and databases in the period.
#      This IS the list of accounts assessed; every later query covers all of them.
$qp = $SqlBase + @"
| eval server_set=$SetCaseSpl
| eval is_change=if(in(action_id,"CR","AL","DR","G","GWG","R","D","APRL","DPRL","AUSC","IMP","TO"),1,0)
| stats count AS events sum(is_change) AS change_actions values(server_set) AS server_sets values(sql_server) AS sql_servers values(database_name) AS databases min(_time) AS first max(_time) AS last BY account
| eval server_sets=mvjoin(server_sets,"; "), sql_servers=mvjoin(sql_servers,"; "), databases=mvjoin(databases,"; "), first_seen=strftime(first,$TimeFmt), last_seen=strftime(last,$TimeFmt)
| sort 0 account
| table account server_sets events change_actions sql_servers databases first_seen last_seen
"@
$rP = Invoke-SplunkQuery -Id 'QP' -Spl $qp -OutFile 'QP_Population.csv' `
      -Columns @('account','server_sets','events','change_actions','sql_servers','databases','first_seen','last_seen')
Save-Result $rP $rP.Data
if (@($rP.Data).Count -eq 0) { throw 'QP found no accounts in scope. Check host names in server_sets.csv against Q0 and the in-scope databases.' }
$banner['Accounts discovered (QP)'] = @($rP.Data).Count
Write-Host ("    Accounts discovered: {0}" -f @($rP.Data).Count)

# Windows logons (QE) are matched on the user name without the domain (Windows logs DOMAIN separately).
# Built from the discovered accounts: DOMAIN\name -> name. Computer accounts (name$) are skipped.
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

# ---- QA Profile: what each account did, overall
$qa = $SqlBase + @"
| stats count AS events count(eval(action_id="LGIS")) AS logins_succeeded count(eval(action_id="LGIF")) AS logins_failed
        values(sql_server) AS sql_servers values(database_name) AS databases values(client_host) AS client_hosts
        values(client_ip) AS client_ips values(application_name) AS applications values(action_id) AS action_ids
        min(_time) AS first max(_time) AS last BY account
| eval sql_servers=mvjoin(sql_servers,"; "), databases=mvjoin(databases,"; "), client_hosts=mvjoin(client_hosts,"; "),
       client_ips=mvjoin(client_ips,"; "), applications=mvjoin(applications,"; "), action_ids=mvjoin(action_ids,"; "),
       first_seen=strftime(first,$TimeFmt), last_seen=strftime(last,$TimeFmt)
| table account events logins_succeeded logins_failed sql_servers databases client_hosts client_ips applications action_ids first_seen last_seen
"@
$colsA = @('account','events','logins_succeeded','logins_failed','sql_servers','databases','client_hosts','client_ips','applications','action_ids','first_seen','last_seen')
$rA = Invoke-SplunkQuery -Id 'QA' -Spl $qa -OutFile 'QA_Profile.csv' -Columns $colsA
Save-Result $rA $rA.Data

# ---- QB Connections: every source each account connected from, flagged
$qb = $SqlBase + @"
| eval client_host=coalesce(client_host,""), client_ip=coalesce(client_ip,""), application_name=coalesce(application_name,""), database_name=coalesce(database_name,"")
| stats count AS events min(_time) AS first max(_time) AS last BY account sql_server database_name db_in_scope client_host client_ip application_name
| eval human_tool=if(match(application_name, "(?i)management studio|ssms|sqlcmd|azure data studio|dbeaver|excel|toad|datagrip|powershell|python|linqpad|heidisql"), "Y", "N")
| eval result=case(human_tool="Y", "EXCEPTION: human tool",
                   client_host="" AND client_ip="", "REVIEW: client not logged",
                   true(), "OK")
| eval first_seen=strftime(first,$TimeFmt), last_seen=strftime(last,$TimeFmt)
| rename database_name AS database, application_name AS application
| table account sql_server database db_in_scope client_host client_ip application events first_seen last_seen human_tool result
"@
$rB = Invoke-SplunkQuery -Id 'QB' -Spl $qb -OutFile 'QB_Connections.csv' `
      -Columns @('account','sql_server','database','db_in_scope','client_host','client_ip','application','events','first_seen','last_seen','human_tool','result')
Save-Result $rB $rB.Data

# ---- QC Changes: anything beyond reading/writing data
# CR create, AL alter, DR drop, G/GWG grant, R revoke, D deny, APRL/DPRL add/drop role member,
# AUSC audit change, IMP impersonate, TO take ownership
$qc = $SqlBase + @"
| search action_id IN ("CR","AL","DR","G","GWG","R","D","APRL","DPRL","AUSC","IMP","TO")
| eval time=strftime(_time,$TimeFmt), statement=substr(statement,1,1000), result="EXCEPTION"
| rename database_name AS database
| sort 0 _time
| table time account sql_server database db_in_scope action_id class_type object_name succeeded statement result
"@
$rC = Invoke-SplunkQuery -Id 'QC' -Spl $qc -OutFile 'QC_Changes.csv' `
      -Columns @('time','account','sql_server','database','db_in_scope','action_id','class_type','object_name','succeeded','statement','result')
Save-Result $rC $rC.Data

# ---- QD Pattern: when each account is active (weekday x hour)
$qd = $SqlBase + @"
| eval weekday=strftime(_time,"%a"), wd=tonumber(strftime(_time,"%w")), hour=strftime(_time,"%H")
| eval business_hours=if(wd>=1 AND wd<=5 AND tonumber(hour)>=8 AND tonumber(hour)<18, "Y", "N")
| stats count AS events BY account weekday wd hour business_hours
| sort 0 account wd hour
| table account weekday hour business_hours events
"@
$rD = Invoke-SplunkQuery -Id 'QD' -Spl $qd -OutFile 'QD_Pattern.csv' -Columns @('account','weekday','hour','business_hours','events')
Save-Result $rD $rD.Data

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
| stats count AS events min(_time) AS first max(_time) AS last BY account account_domain logon_type target_host source_workstation source_ip
| eval logon_type_name=case(logon_type="2","Interactive (console)", logon_type="3","Network", logon_type="4","Batch", logon_type="5","Service",
                            logon_type="7","Unlock", logon_type="8","NetworkCleartext", logon_type="9","NewCredentials",
                            logon_type="10","RemoteInteractive (RDP)", logon_type="11","CachedInteractive", true(),"Other")
| eval result=case(in(logon_type,"2","7","10","11"), "EXCEPTION: interactive logon", logon_type="unknown", "REVIEW: logon type not extracted", true(), "OK")
| eval first_seen=strftime(first,$TimeFmt), last_seen=strftime(last,$TimeFmt)
| table account logon_type logon_type_name target_host source_workstation source_ip events first_seen last_seen result account_domain
"@
$qeNote = "Names matched: {0}. Not covered by QE ({1}): {2}" -f $AdNames.Count, $QeSkipped.Count, ($QeSkipped -join '; ')
$rE = Invoke-SplunkQuery -Id 'QE' -Spl $qe -OutFile 'QE_WinLogons.csv' -PostProcessing $qeNote `
      -Columns @('account','logon_type','logon_type_name','target_host','source_workstation','source_ip','events','first_seen','last_seen','result','account_domain')
Save-Result $rE $rE.Data

# ---- Q_AUDIT: Splunk's own record of the searches above (independent verification)
Write-Host ''
Write-Host "Waiting $AuditIndexWaitSeconds seconds for Splunk to index the search audit records..."
Start-Sleep -Seconds $AuditIndexWaitSeconds
$sids = @($script:Manifest | Where-Object { $_.splunk_sid } | ForEach-Object { $_.splunk_sid })
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
        if (-not $m.splunk_sid -or $m.query_id -eq 'Q_AUDIT') { continue }
        $hit = $rAudit.Data | Where-Object { $_.sid -eq $m.splunk_sid } | Select-Object -First 1
        $m.audit_check = if (-not $hit) { 'NOT FOUND in _audit (re-run Q_AUDIT later if indexing was delayed)' }
                         elseif ([int]$hit.result_count -eq [int]$m.splunk_resultcount) { 'OK' }
                         else { "RESULT COUNT DIFFERS (_audit $($hit.result_count))" }
        if ($m.audit_check -ne 'OK') { $script:RunNotes = $true }
        Write-Host ("    {0} {1}: {2}" -f $m.query_id, $m.splunk_sid, $m.audit_check)
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
    run = $banner; hash_check = $hashStatus; overall_status = $overall
    run_finished_local = $runEnd.ToString('yyyy-MM-dd HH:mm:ss zzz')
    run_finished_utc   = $runEnd.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss') + 'Z'
    queries = $script:Manifest
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestJson -Encoding UTF8

Write-Banner 'RUN SUMMARY'
$script:Manifest | Format-Table query_id, status, splunk_sid, rows_written, retrieval_check, audit_check, output_sha256 -AutoSize | Out-String -Width 300 | Write-Host
Write-Host ("OVERALL STATUS       : {0}" -f $overall) -ForegroundColor $(if ($script:RunFailed) { 'Red' } else { 'Green' })
Write-Host ("Script SHA256        : {0}  ({1})" -f $ScriptHash, $hashStatus)
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
if ($WorkbookTemplate -and $ranQueries) {
    Write-Host ''
    Write-Host 'Building the workbook in Excel (do not use Excel until this finishes)...'
    try { Build-Workbook } catch {
        Write-Host "Workbook build failed: $($_.Exception.Message). The CSV evidence is unaffected; paste it manually if needed." -ForegroundColor Yellow
    }
}

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
