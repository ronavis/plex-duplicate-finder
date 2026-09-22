Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = "C:\Users\Ron\.gemini\antigravity-ide\scratch\plex-duplicate-finder"
objShell.Run "python server.py", 0, False
