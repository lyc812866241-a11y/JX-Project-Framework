param(
    [Parameter(Mandatory=$true)][string]$Runner,
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$TaskId,
    [string]$PythonExecutable = 'python'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Runner -PathType Leaf)) { throw 'Runner missing' }
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) { throw 'Project root missing' }
& $PythonExecutable $Runner --root $ProjectRoot gate --task $TaskId
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
exit 0
