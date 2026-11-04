param(
    [ValidatePattern('^COM[1-9][0-9]*$')]
    [string]$SerialPort = 'COM9',
    [ValidateRange(1, 4000000)]
    [int]$BaudRate = 115200,
    [ValidateRange(1, 65535)]
    [int]$Port = 8765,
    [switch]$Preview,
    [switch]$Check,
    [string]$PythonPath = ''
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $localPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (Test-Path -LiteralPath $localPython -PathType Leaf) { $PythonPath = $localPython }
    else { $PythonPath = (Get-Command python -ErrorAction Stop).Source }
}
$options = @{ SerialPort = $SerialPort; BaudRate = $BaudRate; Port = $Port; PythonPath = $PythonPath }
if ($Preview) { $options.Preview = $true }
if ($Check) { $options.Check = $true }
& (Join-Path $PSScriptRoot 'pc_vision_1_/pc_vision/start_game.ps1') @options
exit $LASTEXITCODE
