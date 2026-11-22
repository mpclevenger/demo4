<#
.SYNOPSIS
    Collects Splunk evidence for the assessment of service accounts (non-human identities) for
    exclusion from the Database Change Review population, and builds the assessment workbook.

.DESCRIPTION
    HOW TO RUN
      Keep in one folder: this script, server_sets.csv (in-scope SQL servers and databases) and
      SvcAcct_Exclusion_Assessment_TEMPLATE.xlsx. Edit the SETTINGS in the param block below, then:
        .\Collect-SvcAcctExclusionEvidence.ps1 -Preflight   quick check that everything works (not evidence)
        .\Collect-SvcAcctExclusionEvidence.ps1 -Discover    STEP 1: find the accounts, look them up in AD
            -> open SvcAcct_Exclusion_Assessment_<RunId>.xlsx in the new SvcAcctDISCOVERY_ folder, set the
               Classification for every account, save it, and put its path in $Workbook below
        .\Collect-SvcAcctExclusionEvidence.ps1              STEP 2: assess the accounts classified 'Service account'
            -> the finished workbook is in the new SvcAcctEvidence_ folder
      If Windows blocks the script, use: powershell -ExecutionPolicy Bypass -File .\Collect-SvcAcctExclusionEvidence.ps1
      The Splunk token is read from the SPLUNK_TOKEN environment variable; it is never prompted for or logged.
      Do not touch the keyboard or mouse until the run prints RUN FINISHED (screenshots are automatic).

    WHAT IT DOES
      Every Splunk query is written in full inside this script (no Splunk macros or lookups), so the
      script's SHA256 hash covers the exact logic and settings that ran. Each run saves a copy of this
      script, the query text, the results, screenshots, a transcript and SHA256SUMS.txt in its own folder.
      Step 1 creates the workbook from the template; step 2 adds one tab per service account, the
      Leadsheet summary and the Step 2 part of Run Details. Nothing is changed in Splunk, Active
      Directory or the SQL servers: every call is a read or a search.
      Searches run one at a time (the Splunk account allows two concurrent searches).
#>
[CmdletBinding()]
param(
    # ===================================== SETTINGS: edit these =====================================
    [datetime]  $StartDate     = '2026-09-01',                               # review period start (inclusive)
    [datetime]  $EndDate       = '2026-11-13',                               # review period end (inclusive)
    [string]    $SplunkBaseUrl = 'https://yourcompany.splunkcloud.com:8089', # Splunk REST API address
    [string]    $SplunkWebUrl  = 'https://yourcompany.splunkcloud.com',      # Splunk address in the browser
    [string]    $WinEventIndex = 'wineventlog',                              # index holding WinEventLog:Security
    [hashtable] $AdServers     = @{ 'CORP' = 'corp.company.com' },           # domain prefix in account names -> Get-ADUser -Server
    [string]    $Workbook      = '',                                         # STEP 2 only: the classified workbook from step 1
    # ================================ do not edit below this line ===================================
    [switch] $Preflight,
    [switch] $Discover,
    [string] $ServerSetsCsv = (Join-Path $PSScriptRoot 'server_sets.csv'),
    [string] $WorkbookTemplate = (Join-Path $PSScriptRoot 'SvcAcct_Exclusion_Assessment_TEMPLATE.xlsx'),
    [string] $OutputRoot = $PSScriptRoot,
    [int]    $JobTimeoutSeconds = 3600,
    [int]    $AuditIndexWaitSeconds = 90,
    [int]    $BrowserWaitSeconds = 25,
    [int]    $JobTtlSeconds = 0,
    [switch] $NoScreenshot
)

$ErrorActionPreference = 'Stop'
$ScriptVersion = '4.2.0'

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

    # Splunk keeps a finished search for about 10 minutes by default, long enough for the screenshot.
    # -JobTtlSeconds > 0 keeps it longer (off by default: searches are not revisited after the run).
    $ttlSet = 'N'
    if ($JobTtlSeconds -gt 0) { try { Invoke-Splunk -Method Post -Path "/services/search/jobs/$sid/control" -Body @{ action = 'setttl'; ttl = $JobTtlSeconds } | Out-Null; $ttlSet = "Y ($JobTtlSeconds s)" }
    catch { Write-Host "    Could not extend job lifetime: $($_.Exception.Message)" -ForegroundColor Yellow } }

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
# Values are written as text, except whole-number count columns, so Excel cannot re-interpret them
# (dates, leading '=', '1e5' and so on).
$NumericCols = @('events','logins_succeeded','logins_failed','days_with_events','expected_days','change_actions','spn_count','rows_written','weekday_events','weekend_events')
$Disp = @{
    account='Account'; server_sets='Server sets'; server_set='Server set'; sql_servers='SQL servers'; sql_server='SQL server'; events='Events'
    first_seen='First seen'; last_seen='Last seen'; ad_lookup='AD lookup'; domain='Domain'; ad_server='AD server queried'; sam_account_name='SAM account name'
    given_name='First name'; surname='Last name'; display_name='Display name'; description='Description'; enabled='Enabled'; employee_id='Employee ID'
    title='Title'; department='Department'; manager='Manager'; spn_count='SPNs'; password_never_expires='Password never expires'; when_created='Created'
    suggested_type='Suggested type'; classification='Classification'; notes='Notes'
    logon_type='Logon type'; logon_type_name='Logon type name'; target_host='Server'; source_workstation='Source workstation'; source_ip='Source IP'
    result='Result'; account_domain='Logon domain'; database='Database'; db_in_scope='In scope'; client_host='Client host'; client_ip='Client IP'
    application='Application'; interactive_tool='Interactive tool'; time='Time'; action_id='Action'; class_type='Object type'; object_name='Object'
    succeeded='Succeeded'; statement='Statement'; host='SQL server'; days_with_events='Days with events'; expected_days='Days in period'
    first_event_day='First day'; last_event_day='Last day'; query_id='Step'; search='Search'; status='Status'; splunk_sid='Splunk search ID'; started_local='Started'
    finished_local='Finished'; rows_written='Rows'; retrieval_check='All results received'; audit_check='Confirmed in Splunk audit log'; query_sha256='Query SHA256'
    output_file='Output file'; output_sha256='Output SHA256'; in_scope_databases='In-scope databases'
    hour='Hour'; weekday_events='Weekday events'; weekend_events='Weekend events'
}
function Get-Disp([string]$c) { if ($Disp.ContainsKey($c)) { $Disp[$c] } else { $c } }

$ClrLavender = 15523812; $ClrSection = 15917529; $ClrHeader = 6567967; $ClrWhite = 16777215
$ClrNote = 4210752; $ClrBorder = 10921638; $ClrLabel = 15921906
$xlTop = -4160; $xlLeft = -4131; $xlCenter = -4108

function Set-Cell($Sheet, [int]$Row, [int]$Col, $Value) {
    $c = $Sheet.Cells.Item($Row, $Col)
    if ($Value -is [int] -or $Value -is [int64] -or $Value -is [double]) { $c.NumberFormat = '0'; $c.Value2 = [double]$Value }
    else { $c.NumberFormat = '@'; $c.Value2 = [string]$Value }
}

# One line of text. -Span > 1 merges the cells across and wraps, with the row height set to fit.
function Write-Text($Sheet, [int]$Row, [string]$Text, [int]$Col = 1, [int]$Span = 8, [switch]$Bold, [switch]$Note, [switch]$Section) {
    Set-Cell $Sheet $Row $Col $Text
    $rng = $Sheet.Range($Sheet.Cells.Item($Row, $Col), $Sheet.Cells.Item($Row, $Col + [Math]::Max($Span, 1) - 1))
    if ($Span -gt 1) {
        [void]$rng.Merge(); $rng.WrapText = $true; $rng.VerticalAlignment = $xlTop; $rng.HorizontalAlignment = $xlLeft
        $perLine = [Math]::Max(20, [int]([double]$rng.Width / 5.6))
        $lines = [Math]::Max(1, [Math]::Ceiling($Text.Length / $perLine))
        $Sheet.Rows.Item($Row).RowHeight = 13.5 * $lines
    }
    if ($Bold -or $Section) { $rng.Font.Bold = $true }
    if ($Note) { $rng.Font.Color = $ClrNote }
    if ($Section) { $rng.Interior.Color = $ClrSection }
    return ($Row + 1)
}

# Label / value rows: label in column A, value merged across B..LastCol.
function Write-Pairs($Sheet, [int]$Row, [object[]]$Pairs, [int]$LastCol = 8) {
    foreach ($p in $Pairs) {
        $l = $Sheet.Cells.Item($Row, 1)
        Set-Cell $Sheet $Row 1 $p[0]; $l.Font.Bold = $true; $l.Interior.Color = $ClrLabel; $l.VerticalAlignment = $xlTop
        $null = Write-Text $Sheet $Row ([string]$p[1]) -Col 2 -Span ($LastCol - 1)
        $Sheet.Range($Sheet.Cells.Item($Row, 1), $Sheet.Cells.Item($Row, $LastCol)).Borders.Color = $ClrBorder
        $Row++
    }
    return $Row
}

# A table from objects. Header names come from $Disp. Returns the next free row.
function Write-Table($Sheet, [int]$Row, [object[]]$Rows, [string[]]$Columns, [int]$Col = 1) {
    $data = @($Rows | Where-Object { $null -ne $_ })
    $n = $data.Count + 1; $m = $Columns.Count
    $isNum = @(for ($j = 0; $j -lt $m; $j++) {
        $c = $Columns[$j]
        ($c -in $NumericCols) -and (@($data | Where-Object { [string]$_.$c -notmatch '^-?\d{1,15}$' }).Count -eq 0)
    })
    $arr = New-Object 'object[,]' $n, $m
    for ($j = 0; $j -lt $m; $j++) { $arr[0, $j] = [string](Get-Disp $Columns[$j]) }
    for ($i = 0; $i -lt $data.Count; $i++) {
        for ($j = 0; $j -lt $m; $j++) {
            $v = [string]$data[$i].($Columns[$j])
            if ($isNum[$j]) { $arr[($i + 1), $j] = [double]$v } else { $arr[($i + 1), $j] = $v }
        }
    }
    for ($j = 0; $j -lt $m; $j++) {
        $Sheet.Range($Sheet.Cells.Item($Row, $Col + $j), $Sheet.Cells.Item($Row + $n - 1, $Col + $j)).NumberFormat = $(if ($isNum[$j]) { '0' } else { '@' })
    }
    $rng = $Sheet.Range($Sheet.Cells.Item($Row, $Col), $Sheet.Cells.Item($Row + $n - 1, $Col + $m - 1))
    $rng.Value2 = $arr
    $rng.Borders.LineStyle = 1; $rng.Borders.Color = $ClrBorder; $rng.VerticalAlignment = $xlTop
    $hdr = $Sheet.Range($Sheet.Cells.Item($Row, $Col), $Sheet.Cells.Item($Row, $Col + $m - 1))
    $hdr.Font.Bold = $true; $hdr.Font.Color = $ClrWhite; $hdr.Interior.Color = $ClrHeader; $hdr.WrapText = $true
    if ($data.Count -eq 0) {
        $null = Write-Text $Sheet ($Row + 1) 'None found in the review period.' -Col $Col -Span 1 -Note
        return ($Row + 2)
    }
    return ($Row + $n)
}

# A lavender area where the control owner pastes or references evidence. Returns the next free row.
function Write-AttachBox($Sheet, [int]$Row, [string]$Label, [int]$Height = 6) {
    $Row = Write-Text $Sheet $Row $Label -Bold
    $rng = $Sheet.Range($Sheet.Cells.Item($Row, 1), $Sheet.Cells.Item($Row + $Height - 1, 8))
    $rng.Interior.Color = $ClrLavender
    foreach ($b in 7, 8, 9, 10) { $rng.Borders.Item($b).LineStyle = 1; $rng.Borders.Item($b).Color = $ClrBorder }   # outline only
    Set-Cell $Sheet $Row 1 'Paste or reference the evidence here.'
    $Sheet.Cells.Item($Row, 1).Font.Color = $ClrNote
    return ($Row + $Height + 1)
}

# Inserts a picture; returns the last row it covers.
function Add-Picture($Sheet, [string]$Path, [int]$Row, [int]$Col, [double]$Width) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $Row }
    $anchor = $Sheet.Cells.Item($Row, $Col)
    $pic = $Sheet.Shapes.AddPicture($Path, 0, -1, $anchor.Left, $anchor.Top, -1, -1)
    $pic.LockAspectRatio = -1
    $pic.Width = $Width
    return [int]$pic.BottomRightCell.Row
}

function Get-LastRow($Sheet) { $ur = $Sheet.UsedRange; return [int]($ur.Row + $ur.Rows.Count - 1) }

# Runs $Body with an Excel instance and always closes Excel afterwards.
function Invoke-Excel([scriptblock]$Body) {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false; $xl.DisplayAlerts = $false; $xl.ScreenUpdating = $false
    try { & $Body $xl }
    finally {
        try { foreach ($w in @($xl.Workbooks)) { $w.Close($false) } } catch { }
        $w = $null
        try { $xl.Quit() } catch { }
        try { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl) } catch { }
        $xl = $null
        [GC]::Collect(); [GC]::WaitForPendingFinalizers(); [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    }
}

# One step's section on the Run Details tab, written as a walkthrough: what was run, the result,
# how to verify it, the screenshots, then the scope and the checks on each search. Returns the next free row.
function Write-RunSection($Ws, [int]$Row, [string]$Title, [string]$WhatRan, [string]$Result, [string[]]$Verify, [object[]]$Pictures, [object[]]$Tables) {
    $r = Write-Text $Ws $Row $Title -Span 12 -Section
    $r = Write-Text $Ws ($r + 1) 'What was run' -Span 12 -Bold
    $r = Write-Text $Ws $r $WhatRan -Span 12
    $r = Write-Text $Ws ($r + 1) 'Result' -Span 12 -Bold
    $r = Write-Text $Ws $r $Result -Span 12
    $r = Write-Text $Ws ($r + 1) 'How to verify' -Span 12 -Bold
    for ($i = 0; $i -lt $Verify.Count; $i++) { $r = Write-Text $Ws $r ("{0}. {1}" -f ($i + 1), $Verify[$i]) -Span 12 }

    $r = Write-Text $Ws ($r + 1) 'Screenshots' -Span 12 -Bold
    $pics = @($Pictures | Where-Object { $_.Path -and (Test-Path -LiteralPath $_.Path) })
    if ($pics.Count -eq 0) { $r = Write-Text $Ws $r 'No screenshots were taken in this run.' -Span 12 -Note }
    $bottom = $r
    for ($i = 0; $i -lt $pics.Count; $i++) {
        $col = if ($i % 2 -eq 0) { 1 } else { 7 }
        if ($i % 2 -eq 0 -and $i -gt 0) { $r = $bottom + 2 }
        $null = Write-Text $Ws $r $pics[$i].Caption -Col $col -Span 1 -Bold
        $bottom = [Math]::Max($bottom, (Add-Picture $Ws $pics[$i].Path ($r + 1) $col 540))
    }
    $r = $bottom + 1
    foreach ($t in $Tables) {
        $r = Write-Text $Ws ($r + 1) $t.Title -Span 12 -Bold
        if ($t.Note) { $r = Write-Text $Ws $r $t.Note -Span 12 -Note }
        $r = Write-Table $Ws $r $t.Rows $t.Columns
    }
    $r = Write-Text $Ws ($r + 1) "End of $Title." -Span 12 -Note
    return $r
}

# The two verification steps shown for each run (both are visible in the screenshots).
function Get-VerifySteps {
    @(
        'The run start screenshot shows the PowerShell console at the start of the run: the command that was run, the settings (review period, in-scope servers, Splunk index and the input file hashes) and the start date and time.',
        'Each Splunk screenshot below shows the search in Splunk Web as it finished: the query, time range and result count, with the date and time on the screen.',
        ("The run summary screenshot shows the PowerShell console at the end of the run: the evidence script version ({0}) and its SHA256 ({1}), the overall status, and the date and time." -f $ScriptVersion, $ScriptHash)
    )
}

# The Splunk searches of this run (not the internal splits of the combined search, the AD step or the audit check itself).
$SearchNames = @{ QDISC = 'Accounts with SQL audit activity'; QS = 'SQL audit activity summary'; QE = 'Windows logons (EventCode 4624)' }
function Get-SearchRows {
    @($script:Manifest | Where-Object { $SearchNames.ContainsKey([string]$_.query_id) } | ForEach-Object {
        [pscustomobject]@{ search = "$($SearchNames[$_.query_id]) ($($_.query_id))"; rows_written = $_.rows_written; finished_local = $_.finished_local
                           retrieval_check = $_.retrieval_check; audit_check = $(if ($_.audit_check) { $_.audit_check } else { 'Not checked' }) }
    })
}
$SearchCols = @('search','rows_written','finished_local','retrieval_check','audit_check')

function Get-RunPictures {
    $p = @([pscustomobject]@{ Caption = 'Run start in the PowerShell console: command, settings and start time (Screenshot_Start.png)'; Path = (Join-Path $RunDir 'Screenshot_Start.png') })
    $p += @(foreach ($m in $script:Manifest | Where-Object { $_.screenshot_file }) {
        [pscustomobject]@{ Caption = "Search $($m.query_id) in Splunk Web ($($m.screenshot_file))"; Path = (Join-Path $RunDir $m.screenshot_file) }
    })
    $p + [pscustomobject]@{ Caption = 'Run summary in the PowerShell console (Screenshot.png)'; Path = (Join-Path $RunDir 'Screenshot.png') }
}

$SearchesNote = 'All results received: the rows received equal the result count Splunk reported. Confirmed in Splunk audit log: at the end of the run, the script found the search in Splunk''s audit log (index _audit) with the same result count.'
$ScopeNote = 'SQL audit events from these servers are included when the database is in scope. Login events (LGIS, LGIF) and events with no database name are included for these servers regardless of database.'
function Import-RunCsv([string]$Name) { $p = Join-Path $RunDir $Name; if (Test-Path -LiteralPath $p) { @(Import-Csv -LiteralPath $p) } else { @() } }

# ------------------------------------------------------------------ step 1 workbook
function Build-Step1Workbook {
    Invoke-Excel {
        param($xl)
        $wbk = $xl.Workbooks.Open($TemplateFull, 0, $true)
        Set-Cell $wbk.Worksheets.Item('Leadsheet') 2 2 $PeriodText

        $ws = $wbk.Worksheets.Item('Account Classification')
        $rows = Import-RunCsv 'Account_Classification.csv'
        $m = $script:Manifest | Where-Object { $_.query_id -eq 'QDISC' } | Select-Object -First 1
        Set-Cell $ws 12 1 ("Source: Splunk search QDISC, finished {0}; {1} accounts. See Run Details, Step 1." -f $m.finished_local, $rows.Count)
        $ws.Cells.Item(12, 1).Font.Color = $ClrNote
        $null = Write-Table $ws 14 $rows $ClassCols
        if ($rows.Count) { $ws.Range($ws.Cells.Item(15, 24), $ws.Cells.Item(14 + $rows.Count, 25)).Interior.Color = $ClrLavender }   # Classification, Notes

        $wr = $wbk.Worksheets.Item('Run Details')
        $tables = @(
            @{ Title = 'In-scope SQL servers and databases (server_sets.csv)'; Note = $ScopeNote; Rows = @(Import-Csv -LiteralPath $ServerSetsPath); Columns = @('server_set','host','in_scope_databases') },
            @{ Title = 'Searches'; Note = $SearchesNote; Rows = (Get-SearchRows); Columns = $SearchCols }
        )
        $whatRan = ("One Splunk search listed every account with SQL audit activity on the in-scope SQL servers and databases from {0}. Each domain account in a configured domain was then looked up in Active Directory. Run by {1} on {2}. Times are in {3}." -f `
            $PeriodText, $banner['Run by'], $banner['Run started (local)'], $SplunkTz)
        $result = ("{0} accounts found, listed on the Account Classification tab (Active Directory lookup: {1}). Overall status: {2}." -f $rows.Count, $ByLookup, $overall)
        $null = Write-RunSection $wr 4 'Step 1: Account discovery' $whatRan $result (Get-VerifySteps) (Get-RunPictures) $tables

        [void]$wbk.Worksheets.Item('Leadsheet').Activate()
        $out = Join-Path $RunDir "SvcAcct_Exclusion_Assessment_$RunId.xlsx"
        [void]$wbk.SaveAs($out, 51)
        [void]$wbk.Close($false)
        Write-Host "Workbook saved: $out"
        Write-Host 'Next: open it, set the Classification for every account on the Account Classification tab, save it, put its path in $Workbook in the SETTINGS at the top of this script and run step 2.' -ForegroundColor Green
    }
}

# ------------------------------------------------------------------ step 2 workbook
function Get-SheetName([string]$Account, [hashtable]$Used) {
    $base = $(if ($Account -match '\\([^\\]+)$') { $Matches[1] } else { $Account }) -replace "[\\/\?\*\[\]:']", '_'
    if ($base.Length -gt 28) { $base = $base.Substring(0, 28) }
    $nm = $base; $n = 2
    while ($Used.ContainsKey($nm.ToLower())) { $nm = "$base~$n"; $n++ }
    $Used[$nm.ToLower()] = $true
    return $nm
}

function Write-AccountPage($Pg, [string]$Acct, $Data) {
    $cr = $ClassRows | Where-Object { $_.Account.ToLower() -eq $Acct } | Select-Object -First 1
    $qp = $Data.QP | Where-Object { $_.account -eq $Acct } | Select-Object -First 1
    $qa = $Data.QA | Where-Object { $_.account -eq $Acct } | Select-Object -First 1
    $qb = @($Data.QB | Where-Object { $_.account -eq $Acct })
    $qc = @($Data.QC | Where-Object { $_.account -eq $Acct })
    $qd = @($Data.QD | Where-Object { $_.account -eq $Acct })
    $kind = if ($Acct -match '^(nt authority|nt service|builtin|iis apppool|window manager|font driver host)\\') { 'builtin' }
            elseif ($Acct -match '\\([^\\]+)$') { if ($Matches[1] -match '\$$') { 'computer' } else { 'windows' } } else { 'sql' }
    $bare = if ($Acct -match '\\([^\\]+)$') { $Matches[1].ToLower() } else { $Acct }
    $qe = @(if ($kind -eq 'windows') { $Data.QE | Where-Object { $_.account -eq $bare } })
    $sum = { param($rows, $filter) [int64](($rows | Where-Object $filter | Measure-Object -Property events -Sum).Sum) }
    $winTotal = & $sum $qe { $true }
    $interactive = & $sum $qe { $_.result -like 'EXCEPTION*' }
    $unknownType = & $sum $qe { $_.result -like 'REVIEW*' }
    $toolEvents = & $sum $qb { $_.interactive_tool -eq 'Y' }
    $notLogged = & $sum $qb { $_.result -like 'REVIEW*' }
    $changes = [int64]$(if ($qp) { $qp.change_actions } else { 0 })
    $events = [int64]$(if ($qp) { $qp.events } else { 0 })
    $count = { param([string]$s) @(([string]$s) -split ';\s*' | Where-Object { $_ }).Count }

    # Title and account details (rows 5-10; owner, purpose and attestation in rows 11-13 are left for the owner)
    Set-Cell $Pg 1 1 "Service Account Assessment: $Acct"
    $adText = if ($cr) {
        $parts = @("Lookup: $($cr.'AD lookup')")
        if ($cr.'Display name') { $parts += "display name: $($cr.'Display name')" }
        if ($cr.Description) { $parts += "description: $($cr.Description)" }
        if ($cr.Enabled) { $parts += "enabled: $($cr.Enabled)" }
        ($parts -join '; ') + '. Details on the Account Classification tab.'
    } else { '' }
    Set-Cell $Pg 5 2 $Acct
    Set-Cell $Pg 6 2 $adText
    Set-Cell $Pg 7 2 $(if ($qp) { $qp.server_sets } else { '' })
    Set-Cell $Pg 8 2 $(if ($qp) { $qp.sql_servers } else { '' })
    Set-Cell $Pg 9 2 $(if ($qp) { $qp.databases } else { '' })
    foreach ($rr in 6..9) { $t = [string]$Pg.Cells.Item($rr, 2).Value2; $Pg.Rows.Item($rr).RowHeight = 13.5 * [Math]::Max(1, [Math]::Ceiling($t.Length / 170)) }
    Set-Cell $Pg 10 2 $(if ($qp) { "$events events in the review period; first seen $($qp.first_seen); last seen $($qp.last_seen)." } else { 'No SQL audit activity in the review period.' })

    # Observed in Splunk (D18:D22) and disqualifier observations (D25:D28)
    $winText = switch ($kind) {
        'windows'  { "Windows logons (EventCode 4624) on the in-scope SQL servers: $winTotal, of which interactive: $interactive" + $(if ($unknownType) { "; logon type not recorded: $unknownType" } else { '' }) + '.' }
        'sql'      { 'SQL login: no Windows account, so no Windows logons.' }
        'builtin'  { 'Built-in Windows identity: Windows logons not checked.' }
        'computer' { 'Computer or managed service account: Windows logons not checked.' }
    }
    $toolText = "SQL audit events from interactive tools: $toolEvents" + $(if ($notLogged) { "; client and application not logged for $notLogged events" } else { '' }) + '.'
    Set-Cell $Pg 18 4 "$winText $toolText See Section 1."
    Set-Cell $Pg 19 4 ("{0} events on {1} database(s) from {2} client host(s) and {3} application(s); {4} schema or permission change(s). See Section 2." -f `
        $events, (& $count $(if ($qa) { $qa.databases })), (& $count $(if ($qa) { $qa.client_hosts })), (& $count $(if ($qa) { $qa.applications })), $changes)
    Set-Cell $Pg 20 4 'Not from Splunk. CyberArk evidence: Section 3.'
    Set-Cell $Pg 21 4 'Not from Splunk. User access review evidence: Section 4.'
    Set-Cell $Pg 22 4 'Not from Splunk. Owner and attestation: Account details and Section 5.'
    if ($kind -eq 'windows') {
        Set-Cell $Pg 25 4 ([int64]$interactive)
        Set-Cell $Pg 25 5 ('interactive Windows logons (Section 1)' + $(if ($unknownType) { "; $unknownType logons with no logon type recorded need review" } else { '' }))
    } else {
        Set-Cell $Pg 25 4 'n/a'
        Set-Cell $Pg 25 5 $(switch ($kind) { 'sql' { 'not applicable: SQL login' } 'builtin' { 'not checked: built-in identity' } 'computer' { 'not checked: computer or managed service account' } })
    }
    if ($interactive -gt 0) { Set-Cell $Pg 25 8 'Yes' }
    Set-Cell $Pg 26 4 'From CyberArk (Section 3).'
    Set-Cell $Pg 27 4 "SQL audit events from interactive tools: $toolEvents; schema or permission changes: $changes (Section 2)."
    Set-Cell $Pg 28 4 'Review the evidence for each criterion.'

    # Evidence sections, from row 33
    $r = Write-Text $Pg 33 '1. Non-interactive use' -Section
    $r = Write-Text $Pg $r 'What this shows: Windows logons (EventCode 4624) by this account name on the in-scope SQL servers, and SQL audit events from interactive tools. Interactive logon types are 2 (console), 7 (unlock), 10 (Remote Desktop) and 11 (cached); any interactive logon is disqualifier D1. Why: supports criterion 1.' -Note
    switch ($kind) {
        'windows' {
            $r = Write-Text $Pg ($r + 1) 'Windows logons (EventCode 4624) on the in-scope SQL servers, by logon type' -Bold
            $r = Write-Table $Pg $r $qe @('logon_type','logon_type_name','target_host','source_workstation','source_ip','events','first_seen','last_seen','result','account_domain')
        }
        'sql'     { $r = Write-Text $Pg ($r + 1) 'Windows logons: not applicable. This is a SQL login with no Windows account.' -Note }
        'builtin' { $r = Write-Text $Pg ($r + 1) 'Windows logons: not checked. Built-in Windows identities are excluded from the logon search because their names match unrelated logons.' -Note }
        'computer' { $r = Write-Text $Pg ($r + 1) 'Windows logons: not checked. Computer and managed service accounts (names ending in $) are excluded from the logon search.' -Note }
    }
    $r = Write-Text $Pg ($r + 1) 'SQL audit events from interactive tools (Management Studio, sqlcmd, PowerShell, Excel and similar)' -Bold
    $r = Write-Table $Pg $r @($qb | Where-Object { $_.interactive_tool -eq 'Y' }) @('sql_server','database','client_host','client_ip','application','events','first_seen','last_seen')
    $r = Write-AttachBox $Pg ($r + 1) $(if ($kind -eq 'sql') { 'Configuration preventing interactive logon: not applicable for a SQL login (enter Not applicable in the evidence reference).' }
                                      else { 'Configuration preventing interactive logon (for example, a Group Policy report showing the account or its group in Deny log on locally and Deny log on through Remote Desktop Services on the in-scope servers)' })

    $r = Write-Text $Pg ($r + 1) '2. Defined activity' -Section
    $r = Write-Text $Pg $r 'What this shows: what the account did in the review period, for comparison with its documented purpose and expected activity (Account details). Why: supports criterion 2 and disqualifier D3.' -Note
    $r = Write-Text $Pg ($r + 1) 'Activity summary' -Bold
    $r = Write-Pairs $Pg $r @(
        @('SQL audit events', [string]$events),
        @('Logins succeeded / failed', $(if ($qa) { "$($qa.logins_succeeded) / $($qa.logins_failed)" } else { '' })),
        @('SQL servers', $(if ($qa) { $qa.sql_servers } else { '' })), @('Databases', $(if ($qa) { $qa.databases } else { '' })),
        @('Client hosts', $(if ($qa) { $qa.client_hosts } else { '' })), @('Client IPs', $(if ($qa) { $qa.client_ips } else { '' })),
        @('Applications', $(if ($qa) { $qa.applications } else { '' })), @('Action types', $(if ($qa) { $qa.action_ids } else { '' })),
        @('First seen / last seen', $(if ($qa) { "$($qa.first_seen) / $($qa.last_seen)" } else { '' }))
    )
    $r = Write-Text $Pg $r 'Action types: SL select, IN insert, UP update, DL delete, EX execute, LGIS login succeeded, LGIF login failed. Changes: CR create, AL alter, DR drop, G grant, GWG grant with grant, R revoke, D deny, APRL add role member, DPRL drop role member, AUSC audit session change, IMP impersonate, TO take ownership.' -Note
    $r = Write-Text $Pg ($r + 1) 'Connection sources (client host and application)' -Bold
    $r = Write-Table $Pg $r $qb @('sql_server','database','db_in_scope','client_host','client_ip','application','events','first_seen','last_seen','interactive_tool')
    $r = Write-Text $Pg ($r + 1) "Activity by hour (events; times in the Splunk user's time zone, $SplunkTz)" -Bold
    $hours = @(for ($h = 0; $h -lt 24; $h++) {
        $hh = '{0:D2}' -f $h
        [pscustomobject]@{
            hour = "$hh`:00"
            weekday_events = [string][int64](($qd | Where-Object { $_.hour -eq $hh -and $_.day_type -eq 'Weekday' } | Measure-Object -Property events -Sum).Sum)
            weekend_events = [string][int64](($qd | Where-Object { $_.hour -eq $hh -and $_.day_type -eq 'Weekend' } | Measure-Object -Property events -Sum).Sum)
        }
    })
    $r = Write-Table $Pg $r $hours @('hour','weekday_events','weekend_events')
    $r = Write-Text $Pg ($r + 1) 'Schema and permission changes (create, alter, drop, grant, revoke, deny, role membership, ownership and audit changes)' -Bold
    $r = Write-Table $Pg $r $qc @('time','sql_server','database','action_id','class_type','object_name','succeeded','statement','events')

    $r = Write-Text $Pg ($r + 1) '3. Credential custody' -Section
    $r = Write-Text $Pg $r 'Evidence required: the credentials are vaulted in CyberArk, and every retrieval in the review period is attributable and supported by an authorized rotation, approved ticket or other documented business reason. Why: supports criterion 3 and disqualifier D2.' -Note
    $r = Write-AttachBox $Pg ($r + 1) 'CyberArk evidence: the safe and platform policy for this account (vaulted, checkout required) and the checkout report for the review period, with the justification or ticket for each retrieval'

    $r = Write-Text $Pg ($r + 1) '4. Least privilege' -Section
    $r = Write-Text $Pg $r 'Evidence required: the account''s permissions as reviewed in the user access review (UAR). Why: supports criterion 4.' -Note
    $r = Write-AttachBox $Pg ($r + 1) 'User access review: the UAR name and date, and the account''s entitlements as reviewed'

    $r = Write-Text $Pg ($r + 1) '5. Accountability' -Section
    $r = Write-Text $Pg $r 'Evidence required: the accountable owner''s attestation of the purpose and expected activity recorded in Account details. Why: supports criterion 5.' -Note
    $null = Write-AttachBox $Pg ($r + 1) 'Owner attestation (for example, the approved ticket)'
}

function Build-Step2Workbook {
    $data = @{
        QP = Import-RunCsv 'QP_Population.csv'; QA = Import-RunCsv 'QA_Profile.csv'; QB = Import-RunCsv 'QB_Connections.csv'
        QC = Import-RunCsv 'QC_Changes.csv'; QD = Import-RunCsv 'QD_Pattern.csv'; QE = Import-RunCsv 'QE_WinLogons.csv'
    }
    Invoke-Excel {
        param($xl)
        $wbk = $xl.Workbooks.Open($WorkbookCopy, 0, $true)
        $ls = $wbk.Worksheets.Item('Leadsheet')
        Set-Cell $ls 2 2 $PeriodText

        # One tab per account classified as Service account: a copy of the hidden 'Account Template' tab
        $tpl = $wbk.Worksheets.Item('Account Template')
        $tpl.Visible = -1
        $after = $wbk.Worksheets.Item('Account Classification')
        $used = @{ 'leadsheet' = 1; 'account classification' = 1; 'account template' = 1; 'run details' = 1 }
        $tabs = @()
        foreach ($acct in ($Candidates | Sort-Object)) {
            $nm = Get-SheetName $acct $used
            [void]$tpl.Copy([System.Reflection.Missing]::Value, $after)
            $pg = $wbk.Worksheets.Item($after.Index + 1)
            $pg.Name = $nm
            Write-AccountPage $pg $acct $data
            $after = $pg
            $tabs += [pscustomobject]@{ Account = $acct; Sheet = $nm }
            Write-Host "    account tab: $nm"
        }
        [void]$tpl.Delete()

        # Leadsheet summary: one row per account, linked to its tab
        $r = 36
        $a36 = $ls.Cells.Item(36, 1)
        $a36.NumberFormat = 'General'; [void]$a36.ClearContents(); $a36.Font.Color = 0
        foreach ($t in $tabs) {
            $q = "'" + $t.Sheet + "'!"
            $ls.Cells.Item($r, 1).Formula = "=$($q)B5"
            $ls.Cells.Item($r, 2).Formula = "=IF($($q)B11=`"`",`"`",$($q)B11)"
            $ls.Cells.Item($r, 3).Formula = "=IF($($q)B12=`"`",`"`",$($q)B12)"
            for ($k = 0; $k -lt 5; $k++) { $ls.Cells.Item($r, 4 + $k).Formula = "=$($q)H$(18 + $k)" }
            $ls.Cells.Item($r, 9).Formula = "=$($q)H30"
            $ls.Cells.Item($r, 10).Formula = "=$($q)H31"
            $ls.Cells.Item($r, 11).Formula = "=HYPERLINK(`"#$($q)A1`",`"Open`")"
            $r++
        }
        if ($tabs.Count) {
            $rng = $ls.Range($ls.Cells.Item(36, 1), $ls.Cells.Item($r - 1, 11))
            $rng.Borders.LineStyle = 1; $rng.Borders.Color = $ClrBorder; $rng.VerticalAlignment = $xlTop
            $ls.Range($ls.Cells.Item(36, 3), $ls.Cells.Item($r - 1, 3)).WrapText = $true
            $ls.Range($ls.Cells.Item(36, 4), $ls.Cells.Item($r - 1, 11)).HorizontalAlignment = $xlCenter
        }

        # Run Details: step 2 section below step 1
        $wr = $wbk.Worksheets.Item('Run Details')
        $start = (Get-LastRow $wr) + 3
        $q0 = @(Import-RunCsv 'Q0_Completeness.csv')
        $tables = @(
            @{ Title = 'In-scope SQL servers and databases (server_sets.csv)'; Note = $ScopeNote; Rows = @(Import-Csv -LiteralPath $ServerSetsPath); Columns = @('server_set','host','in_scope_databases') },
            @{ Title = 'Log coverage'; Note = 'Days with SQL audit events (EventCode 33205) from each in-scope server. A server with no events or missing days is an exception and limits the evidence for that server. Completeness of Windows logon events (4624) is not measured here.'; Rows = $q0; Columns = @('host','server_set','events','days_with_events','expected_days','first_event_day','last_event_day','result') },
            @{ Title = 'Searches'; Note = $SearchesNote; Rows = (Get-SearchRows); Columns = $SearchCols }
        )
        $whatRan = ("One Splunk search summarized all SQL audit events on the in-scope SQL servers and databases from {0}: the {1} accounts classified as Service account in detail, and all other accounts as one total so the figures reconcile. A second search listed Windows logons (EventCode 4624) on the in-scope SQL servers for those accounts' names (the part after DOMAIN\). Run by {2} on {3}. Times are in {4}." -f `
            $PeriodText, $Candidates.Count, $banner['Run by'], $banner['Run started (local)'], $SplunkTz)
        $result = ("{0} accounts assessed, one tab each. Every summary of the SQL audit search adds up to the same total of in-scope events: {1}. Servers with SQL audit events on every day of the period: {2} of {3} (Log coverage, below). Overall status: {4}." -f `
            $tabs.Count, $(if ($reconOk) { 'Yes' } else { 'No' }), @($q0 | Where-Object { $_.result -eq 'OK' }).Count, $q0.Count, $overall)
        $null = Write-RunSection $wr $start 'Step 2: Assessment' $whatRan $result (Get-VerifySteps) (Get-RunPictures) $tables

        [void]$ls.Activate()
        $out = Join-Path $RunDir "SvcAcct_Exclusion_Assessment_$RunId.xlsx"
        [void]$wbk.SaveAs($out, 51)
        [void]$wbk.Close($false)
        Write-Host "Workbook saved: $out"
    }
}


# ------------------------------------------------------------------ read an .xlsx table (no Excel needed)
# Reads one sheet of an .xlsx file (it is a zip of XML files) and returns the rows below a header row
# as objects keyed by the header names. Stops at the first row with an empty first column.
function Read-XlsxTable([string]$Path, [string]$SheetName, [int]$HeaderRow) {
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead((Resolve-Path $Path).Path)
    try {
        function Get-ZipXml($name) {
            $e = $zip.Entries | Where-Object { $_.FullName -eq $name } | Select-Object -First 1
            if (-not $e) { return $null }
            $sr = New-Object IO.StreamReader($e.Open()); try { [xml]$sr.ReadToEnd() } finally { $sr.Dispose() }
        }
        $wbx  = Get-ZipXml 'xl/workbook.xml'
        $rels = Get-ZipXml 'xl/_rels/workbook.xml.rels'
        $sheet = @($wbx.workbook.sheets.sheet) | Where-Object { $_.name -eq $SheetName } | Select-Object -First 1
        if (-not $sheet) { throw "Sheet '$SheetName' not found in $Path" }
        $rid = $sheet.GetAttribute('id', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships')
        $target = (@($rels.Relationships.Relationship) | Where-Object { $_.Id -eq $rid }).Target
        $target = if ($target.StartsWith('/')) { $target.TrimStart('/') } else { 'xl/' + $target }
        $shared = @()
        $ssx = Get-ZipXml 'xl/sharedStrings.xml'
        if ($ssx) { $shared = @($ssx.sst.si | ForEach-Object { if ($_.t -ne $null) { if ($_.t -is [string]) { $_.t } else { $_.t.'#text' } } else { (@($_.r) | ForEach-Object { if ($_.t -is [string]) { $_.t } else { $_.t.'#text' } }) -join '' } }) }
        $sx = Get-ZipXml $target
        $grid = @{}
        foreach ($row in @($sx.worksheet.sheetData.row)) {
            $rn = [int]$row.r
            foreach ($c in @($row.c)) {
                if (-not $c) { continue }
                $col = 0; foreach ($ch in ($c.r -replace '\d', '').ToCharArray()) { $col = $col * 26 + ([int][char]$ch - 64) }
                $v = $null
                switch ($c.t) {
                    's'         { $v = $shared[[int]$c.v] }
                    'inlineStr' { $v = if ($c.is.t -is [string]) { $c.is.t } else { $c.is.t.'#text' } }
                    default     { $v = if ($c.v -is [string]) { $c.v } elseif ($c.v) { $c.v.'#text' } else { $null } }
                }
                if ($v -ne $null) { $grid["$rn,$col"] = [string]$v }
            }
        }
        $headers = @{}
        for ($col = 1; $col -le 200; $col++) { $h = $grid["$HeaderRow,$col"]; if ($h) { $headers[$col] = $h.Trim() } }
        $nonEmptyA = @($grid.Keys | Where-Object { ($_ -split ',')[1] -eq '1' -and [int](($_ -split ',')[0]) -gt $HeaderRow -and $grid[$_].Trim() }).Count
        $out = New-Object System.Collections.Generic.List[object]
        for ($rn = $HeaderRow + 1; $rn -le $HeaderRow + 100000; $rn++) {
            if (-not $grid["$rn,1"]) { break }
            $o = [ordered]@{}
            foreach ($col in ($headers.Keys | Sort-Object)) { $o[$headers[$col]] = $(if ($grid.ContainsKey("$rn,$col")) { $grid["$rn,$col"].Trim() } else { '' }) }
            $out.Add([pscustomobject]$o)
        }
        if ($nonEmptyA -ne $out.Count) { throw "Tab '$SheetName' has a blank row inside the table (read $($out.Count) rows, column A has $nonEmptyA values). Remove blank rows and run again." }
        return $out.ToArray()
    } finally { $zip.Dispose() }
}

# Tab names of an .xlsx file, in order (no Excel needed)
function Get-XlsxSheetNames([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead((Resolve-Path $Path).Path)
    try {
        $e = $zip.Entries | Where-Object { $_.FullName -eq 'xl/workbook.xml' } | Select-Object -First 1
        $sr = New-Object IO.StreamReader($e.Open()); try { [xml]$x = $sr.ReadToEnd() } finally { $sr.Dispose() }
        return @(@($x.workbook.sheets.sheet) | ForEach-Object { $_.name })
    } finally { $zip.Dispose() }
}

# --------------------------------------------------------------------- setup and inputs
$ScriptPath = $PSCommandPath
$CommandLine = "$($MyInvocation.Line)".Trim()
if (-not $CommandLine) {   # e.g. started with powershell -File: rebuild it from the parameters given
    $CommandLine = ((@(Split-Path -Leaf $ScriptPath) + @($PSBoundParameters.GetEnumerator() | ForEach-Object {
        if ($_.Value -is [switch]) { "-$($_.Key)" } else { "-$($_.Key) $($_.Value)" } })) -join ' ')
}
$ScriptHash = Get-Sha256 $ScriptPath
$RunStart   = Get-Date
$RunId      = $RunStart.ToString('yyyyMMdd_HHmmss')
try { $Host.UI.RawUI.WindowTitle = "SvcAcctEvidence_$RunId" } catch { }
$RunDir     = Join-Path (Resolve-Path $OutputRoot) $(if ($Preflight) { "SvcAcctPREFLIGHT_$RunId" } elseif ($Discover) { "SvcAcctDISCOVERY_$RunId" } else { "SvcAcctEvidence_$RunId" })
$QueryDir   = Join-Path $RunDir 'queries'
New-Item -ItemType Directory -Path $QueryDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $RunDir 'screenshots') -Force | Out-Null
# Save the exact script that is running (with its settings) in the run folder, and check the copy
$ScriptCopy = Join-Path $RunDir (Split-Path -Leaf $ScriptPath)
Copy-Item -LiteralPath $ScriptPath -Destination $ScriptCopy
if ((Get-Sha256 $ScriptCopy) -ne $ScriptHash) { throw 'The copy of the script in the run folder does not match the running script.' }
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
# Step 2 needs the classified workbook from step 1
if (-not $Preflight -and -not $Discover -and -not $Workbook) {
    throw 'No workbook given. Run step 1 (-Discover) first, set the Classification for every account in the workbook it creates, save it, then give that workbook to step 2.'
}
if ($Discover -and -not $WorkbookTemplate) { throw 'Step 1 needs the workbook template (-WorkbookTemplate).' }
$dupHosts = @($ServerSets | Group-Object { $_.host.ToLower() } | Where-Object { $_.Count -gt 1 } | ForEach-Object { $_.Name })
if ($dupHosts.Count) { throw "server sets CSV lists these hosts more than once: $($dupHosts -join ', '). Each host must be in exactly one row." }
$TemplateFull = if ($WorkbookTemplate) { (Resolve-Path $WorkbookTemplate).Path } else { '' }
$PeriodText = '{0} to {1}' -f $StartDate.ToString('yyyy-MM-dd'), $EndDate.ToString('yyyy-MM-dd')

# Step 2: copy the classified workbook into the run folder (that copy is hashed, read and built on),
# then load the classification. Only 'Service account' rows are assessed (candidates).
$ClassTypes = @('Service account', 'Human', 'Deployment', 'Other')
$ClassRows = @(); $Candidates = @(); $WorkbookPath = ''; $WorkbookCopy = ''
if ($Workbook -and -not $Discover -and -not $Preflight) {
    $WorkbookPath = (Resolve-Path $Workbook).Path
    $WorkbookCopy = Join-Path $RunDir 'Classified_Workbook_Input.xlsx'
    try { Copy-Item -LiteralPath $WorkbookPath -Destination $WorkbookCopy -ErrorAction Stop }
    catch { throw "Could not copy $WorkbookPath ($($_.Exception.Message)). Close it in Excel and run again." }
    $sheetNames = @(Get-XlsxSheetNames $WorkbookCopy)
    if ('Account Classification' -notin $sheetNames) { throw "$WorkbookPath has no 'Account Classification' tab. Use the workbook produced by step 1." }
    if ('Account Template' -notin $sheetNames) { throw "$WorkbookPath has already been through step 2 (no 'Account Template' tab). Use the classified workbook produced by step 1." }
    $ClassRows = @(Read-XlsxTable $WorkbookCopy 'Account Classification' 14)
    if ($ClassRows.Count -eq 0) { throw "No accounts found in $WorkbookPath (tab 'Account Classification', header row 14)." }
    foreach ($col in 'Account', 'Classification') {
        if ($col -notin $ClassRows[0].PSObject.Properties.Name) { throw "Column '$col' not found in row 14 of the Account Classification tab. Do not rename or move the columns." }
    }
    $untagged = @($ClassRows | Where-Object { $_.Classification -notin $ClassTypes })
    if ($untagged.Count) { throw ("{0} account(s) have no valid classification (allowed: {1}), e.g. {2}. Classify every account, save, and run again." -f $untagged.Count, ($ClassTypes -join ' / '), (($untagged | Select-Object -First 3 | ForEach-Object { $_.Account }) -join ', ')) }
    $Candidates = @($ClassRows | Where-Object { $_.Classification -eq 'Service account' } | ForEach-Object { $_.Account.ToLower() } | Select-Object -Unique)
    if ($Candidates.Count -eq 0) { throw 'No accounts are classified as Service account; nothing to assess.' }
    $ClassRows | Export-Csv -LiteralPath (Join-Path $RunDir 'Classification_Input.csv') -NoTypeInformation -Encoding UTF8
}

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
    'Command'                = $CommandLine
    'Run started (local)'    = $RunStart.ToString('yyyy-MM-dd HH:mm:ss zzz')
    'Run started (UTC)'      = $RunStart.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss') + 'Z'
    'Run by'                 = "$env:USERDOMAIN\$env:USERNAME"
    'Computer'               = $env:COMPUTERNAME
    'PowerShell'             = $PSVersionTable.PSVersion.ToString()
    'Script'                 = $ScriptPath
    'Script SHA256'          = $ScriptHash
    'Server sets CSV'        = $ServerSetsPath
    'Server sets CSV SHA256' = Get-Sha256 $ServerSetsPath
    'Mode'                   = $(if ($Preflight) { 'Preflight (not evidence)' } elseif ($Discover) { 'Step 1 - account discovery and AD lookup' } else { 'Step 2 - assessment of accounts tagged Service account' })
    'Classified workbook'    = $(if ($WorkbookPath) { $WorkbookPath } else { '(not used)' })
    'Workbook SHA256'        = $(if ($WorkbookCopy) { Get-Sha256 $WorkbookCopy } else { '' })
    'Accounts assessed'      = $(if ($WorkbookPath) { "$($Candidates.Count) classified as Service account, of $($ClassRows.Count) accounts" } else { '' })
    'AD servers'             = $(if ($AdServers.Count) { ($AdServers.Keys | ForEach-Object { "$_ -> $($AdServers[$_])" }) -join '; ' } else { '(none configured)' })
    'In-scope SQL servers'   = ($Hosts -join ', ')
    'Period (local)'         = "{0} 00:00 to {1} 23:59:59 ({2} days)" -f $PeriodStart.ToString('yyyy-MM-dd'), $EndDate.ToString('yyyy-MM-dd'), $ExpectedDays
    'Period (epoch sent)'    = "earliest=$EarliestEpoch latest=$LatestEpoch"
    'Period (UTC)'           = "{0}Z to {1}Z" -f $PeriodStart.ToUniversalTime().ToString('yyyy-MM-dd HH:mm'), $PeriodEnd.ToUniversalTime().ToString('yyyy-MM-dd HH:mm')
    'Splunk API'             = $SplunkBaseUrl
    'Splunk Web'             = $SplunkWebUrl
    'Workbook template'      = $(if ($TemplateFull) { $TemplateFull } else { '(not used)' })
    'Template SHA256'        = $(if ($TemplateFull) { Get-Sha256 $TemplateFull } else { '' })
    'Windows event index'    = $WinEventIndex
    'Output folder'          = $RunDir
}
$banner.GetEnumerator() | ForEach-Object { Write-Host ("{0,-24}: {1}" -f $_.Key, $_.Value) }
$script:Manifest  = New-Object System.Collections.Generic.List[object]
$script:RunFailed = $false
$script:RunNotes  = $false
# Start screenshot: the console showing the command that was run, the settings above and the start time
if (-not $NoScreenshot) {
    try {
        Write-Host ''
        Write-Host ("Get-Date                : {0}" -f (Get-Date -Format 'dddd, MMMM d, yyyy h:mm:ss tt K'))
        Write-Host 'Start screenshot in 3 seconds. Do not touch the keyboard or mouse until the run prints RUN FINISHED.' -ForegroundColor Green
        Start-Sleep -Seconds 3
        $hStart = Save-Screenshot (Join-Path $RunDir 'Screenshot_Start.png')
        Write-Host "Start screenshot saved: Screenshot_Start.png  SHA256 $hStart"
    } catch { Write-Host "Start screenshot failed: $($_.Exception.Message)" -ForegroundColor Yellow; $script:RunNotes = $true }
}
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
# All logic that selects and summarizes data is in the Splunk search text below. Each search is
# saved byte-for-byte as sent in the run folder (queries\<id>.spl).
#
# Shared filter, used word for word by QDISC (step 1) and QS (step 2), so step 2 covers exactly
# the population step 1 found:
#   1. Read the SQL Server audit events (Windows Security log, EventCode 33205) from the in-scope
#      SQL servers for the review period.
#   2. From each event, read the action, the account that performed it and the database.
#   3. Keep an event if the database is one of the in-scope databases on that server, OR it is a
#      login (succeeded or failed), OR it has no database (a server-level action). Drop the rest.
# =====================================================================================
$SqlScope = @'
search index=__IDX__ source="WinEventLog:Security" EventCode=33205 host IN (__HOSTS__)
| fields _time host Message
| rex field=Message "(?<![a-z_])action_id:(?<action_id>\S*)"
| rex field=Message "(?<![a-z_])server_principal_name:(?<server_principal_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])database_name:(?<database_name>.*?)(?=\s+[a-z_]+:|$)"
| where isnotnull(server_principal_name) AND server_principal_name!=""
| eval db_in_scope=case(isnull(database_name) OR database_name="", "Server-level", in(lower(host."|".database_name), __HOSTDB__), "Y", in(action_id,"LGIS","LGIF"), "Login", true(), "N")
| where db_in_scope!="N"
'@
$SqlDetail = @'
| rex field=Message "(?<![a-z_])succeeded:(?<succeeded>\S*)"
| rex field=Message "(?<![a-z_])class_type:(?<class_type>\S*)"
| rex field=Message "(?<![a-z_])object_name:(?<object_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])statement:(?<statement>[\s\S]*?)(?:\s+additional_information:|$)"
| rex field=Message "(?<![a-z_])client_ip:(?<client_ip>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])application_name:(?<application_name>.*?)(?=\s+[a-z_]+:|$)"
| rex field=Message "(?<![a-z_])host_name:(?<client_host>.*?)(?=\s+[a-z_]+:|$)"
| eval account=lower(server_principal_name), sql_server=host
'@
$SqlScope = $SqlScope.Replace('__IDX__', $WinEventIndex).Replace('__HOSTS__', $HostsSpl).Replace('__HOSTDB__', $HostDbSpl) + "`n"
$SqlDetail = $SqlDetail + "`n"
$SqlBase = $SqlScope + $SqlDetail
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

    # 4. Template has the expected tabs, and Excel can open it
    if ($TemplateFull) {
        try {
            $missing = @(@('Leadsheet', 'Account Classification', 'Account Template', 'Run Details') | Where-Object { $_ -notin @(Get-XlsxSheetNames $TemplateFull) })
            Invoke-Excel { param($xl) $t = $xl.Workbooks.Open($TemplateFull, 0, $true); [void]$t.Close($false) }
            Add-Check 'Excel + template' $(if ($missing.Count -eq 0) { 'PASS' } else { 'FAIL' }) $(if ($missing.Count -eq 0) { 'template opens in Excel; all tabs present' } else { "missing tabs: $($missing -join ', ')" })
        } catch { Add-Check 'Excel + template' 'FAIL' $_.Exception.Message }
    } else { Add-Check 'Excel + template' 'SKIPPED' 'no -WorkbookTemplate' }

    Write-Banner 'PREFLIGHT RESULTS'
    $pf | Format-Table -AutoSize -Wrap | Out-String -Width 250 | Write-Host
    $pf | Export-Csv -LiteralPath (Join-Path $RunDir 'PREFLIGHT_RESULTS.csv') -NoTypeInformation -Encoding UTF8
    if ($pf | Where-Object { $_.Result -eq 'FAIL' }) { Write-Host 'PREFLIGHT: FIX THE FAIL ITEMS BEFORE THE EVIDENCE RUN.' -ForegroundColor Red }
    else { Write-Host 'PREFLIGHT: READY FOR THE EVIDENCE RUN (check the screenshot in the screenshots folder).' -ForegroundColor Green }
    return
}

# =====================================================================================
# STEP 1 (-Discover)
# QDISC: accounts with SQL audit activity
#   1-3. The shared filter above.
#   4.   For each account: count its events and record the server sets and SQL servers it was
#        active on, and its first and last event.
#   5.   Result: one row per account (the Account Classification list).
# Then each DOMAIN\name account in a configured domain is looked up in Active Directory
# (Get-ADUser -Server). Nothing is changed in Splunk or Active Directory.
# =====================================================================================
if ($Discover) {
$qdisc = $SqlScope + @"
| eval account=lower(server_principal_name)
| eval server_set=coalesce(nullif($SetCaseSpl,""),"-")
| stats count AS events min(_time) AS first_t max(_time) AS last_t values(server_set) AS server_sets values(host) AS sql_servers BY account
| eval server_sets=mvjoin(server_sets,"; "), sql_servers=mvjoin(sql_servers,"; "), first_seen=strftime(first_t,$TimeFmt), last_seen=strftime(last_t,$TimeFmt)
| table account server_sets sql_servers events first_seen last_seen
"@
$rDisc = Invoke-SplunkQuery -Id 'QDISC' -Spl $qdisc -OutFile 'Discovery_Accounts.csv' -Columns @('account','server_sets','sql_servers','events','first_seen','last_seen')
Save-Result $rDisc $rDisc.Data
if (@($rDisc.Data).Count -eq 0) { throw 'No accounts found in scope. Check host names and in_scope_databases in server_sets.csv (run -Preflight).' }

# AD lookup: Get-ADUser -Server <server for the account's domain prefix>
$adAvailable = [bool](Get-Command Get-ADUser -ErrorAction SilentlyContinue)
if (-not $adAvailable) { try { Import-Module ActiveDirectory -ErrorAction Stop; $adAvailable = $true } catch { } }
$AdMap = @{}; foreach ($k in $AdServers.Keys) { $AdMap[([string]$k).ToLower()] = [string]$AdServers[$k] }
Write-Host ''
Write-Host ("[AD] ActiveDirectory module available: {0}; domains configured: {1}" -f $adAvailable, $(if ($AdMap.Count) { ($AdMap.Keys -join ', ') } else { 'none' }))
$ClassCols = @('account','server_sets','sql_servers','events','first_seen','last_seen','ad_lookup','domain','ad_server','sam_account_name',
               'given_name','surname','display_name','description','enabled','employee_id','title','department','manager','spn_count',
               'password_never_expires','when_created','suggested_type','classification','notes')
$classData = foreach ($a in $rDisc.Data) {
    $o = [ordered]@{}; foreach ($c in $classCols) { $o[$c] = '' }
    foreach ($c in 'account','server_sets','sql_servers','events','first_seen','last_seen') { $o[$c] = $a.$c }
    $acct = [string]$a.account
    if ($acct -match '^(nt authority|nt service|builtin|iis apppool|window manager|font driver host)\\') {
        $o.ad_lookup = 'Built-in Windows identity'; $o.suggested_type = 'Other'
    } elseif ($acct -match '^([^\\]+)\\(.+)$') {
        $dom = $Matches[1]; $name = $Matches[2]; $o.domain = $dom; $o.sam_account_name = $name
        if ($name -match '\$$') { $o.ad_lookup = 'Computer account'; $o.suggested_type = 'Other' }
        elseif (-not $AdMap.ContainsKey($dom)) { $o.ad_lookup = 'Not looked up (domain not configured)'; $o.suggested_type = 'Unknown' }
        elseif (-not $adAvailable) { $o.ad_lookup = 'Not looked up (ActiveDirectory module not available)'; $o.suggested_type = 'Unknown' }
        else {
            $o.ad_server = $AdMap[$dom]
            try {
                $u = Get-ADUser -Identity $name -Server $AdMap[$dom] -Properties GivenName, Surname, DisplayName, Description, Enabled, EmployeeID, Title, Department, Manager, ServicePrincipalName, PasswordNeverExpires, whenCreated
                $o.ad_lookup = 'Found'
                $o.given_name = $u.GivenName; $o.surname = $u.Surname; $o.display_name = $u.DisplayName; $o.description = $u.Description
                $o.enabled = $u.Enabled; $o.employee_id = $u.EmployeeID; $o.title = $u.Title; $o.department = $u.Department
                $o.manager = $(if ($u.Manager) { ($u.Manager -split ',')[0] -replace '^CN=' } else { '' })
                $o.spn_count = @($u.ServicePrincipalName | Where-Object { $_ }).Count
                $o.password_never_expires = $u.PasswordNeverExpires
                $o.when_created = $(if ($u.whenCreated) { ([datetime]$u.whenCreated).ToString('yyyy-MM-dd') } else { '' })
                $o.suggested_type = $(if ($u.GivenName -or $u.Surname -or $u.EmployeeID) { 'Human' } else { 'Service account' })
            } catch {
                $o.ad_lookup = 'Not found in AD'; $o.notes = $_.Exception.Message; $o.suggested_type = 'Unknown'
            }
        }
    } else {
        $o.ad_lookup = 'SQL login (no AD account)'; $o.suggested_type = 'Service account'
    }
    [pscustomobject]$o
}
$classData = @($classData)
$classFile = Join-Path $RunDir 'Account_Classification.csv'
$classData | Select-Object $classCols | Export-Csv -LiteralPath $classFile -NoTypeInformation -Encoding UTF8
$h = Get-Sha256 $classFile
$script:ByLookup = ($classData | Group-Object ad_lookup | ForEach-Object { "$($_.Name): $($_.Count)" }) -join '; '
$bySuggest = ($classData | Group-Object suggested_type | ForEach-Object { "$($_.Name): $($_.Count)" }) -join '; '
Write-Host "    Accounts: $($classData.Count). AD lookup - $ByLookup"
Write-Host "    Suggested type - $bySuggest"
Write-Host "    Account_Classification.csv SHA256 $h"
$banner['Accounts discovered'] = "$($classData.Count) (AD lookup: $byLookup)"
$script:Manifest.Add([pscustomobject][ordered]@{ query_id = 'AD'; source_query = 'AD'; status = 'OK'; splunk_sid = ''; started_local = ''; finished_local = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss zzz')
    splunk_eventcount = ''; splunk_scancount = ''; splunk_resultcount = ''; rows_retrieved = $classData.Count; retrieval_check = ''; splunk_issues = ''; rows_written = $classData.Count
    post_processing = "Get-ADUser -Server per domain ($($banner['AD servers'])). Lookup results: $byLookup. Suggested type: Human if GivenName, Surname or EmployeeID is set; otherwise Service account."
    output_file = 'Account_Classification.csv'; output_sha256 = $h; query_file = '(Get-ADUser, in script)'; query_sha256 = ''
    screenshot_file = ''; screenshot_sha256 = ''; job_ttl_set = ''; audit_check = '' })
} else {

# =====================================================================================
# QS (step 2): SQL audit activity summary. ONE search, so the SQL audit data is read once.
#   1. The shared filter above (same population as step 1).
#   2. Mark each event as belonging to an account classified as Service account, or not. Events of
#      all other accounts are combined into one '(non-candidate accounts)' row: they still count
#      toward the totals, but nothing more is read from them.
#   3. For service account events, also read client machine, client IP, application, object and
#      statement. Blank values are stored as '-' so no event drops out of the summary.
#   4. Summarize everything once (account x server x database x client x application x action x
#      weekday/weekend x hour; schema and permission changes one row per change), then produce
#      these views from that one summary (appendpipe, inside the same search):
#        TOTAL  number of in-scope events (the control total)
#        Q0     log coverage: events and days with events per SQL server
#        QP     per account: events, changes, servers, databases, first and last event
#        QA     per account: events, logins, servers, databases, client machines, applications
#        QB     connection sources per account; interactive tools (Management Studio, sqlcmd...) flagged
#        QC     schema and permission changes: create, alter, drop, grant, revoke, deny, role
#               membership, ownership and audit changes (one row per change)
#        QD     activity by weekday/weekend and hour per account
#   5. The script splits the result by its 'section' column into one CSV per view, and checks that
#      Q0, QP, QA, QB and QD each add up to TOTAL, and that QC matches the changes counted in QP.
# =====================================================================================
$ChangeCodes = '"CR","AL","DR","G","GWG","R","D","APRL","DPRL","AUSC","IMP","TO"'
$HumanTools  = '(?i)management studio|ssms|sqlcmd|azure data studio|dbeaver|excel|toad|datagrip|powershell|python|linqpad|heidisql'
$CandSpl = ConvertTo-SplList $Candidates
# Accounts not tagged 'Service account' are kept in the totals as one row, '(non-candidate accounts)', so the
# reconciliation and log coverage still use every in-scope event; their detail fields are not extracted.
$qs = $SqlScope + @"
| eval account=lower(server_principal_name)
| eval is_candidate=if(in(account, $CandSpl), 1, 0)
| eval Message=if(is_candidate=1, Message, null())
"@ + "`n" + $SqlDetail + @"
| eval account=if(is_candidate=1, account, "(non-candidate accounts)")
| eval client_host=coalesce(nullif(client_host,""),"-"), client_ip=coalesce(nullif(client_ip,""),"-"), application_name=coalesce(nullif(application_name,""),"-"), database_name=coalesce(nullif(database_name,""),"-"), action_id=coalesce(nullif(action_id,""),"-")
| eval server_set=coalesce(nullif($SetCaseSpl,""),"-")
| eval is_change=if(is_candidate=1 AND in(action_id, $ChangeCodes), 1, 0)
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
               | eval result=case(account="(non-candidate accounts)", "Not assessed", human_tool="Y", "EXCEPTION: interactive tool", client_host="-" AND client_ip="-", "REVIEW: client not logged", true(), "OK")
               | eval first_seen=strftime(first_t,$TimeFmt), last_seen=strftime(last_t,$TimeFmt), section="QB"
               | rename database_name AS database, application_name AS application, human_tool AS interactive_tool ]
| appendpipe [ where isnull(section) AND is_change=1 | stats sum(events) AS events BY c_time account sql_server database_name db_in_scope action_id c_class c_object c_succeeded c_statement
               | rename c_time AS time, database_name AS database, c_class AS class_type, c_object AS object_name, c_succeeded AS succeeded, c_statement AS statement
               | eval result="EXCEPTION", section="QC" ]
| appendpipe [ where isnull(section) | stats sum(events) AS events BY account day_type hour
               | eval business_hours=if(day_type="Weekday" AND tonumber(hour)>=8 AND tonumber(hour)<18, "Y", "N"), section="QD" ]
| where isnotnull(section)
| table section account host server_set server_sets events days_with_events first_day_n last_day_n change_actions sql_server sql_servers database databases db_in_scope
        client_host client_hosts client_ip client_ips application applications action_id action_ids logins_succeeded logins_failed interactive_tool
        time class_type object_name succeeded statement day_type hour business_hours first_seen last_seen result
"@
$qsCols = @('section','account','host','server_set','server_sets','events','days_with_events','first_day_n','last_day_n','change_actions','sql_server','sql_servers',
            'database','databases','db_in_scope','client_host','client_hosts','client_ip','client_ips','application','applications','action_id','action_ids',
            'logins_succeeded','logins_failed','interactive_tool','time','class_type','object_name','succeeded','statement','day_type','hour','business_hours',
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
Save-Derived 'QS' 'QB' 'QB_Connections.csv' @('account','sql_server','database','db_in_scope','client_host','client_ip','application','events','first_seen','last_seen','interactive_tool','result') $sec['QB'] ''
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

$banner['Reconciliation'] = $reconText
Write-Host ("    Accounts assessed: {0} of {1}" -f $Candidates.Count, $ClassRows.Count)

# Windows logons (QE) are matched on the user name without the domain (Windows logs DOMAIN separately).
# Built-in Windows identities (NT AUTHORITY\SYSTEM, NT SERVICE\..., BUILTIN\...) are skipped: their bare names
# (e.g. 'system') would match large numbers of unrelated logons. Every skipped account is printed and recorded.
$AdNames = @(); $QeSkipped = @()
foreach ($acct in @($Candidates)) {
    if ($acct -match '^(nt authority|nt service|builtin|iis apppool|window manager|font driver host)\\') { $QeSkipped += "$acct (built-in Windows identity)" }
    elseif ($acct -match '\\([^\\]+)$' -and $Matches[1] -notmatch '\$$') { $AdNames += $Matches[1].ToLower() }
    else { $QeSkipped += "$acct (SQL login or computer account: no Windows logon check)" }
}
$AdNames = @($AdNames | Select-Object -Unique)
Write-Host ("    Windows logon check (QE) will cover {0} account name(s); not covered: {1}" -f $AdNames.Count, $QeSkipped.Count)
foreach ($k in $QeSkipped) { Write-Host "      not covered by QE: $k" }
$AdSpl   = ConvertTo-SplList $AdNames
$AdTerms = if ($AdNames.Count) { '(' + (($AdNames | ForEach-Object { ConvertTo-SplString $_ }) -join ' OR ') + ')' } else { '"__none__"' }

# ---- QE (step 2): Windows logons
#   1. Read Windows logon events (EventCode 4624) on the in-scope SQL servers for the review period.
#   2. Keep events for the user names of the service accounts, matched on the part after DOMAIN\
#      (Windows logs the domain separately). A name shared by two domains can only add logons,
#      which errs toward keeping an account in review, never toward excluding it.
#   3. For each account: group by logon type, target server and source machine / IP; count events
#      and record the first and last logon.
#   4. Logon types 2 (console), 7 (unlock), 10 (Remote Desktop) and 11 (cached) are marked
#      interactive. A logon with no recorded type is marked for review.
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
}   # end of step 2

# ---- Q_AUDIT (both steps): audit log check
#   1. At the end of the run, read Splunk's own audit log (index _audit) for the searches made by this run.
#   2. For each search: confirm Splunk recorded it as completed, and compare Splunk's result count with
#      the rows the script received.
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
Write-Host ("Script version       : {0} {1}" -f (Split-Path -Leaf $ScriptPath), $ScriptVersion)
Write-Host ("Script SHA256        : {0}" -f $ScriptHash)
Write-Host ("server_sets.csv SHA256: {0}" -f (Get-Sha256 $ServerSetsPath))
Write-Host ("RunManifest.csv SHA256: {0}" -f (Get-Sha256 $manifestCsv))
Write-Host ("Run finished         : {0}  /  {1}Z" -f $runEnd.ToString('yyyy-MM-dd HH:mm:ss zzz'), $runEnd.ToUniversalTime().ToString('yyyy-MM-dd HH:mm:ss'))
Write-Host ("Get-Date             : {0}" -f (Get-Date -Format 'dddd, MMMM d, yyyy h:mm:ss tt K'))
Write-Host ''
if (-not $NoScreenshot) {
    Write-Host 'Run summary screenshot in 5 seconds. Do not touch the keyboard or mouse until the run finishes.' -ForegroundColor Green
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
if ($ranQueries -and -not $Preflight) {
    Write-Host ''
    Write-Host 'Building the workbook in Excel (do not use Excel until this finishes)...'
    try {
        if ($Discover) { if (Test-Path -LiteralPath (Join-Path $RunDir 'Account_Classification.csv')) { Build-Step1Workbook } }
        elseif ($WorkbookCopy -and $Candidates.Count) { Build-Step2Workbook }
    } catch {
        Write-Host "Workbook build failed: $($_.Exception.Message). The CSV evidence is unaffected." -ForegroundColor Yellow
        Write-Host $_.ScriptStackTrace -ForegroundColor Yellow
    }
}

Disable-KeepAwake
Stop-Transcript | Out-Null

# Hash every file in the run folder (including transcript and screenshot) into SHA256SUMS.txt.
# Its hash is printed last and captured in Screenshot_Final.png, which ties the screenshot to every file.
$sumsFile = Join-Path $RunDir 'SHA256SUMS.txt'
$sums = Get-ChildItem -LiteralPath $RunDir -Recurse -File | Where-Object { $_.FullName -ne $sumsFile } | Sort-Object FullName | ForEach-Object {
    "{0}  {1}" -f (Get-Sha256 $_.FullName), $_.FullName.Substring($RunDir.Length + 1)
}
[IO.File]::WriteAllLines($sumsFile, [string[]]$sums, $Utf8NoBom)
Write-Host ''
Write-Host ("SHA256SUMS.txt SHA256: {0}" -f (Get-Sha256 $sumsFile)) -ForegroundColor Cyan
Write-Host ("OVERALL STATUS       : {0}" -f $overall) -ForegroundColor $(if ($script:RunFailed) { 'Red' } else { 'Green' })
Write-Host ("Get-Date             : {0}" -f (Get-Date -Format 'dddd, MMMM d, yyyy h:mm:ss tt K'))
if (-not $NoScreenshot) {
    # Final screenshot: the console showing the SHA256SUMS hash, status and Get-Date. It is taken after
    # SHA256SUMS.txt is written, so it cannot be listed in it; its own hash is printed below.
    try {
        try { [void](New-Object -ComObject WScript.Shell).AppActivate("SvcAcctEvidence_$RunId") } catch { }
        Start-Sleep -Seconds 3
        $hFinal = Save-Screenshot (Join-Path $RunDir 'Screenshot_Final.png')
        Write-Host "Final screenshot saved: Screenshot_Final.png  SHA256 $hFinal" -ForegroundColor Green
    } catch {
        Write-Host "Final screenshot failed: $($_.Exception.Message). Take a full-screen screenshot of this window now." -ForegroundColor Yellow
    }
}
Write-Host 'RUN FINISHED.' -ForegroundColor Green
}
