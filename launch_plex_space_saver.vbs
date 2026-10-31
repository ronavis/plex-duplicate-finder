Set oWS = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")
strDir = "C:\Users\Ron\.gemini\antigravity-ide\scratch\plex-duplicate-finder"
oWS.CurrentDirectory = strDir

' Check if port 8282 is already responding
On Error Resume Next
Set oHTTP = CreateObject("MSXML2.ServerXMLHTTP.6.0")
oHTTP.Open "GET", "http://localhost:8282/api/scan/status", False
oHTTP.setTimeouts 800, 800, 800, 800
oHTTP.Send

If Err.Number <> 0 Then
    ' Server is not running, launch pythonw in background
    Err.Clear
    oWS.Run """C:\Users\Ron\.gemini\antigravity-ide\tools\python\pythonw.exe"" server.py", 0, False
    WScript.Sleep 1500
End If
On Error GoTo 0

' Open the web interface in default browser
oWS.Run "http://localhost:8282"
