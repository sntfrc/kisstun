set appPath to POSIX path of (path to me)
set resourceFolder to appPath & "Contents/Resources"
set commandToRun to "if ! brew list --formula direwolf >/dev/null 2>&1; then brew install direwolf; fi; sudo python3 ./kisstun.py"

tell application "Terminal"
    activate
    do script "clear && cd " & quoted form of resourceFolder & " && " & commandToRun & " || exit"
end tell

