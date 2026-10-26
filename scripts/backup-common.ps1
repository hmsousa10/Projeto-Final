function Read-BoundedBytes([string]$Path,[int]$Limit) {
  Assert-PlainPath $Path
  $taskRead = [IO.File]::Open($Path,'Open','Read','Read')
  $taskMemory = New-Object IO.MemoryStream
  try {
    if ($taskRead.Length -gt $Limit) { throw 'Ficheiro acima do limite.' }
    $taskBuffer = New-Object byte[] 65536
    while (($taskCount = $taskRead.Read($taskBuffer,0,$taskBuffer.Length)) -gt 0) {
      if ($taskMemory.Length + $taskCount -gt $Limit) { throw 'Ficheiro acima do limite.' }
      $taskMemory.Write($taskBuffer,0,$taskCount)
    }
    return ,$taskMemory.ToArray()
  } finally { $taskRead.Dispose(); $taskMemory.Dispose() }
}

function Assert-PlainPath([string]$Path) {
  $taskCandidate = [System.IO.Path]::GetFullPath($Path)
  while ($taskCandidate) {
    if (Test-Path -LiteralPath $taskCandidate) {
      $taskItem = Get-Item -LiteralPath $taskCandidate -Force
      if ($taskItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw 'Nao sao aceites junctions ou ligacoes simbolicas.'
      }
    }
    $taskCandidate = [System.IO.Path]::GetDirectoryName($taskCandidate)
  }
}

function Protect-Directory([string]$Path) {
  Assert-PlainPath $Path
  [System.IO.Directory]::CreateDirectory($Path) | Out-Null
  # Build a DACL only: never request privileges to rewrite owner or audit/SACL.
  $taskAcl = New-Object System.Security.AccessControl.DirectorySecurity
  $taskAcl.SetAccessRuleProtection($true, $false)
  $taskSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
  $taskInheritance = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
  foreach ($taskIdentity in @($taskSid, [System.Security.Principal.SecurityIdentifier]'S-1-5-18')) {
    $taskRule = New-Object System.Security.AccessControl.FileSystemAccessRule($taskIdentity,'FullControl',$taskInheritance,'None','Allow')
    $taskAcl.AddAccessRule($taskRule)
  }
  $taskDirectory = New-Object System.IO.DirectoryInfo($Path)
  if ('System.IO.FileSystemAclExtensions' -as [type]) {
    [System.IO.FileSystemAclExtensions]::SetAccessControl($taskDirectory,$taskAcl)
  } else {
    $taskDirectory.SetAccessControl($taskAcl)
  }
}

