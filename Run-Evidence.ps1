# =====================================================================================
#  Run-Evidence.ps1  -  settings for the service account exclusion evidence run.
#  Fill in the settings below, save, then run (the Splunk token is read from the
#  SPLUNK_TOKEN environment variable):
#
#    powershell -ExecutionPolicy Bypass -File .\Run-Evidence.ps1 -Preflight   quick check, not evidence
#    powershell -ExecutionPolicy Bypass -File .\Run-Evidence.ps1 -Discover    STEP 1: find accounts + AD lookup
#        -> open SvcAcct_Exclusion_Assessment_<RunId>.xlsx in the new SvcAcctDISCOVERY_ folder,
#           set the Classification for every account, save, and put its path in $AssessWorkbook
#    powershell -ExecutionPolicy Bypass -File .\Run-Evidence.ps1              STEP 2: assess the accounts
#                                                                               classified 'Service account'
#        -> the finished workbook is in the new SvcAcctEvidence_ folder
#  Keep this file, the evidence script, server_sets.csv and the template in the same folder.
#  The script records the SHA256 of itself and of its input files on every run.
# =====================================================================================
param([switch]$Preflight, [switch]$Discover)

$SplunkApiUrl   = 'https://yourcompany.splunkcloud.com:8089'   # REST API address (the one your earlier client used)
$SplunkWebUrl   = 'https://yourcompany.splunkcloud.com'        # address you use in the browser
$WinEventIndex  = 'wineventlog'                                 # index holding WinEventLog:Security
$StartDate      = '2026-09-01'                                  # review period start (inclusive)
$EndDate        = '2026-11-13'                                  # review period end (inclusive)

# Active Directory servers for step 1, by the domain prefix used in account names (DOMAIN\name).
# The value is passed to Get-ADUser -Server. Domains not listed are marked 'Not looked up'.
$AdServers      = @{
    'CORP' = 'corp.company.com'
}

# Step 2 only: the step 1 workbook, after you have set the Classification for every account and saved it
$AssessWorkbook = ''

# ----------------------------------------------------------------- do not edit below
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$params = @{
    SplunkBaseUrl    = $SplunkApiUrl
    SplunkWebUrl     = $SplunkWebUrl
    WinEventIndex    = $WinEventIndex
    ServerSetsCsv    = Join-Path $here 'server_sets.csv'
    WorkbookTemplate = Join-Path $here 'SvcAcct_Exclusion_Assessment_TEMPLATE.xlsx'
    StartDate        = $StartDate
    EndDate          = $EndDate
    OutputRoot       = $here
    AdServers        = $AdServers
    Workbook         = $AssessWorkbook
    Preflight        = [bool]$Preflight
    Discover         = [bool]$Discover
}
& (Join-Path $here 'Collect-SvcAcctExclusionEvidence.ps1') @params
