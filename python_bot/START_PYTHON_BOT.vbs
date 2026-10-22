Option Explicit
Dim sh, fso, folder, script, shellCmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(folder, "START_PYTHON_BOT.pyw")
sh.CurrentDirectory = folder
If Not fso.FileExists(script) Then
    MsgBox "Khong tim thay START_PYTHON_BOT.pyw", vbCritical, "Python Bot"
    WScript.Quit 1
End If
' Use pythonw (GUI interpreter), not python or cmd /c.
shellCmd = "pythonw.exe " & Chr(34) & script & Chr(34)
On Error Resume Next
Err.Clear
sh.Run shellCmd, 0, False
If Err.Number <> 0 Then
    Err.Clear
    sh.Run "pyw.exe -3 " & Chr(34) & script & Chr(34), 0, False
    If Err.Number <> 0 Then
        MsgBox "Khong tim thay pythonw.exe / pyw.exe. Hay cai Python 3 va chon Add Python to PATH.", vbCritical, "Python Bot"
    End If
End If
On Error GoTo 0
