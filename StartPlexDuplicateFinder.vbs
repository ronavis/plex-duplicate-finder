Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strScriptDir

If objFSO.FileExists(strScriptDir & "\.venv\Scripts\python.exe") Then
    objShell.Run """" & strScriptDir & "\.venv\Scripts\python.exe"" server.py", 0, False
Else
    objShell.Run "python server.py", 0, False
End If
