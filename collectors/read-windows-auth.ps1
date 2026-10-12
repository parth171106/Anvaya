param(
    [long]$AfterRecordId = 0,
    [Parameter(Mandatory = $true)][string]$SinceUtc,
    [ValidateRange(1, 1000)][int]$MaxEvents = 200
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    # Check permissions separately: an inaccessible log must never look like an empty log.
    $null = Get-WinEvent -ListLog Security -ErrorAction Stop
    $since = [DateTimeOffset]::Parse($SinceUtc).UtcDateTime.ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    $latest = Get-WinEvent -LogName Security -MaxEvents 1 -ErrorAction Stop
    if ($AfterRecordId -gt $latest.RecordId) {
        throw 'Security log record IDs moved backwards. Preserve the checkpoint and investigate a log clear before restarting collection with a new checkpoint.'
    }
    $xpath = "*[System[(EventID=4624 or EventID=4625) and EventRecordID > $AfterRecordId and TimeCreated[@SystemTime >= '$since']]]"
    $events = @()
    try {
        $events = @(Get-WinEvent -LogName Security -FilterXPath $xpath -Oldest -MaxEvents $MaxEvents -ErrorAction Stop)
    } catch {
        if ($_.FullyQualifiedErrorId -notlike 'NoMatchingEventsFound*') { throw }
    }
    ConvertTo-Json -InputObject @($events | ForEach-Object { $_.ToXml() }) -Compress
} catch {
    [Console]::Error.WriteLine("Cannot read Windows sign-in events: $($_.Exception.Message) Run the collector from a PowerShell session with permission to read the Security log (usually Run as administrator).")
    exit 1
}
