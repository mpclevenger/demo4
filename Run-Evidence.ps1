# =====================================================================================
#  Run-Evidence.ps1  -  settings for the service account exclusion evidence run.
#  Paste your values between the quotes below, save, then run:
#      powershell -ExecutionPolicy Bypass -File .\Run-Evidence.ps1 -Preflight   (quick check, not evidence)
#      powershell -ExecutionPolicy Bypass -File .\Run-Evidence.ps1              (evidence run)
#  The Splunk token is read from the SPLUNK_TOKEN environment variable.
#  Keep this file, the evidence script, server_sets.csv and the workbook
#  template in the same folder. The run folder is created here too.
#
#  The script records the SHA256 of itself and of server_sets.csv on every run.
#  Every value below is printed in the run banner and transcript.
# =====================================================================================
param([switch]$Preflight)

$SplunkApiUrl   = 'https://yourcompany.splunkcloud.com:8089'   # REST API address (the one your earlier client used)
$SplunkWebUrl   = 'https://yourcompany.splunkcloud.com'        # address you use in the browser
$WinEventIndex  = 'wineventlog'                                 # index holding WinEventLog:Security
$StartDate      = '2026-09-01'                                  # review period start (inclusive)
$EndDate        = '2026-11-13'                                  # review period end (inclusive)

# ----------------------------------------------------------------- do not edit below
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$params = @{
    SplunkBaseUrl    = $SplunkApiUrl
    SplunkWebUrl     = $SplunkWebUrl
    WinEventIndex    = $WinEventIndex
    ServerSetsCsv    = Join-Path $here 'server_sets.csv'
    WorkbookTemplate = Join-Path $here 'SvcAcct_Exclusion_Evidence_TEMPLATE.xlsx'
    StartDate        = $StartDate
    EndDate          = $EndDate
    OutputRoot       = $here
    Preflight        = [bool]$Preflight
}
& (Join-Path $here 'Collect-SvcAcctExclusionEvidence.ps1') @params
