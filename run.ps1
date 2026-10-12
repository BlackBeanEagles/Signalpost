param(
    [Parameter(Position=0)]
    [ValidateSet("profile", "batch", "validate")]
    [string]$Command = "profile",
    [Parameter(Position=1)]
    [string]$OrganizationNumber = "923609016",
    [int]$Count = 1000
)

if (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
} else {
    throw "Python 3.10 or newer is required. Install Python and rerun this command."
}

if ($Command -eq "batch") {
    & $Python -m signalpost batch --count $Count --output data/profiles.jsonl
} elseif ($Command -eq "validate") {
    & $Python -m signalpost validate data/profiles.jsonl --minimum 1000
} else {
    & $Python -m signalpost profile $OrganizationNumber --format json
}

