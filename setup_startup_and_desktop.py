import os
import sys
import subprocess
import urllib.request
import time

def main():
    finder_dir = r"C:\Users\Ron\.gemini\antigravity-ide\scratch\plex-duplicate-finder"
    pythonw_path = r"C:\Users\Ron\.gemini\antigravity-ide\tools\python\pythonw.exe"
    python_path = r"C:\Users\Ron\.gemini\antigravity-ide\tools\python\python.exe"
    ico_path = os.path.join(finder_dir, "plex_space_saver.ico")
    
    desktop_dir = r"C:\Users\Ron\Desktop"
    startup_dir = r"C:\Users\Ron\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    
    # 1. Create launch_plex_space_saver.vbs (for Desktop shortcut: starts server if needed & opens browser)
    launcher_vbs = os.path.join(finder_dir, "launch_plex_space_saver.vbs")
    vbs_content = f'''Set oWS = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")
strDir = "{finder_dir}"
oWS.CurrentDirectory = strDir

' Check if port 8282 is already responding
On Error Resume Next
Set oHTTP = CreateObject("MSXML2.ServerXMLHTTP.6.0")
oHTTP.Open "GET", "http://localhost:8282/api/status", False
oHTTP.setTimeouts 800, 800, 800, 800
oHTTP.Send

If Err.Number <> 0 Then
    ' Server is not running, launch pythonw in background
    Err.Clear
    oWS.Run """{pythonw_path}"" server.py", 0, False
    WScript.Sleep 1500
End If
On Error GoTo 0

' Open the web interface in default browser
oWS.Run "http://localhost:8282"
'''
    with open(launcher_vbs, "w", encoding="utf-8") as f:
        f.write(vbs_content)
    print("Created desktop launcher VBS:", launcher_vbs)
    
    # 2. Create autostart VBS in Windows Startup folder (starts server silently in background on Windows boot)
    startup_vbs = os.path.join(startup_dir, "StartPlexSpaceSaver.vbs")
    startup_vbs_content = f'''Set oWS = CreateObject("WScript.Shell")
strDir = "{finder_dir}"
oWS.CurrentDirectory = strDir
oWS.Run """{pythonw_path}"" server.py", 0, False
'''
    with open(startup_vbs, "w", encoding="utf-8") as f:
        f.write(startup_vbs_content)
    print("Created Windows Startup launcher:", startup_vbs)
    
    # 3. Create the Desktop Shortcut using VBScript helper
    shortcut_vbs_script = os.path.join(finder_dir, "create_shortcut.vbs")
    shortcut_path = os.path.join(desktop_dir, "Plex Space Saver.lnk")
    
    make_shortcut_vbs = f'''Set oWS = CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "wscript.exe"
oLink.Arguments = """{launcher_vbs}"""
oLink.WorkingDirectory = "{finder_dir}"
oLink.WindowStyle = 1
oLink.IconLocation = "{ico_path},0"
oLink.Description = "Plex Space Saver & Reclaimer - Multi-Drive Deduplicator"
oLink.Save
'''
    with open(shortcut_vbs_script, "w", encoding="utf-8") as f:
        f.write(make_shortcut_vbs)
        
    res = subprocess.run(["cscript", "//nologo", shortcut_vbs_script], capture_output=True, text=True)
    print("Desktop shortcut creation result:", res.returncode, res.stdout, res.stderr)
    
    # Clean up helper
    if os.path.exists(shortcut_vbs_script):
        try: os.remove(shortcut_vbs_script)
        except: pass
        
    # 4. Start the server right now!
    print("Starting Plex Space Saver server right now...")
    # Clean up any stale process first or let server.py do it
    subprocess.Popen([pythonw_path, "server.py"], cwd=finder_dir)
    
    # 5. Verify server is running
    time.sleep(2)
    for attempt in range(5):
        try:
            req = urllib.request.Request("http://localhost:8282/api/status")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = resp.read().decode('utf-8')
                print("Server is UP and RESPONDING on http://localhost:8282!")
                print("Status response:", data[:200])
                break
        except Exception as e:
            print(f"Waiting for server (attempt {attempt+1}): {e}")
            time.sleep(1)

if __name__ == "__main__":
    main()

