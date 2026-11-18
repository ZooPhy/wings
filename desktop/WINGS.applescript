on normalizeAccessKey(rawKey)
    -- Work with numeric code points, never locale-sensitive text comparisons.
    -- Preserve every printable ASCII character, including hyphens and case.
    if (count characters of rawKey) is 0 then error "Paste the access key, or choose Add later."
    set keyCodes to id of (rawKey as text)
    if class of keyCodes is integer then set keyCodes to {keyCodes}
    set edgeWhitespace to {9, 10, 11, 12, 13, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288, 65279}
    set firstCode to 1
    set lastCode to count keyCodes
    repeat while firstCode <= lastCode
        if (item firstCode of keyCodes) is not in edgeWhitespace then exit repeat
        set firstCode to firstCode + 1
    end repeat
    repeat while lastCode >= firstCode
        if (item lastCode of keyCodes) is not in edgeWhitespace then exit repeat
        set lastCode to lastCode - 1
    end repeat
    if firstCode > lastCode then error "Paste the access key, or choose Add later."
    set keyCodes to items firstCode thru lastCode of keyCodes
    if (count keyCodes) > 4096 then error "That entry is too long for an access key. Paste only the key, or choose Add later."
    repeat with codeValue in keyCodes
        set codeNumber to contents of codeValue
        if codeNumber < 33 or codeNumber > 126 then error "Hyphens (-) are allowed. The pasted text contains an internal space, line break, or non-ASCII character. Copy only the key directly from eBird, or choose Add later."
    end repeat
    return string id keyCodes
end normalizeAccessKey

on markEBirdPrompt(workspace)
    set settingsPath to workspace & "/.desktop"
    do shell script "umask 077; /bin/mkdir -p " & quoted form of settingsPath & "; : > " & quoted form of (settingsPath & "/ebirdst-prompted")
end markEBirdPrompt

on editEBirdKey(workspace)
    repeat
        set answer to display dialog "Optional: eBird Status and Trends access key for seasonal bird abundance. This is separate from the general eBird API key.\n\nChoose Add later to continue without new abundance downloads. Cached data remain usable. You can add or update the key under Settings at any time." default answer "" buttons {"Cancel", "Add later", "Save key"} default button "Save key" with title "eBird abundance access" with hidden answer
        if button returned of answer is "Add later" then
            my markEBirdPrompt(workspace)
            return
        end if
        try
            set accessKey to my normalizeAccessKey(text returned of answer)
            exit repeat
        on error validationMessage
            set correction to display dialog validationMessage buttons {"Add later", "Try again"} default button "Try again" with title "eBird abundance access"
            if button returned of correction is "Add later" then
                my markEBirdPrompt(workspace)
                return
            end if
        end try
    end repeat
    set settingsPath to workspace & "/.desktop"
    do shell script "umask 077; /bin/mkdir -p " & quoted form of settingsPath
    set temporaryPath to do shell script "/usr/bin/mktemp " & quoted form of (settingsPath & "/.ebirdst-key.XXXXXX")
    try
        -- Native file I/O keeps the key out of shell commands and process args.
        set keyFile to open for access (POSIX file temporaryPath) with write permission
        set eof keyFile to 0
        write accessKey to keyFile as «class utf8»
        close access keyFile
        do shell script "/bin/chmod 600 " & quoted form of temporaryPath & " && /bin/mv -f " & quoted form of temporaryPath & " " & quoted form of (settingsPath & "/ebirdst-access-key")
    on error
        try
            close access keyFile
        end try
        do shell script "/bin/rm -f " & quoted form of temporaryPath
        error "The eBird key could not be saved. Check that the workspace is writable."
    end try
    set accessKey to ""
    my markEBirdPrompt(workspace)
    display dialog "Key saved. New context preparations and analysis attempts will use it automatically. Existing jobs keep their current settings.\n\nIf abundance preparation previously reported missing access, prepare context again. The key will be checked by eBird when a download is requested." buttons {"OK"} with title "eBird abundance access"
end editEBirdKey

on normalizeContactEmail(rawEmail)
    set codes to id of (rawEmail as text)
    if class of codes is integer then set codes to {codes}
    set whitespaceCodes to {9, 10, 11, 12, 13, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288, 65279}
    set firstCode to 1
    set lastCode to count codes
    repeat while firstCode <= lastCode
        if (item firstCode of codes) is not in whitespaceCodes then exit repeat
        set firstCode to firstCode + 1
    end repeat
    repeat while lastCode >= firstCode
        if (item lastCode of codes) is not in whitespaceCodes then exit repeat
        set lastCode to lastCode - 1
    end repeat
    set invalidMessage to "Enter a contact email such as name@example.org, or choose Add later."
    if firstCode > lastCode then error invalidMessage
    set codes to items firstCode thru lastCode of codes
    if (count codes) > 320 then error invalidMessage
    set atIndex to 0
    repeat with i from 1 to count codes
        set c to item i of codes
        if c is 64 then
            if atIndex is not 0 then error invalidMessage
            set atIndex to i
        else
            set isLetter to ((c >= 65 and c <= 90) or (c >= 97 and c <= 122))
            set isDigit to (c >= 48 and c <= 57)
            if not isLetter and not isDigit and c is not in {46, 95, 37, 43, 45} then error invalidMessage
        end if
    end repeat
    if atIndex < 2 or atIndex >= (count codes) then error invalidMessage
    set dotIndex to 0
    repeat with i from (atIndex + 1) to count codes
        set c to item i of codes
        if c is in {95, 37, 43} then error invalidMessage
        if c is 46 then set dotIndex to i
    end repeat
    if dotIndex <= (atIndex + 1) or ((count codes) - dotIndex) < 2 then error invalidMessage
    repeat with i from (dotIndex + 1) to count codes
        set c to item i of codes
        if not ((c >= 65 and c <= 90) or (c >= 97 and c <= 122)) then error invalidMessage
    end repeat
    return string id codes
end normalizeContactEmail

on markNCBIPrompt(workspace)
    do shell script "umask 077; /bin/mkdir -p " & quoted form of (workspace & "/.desktop") & "; : > " & quoted form of (workspace & "/.desktop/ncbi-prompted")
end markNCBIPrompt

on editNCBIEmail(workspace)
    repeat
        set answer to display dialog "Optional: contact email for NCBI reference requests. Phylodynamics needs it when retrieving references.\n\nChoose Add later to continue setting up WINGS. You can add it under Settings → Add or update NCBI email." default answer "" buttons {"Cancel", "Add later", "Save email"} default button "Save email" with title "Reference retrieval"
        if button returned of answer is "Add later" then
            my markNCBIPrompt(workspace)
            return
        end if
        try
            set emailAddress to my normalizeContactEmail(text returned of answer)
            exit repeat
        on error validationMessage
            set correction to display dialog validationMessage buttons {"Add later", "Try again"} default button "Try again" with title "Reference retrieval"
            if button returned of correction is "Add later" then
                my markNCBIPrompt(workspace)
                return
            end if
        end try
    end repeat
    set settingsPath to workspace & "/.desktop"
    do shell script "umask 077; /bin/mkdir -p " & quoted form of settingsPath
    set temporaryPath to do shell script "/usr/bin/mktemp " & quoted form of (settingsPath & "/.ncbi-email.XXXXXX")
    try
        set emailFile to open for access (POSIX file temporaryPath) with write permission
        set eof emailFile to 0
        write emailAddress to emailFile as «class utf8»
        close access emailFile
        do shell script "/bin/chmod 600 " & quoted form of temporaryPath & " && /bin/mv -f " & quoted form of temporaryPath & " " & quoted form of (settingsPath & "/ncbi-email")
    on error
        try
            close access emailFile
        end try
        do shell script "/bin/rm -f " & quoted form of temporaryPath
        error "The contact email could not be saved. Check that the workspace is writable."
    end try
    set emailAddress to ""
    my markNCBIPrompt(workspace)
    display dialog "Contact email saved. Refresh the WINGS browser page. New jobs will use it; existing jobs keep their settings." buttons {"OK"} with title "Reference retrieval"
end editNCBIEmail

on manageSharedFolders(workspace)
    set settingsPath to workspace & "/.desktop"
    set listPath to settingsPath & "/shared-folders"
    set sharedFolders to {}
    try
        set fileContents to read (POSIX file listPath) as «class utf8»
        repeat with entry in paragraphs of fileContents
            if (contents of entry) is not "" then set end of sharedFolders to contents of entry
        end repeat
    end try
    set action to choose from list {"Add folder", "Remove folder"} with title "Shared input folders" with prompt "Home and external drives are available automatically. Add another folder for read-only access from WINGS."
    if action is false then return
    if item 1 of action is "Add folder" then
        set chosenPath to POSIX path of (choose folder with prompt "Share this folder with WINGS for read-only input access:")
        if chosenPath ends with "/" and chosenPath is not "/" then set chosenPath to text 1 thru -2 of chosenPath
        if chosenPath is "/" or chosenPath contains "," or chosenPath contains ":" or chosenPath contains linefeed or chosenPath contains return then
            display dialog "Choose a data folder without commas, colons or line breaks." buttons {"OK"} with title "Shared input folders"
            return
        end if
        if chosenPath is not in sharedFolders then set end of sharedFolders to chosenPath
    else
        if (count sharedFolders) is 0 then
            display dialog "No additional folders are shared. Home and external drives are available automatically." buttons {"OK"} with title "Shared input folders"
            return
        end if
        set removed to choose from list sharedFolders with title "Remove shared folder" with prompt "Remove access after restarting WINGS. This does not delete files."
        if removed is false then return
        set remainingFolders to {}
        repeat with entry in sharedFolders
            if (contents of entry) is not (item 1 of removed) then set end of remainingFolders to contents of entry
        end repeat
        set sharedFolders to remainingFolders
    end if
    set savedText to ""
    repeat with entry in sharedFolders
        set savedText to savedText & (contents of entry) & linefeed
    end repeat
    do shell script "umask 077; /bin/mkdir -p " & quoted form of settingsPath
    set temporaryPath to do shell script "/usr/bin/mktemp " & quoted form of (settingsPath & "/.shared-folders.XXXXXX")
    try
        set listFile to open for access (POSIX file temporaryPath) with write permission
        set eof listFile to 0
        write savedText to listFile as «class utf8»
        close access listFile
        do shell script "/bin/chmod 600 " & quoted form of temporaryPath & " && /bin/mv -f " & quoted form of temporaryPath & " " & quoted form of listPath
    on error
        try
            close access listFile
        end try
        do shell script "/bin/rm -f " & quoted form of temporaryPath
        error "Shared folders could not be saved. Check that the workspace is writable."
    end try
    display dialog "Shared folders saved. Finish active jobs, then use Settings → Stop WINGS service and reopen WINGS to apply this change." buttons {"OK"} with title "Shared input folders"
end manageSharedFolders

on checkOllama(backend, workspace)
    try
        with timeout of 20 seconds
            set resultText to do shell script "/bin/bash " & backend & " ollama-check " & quoted form of workspace
        end timeout
        display dialog resultText buttons {"OK"} with title "Ollama connection"
    on error messageText number errorNumber
        if errorNumber is not -128 then
            display dialog messageText buttons {"OK"} with title "Ollama connection"
        end if
    end try
end checkOllama

on configureOllama(resourcePath, backend, workspace)
    set serverAddress to "http://localhost:11434"
    set modelName to "gpt-oss:20b"
    try
        set serverAddress to do shell script "/usr/bin/sed -n '1p' " & quoted form of (workspace & "/.desktop/ollama.conf")
        set modelName to do shell script "/usr/bin/sed -n '2p' " & quoted form of (workspace & "/.desktop/ollama.conf")
    end try
    set serverAddress to text returned of (display dialog "Ollama server on this Mac. Use localhost and the port shown by Ollama. WINGS handles the connection from its analysis container." default answer serverAddress buttons {"Cancel", "Continue"} default button "Continue" with title "Configure Ollama")
    set modelDialog to display dialog "Default model name, exactly as installed in Ollama. Briefings remain optional for each job. Save and check verifies availability; it does not download a model or generate text." default answer modelName buttons {"Cancel", "Save", "Save and check"} default button "Save and check" with title "Ollama model"
    set modelName to text returned of modelDialog
    set resultText to do shell script "/bin/bash " & quoted form of (resourcePath & "/ollama-settings.sh") & " " & quoted form of workspace & " " & quoted form of serverAddress & " " & quoted form of modelName
    if button returned of modelDialog is "Save and check" then
        my checkOllama(backend, workspace)
    else
        display dialog resultText buttons {"OK"} with title "Ollama settings saved"
    end if
end configureOllama

on settingsActions(category)
    if category is "NCBI & eBird access" then return {"Add or update NCBI email", "Add or update eBird access key", "Get an eBird access key", "Remove eBird access key"}
    if category is "Ollama" then return {"Configure Ollama", "Check Ollama connection"}
    if category is "Folders and storage" then return {"Share a folder with WINGS", "Open workspace"}
    if category is "Setup and diagnostics" then return {"View setup progress", "Export installation diagnostics"}
    return {}
end settingsActions

on chooseSettingsCategory()
    set selected to choose from list {"NCBI & eBird access", "Ollama", "Folders and storage", "Setup and diagnostics", "Stop WINGS service"} with title "WINGS settings" with prompt "Choose a settings category." OK button name "Select" cancel button name "Done"
    if selected is false then return false
    return item 1 of selected
end chooseSettingsCategory

on chooseSettingsAction(category)
    set options to my settingsActions(category)
    set selected to choose from list options with title category with prompt "Choose an action. Back returns to all settings." OK button name "Select" cancel button name "Back"
    if selected is false then return false
    return item 1 of selected
end chooseSettingsAction

on settingsError(messageText)
    display dialog messageText buttons {"OK"} with title "WINGS settings"
end settingsError

on showWINGSSettings(resourcePath, backend, workspace)
    repeat
        set category to my chooseSettingsCategory()
        if category is false then return
        if category is "Stop WINGS service" then
            try
                my runSettingsAction(category, resourcePath, backend, workspace)
                return
            on error messageText number errorNumber
                if errorNumber is not -128 then my settingsError(messageText)
            end try
        else
            repeat
                set action to my chooseSettingsAction(category)
                if action is false then exit repeat
                try
                    my runSettingsAction(action, resourcePath, backend, workspace)
                on error messageText number errorNumber
                    -- Saving, cancelling, or a recoverable error keeps settings open.
                    if errorNumber is not -128 then my settingsError(messageText)
                end try
            end repeat
        end if
    end repeat
end showWINGSSettings


on runSettingsAction(action, resourcePath, backend, workspace)
        if action is "Configure Ollama" then
            my configureOllama(resourcePath, backend, workspace)
        else if action is "Check Ollama connection" then
            my checkOllama(backend, workspace)
        else if action is "View setup progress" then
            try
                set progressPage to do shell script "/bin/cat " & quoted form of (workspace & "/.desktop/setup-page")
                do shell script "/usr/bin/open " & quoted form of progressPage
            on error
                display dialog "No setup progress page is available yet. Choose Open WINGS to begin." buttons {"OK"} with title "WINGS setup"
            end try
        else if action is "Share a folder with WINGS" then
            my manageSharedFolders(workspace)
        else if action is "Add or update NCBI email" then
            my editNCBIEmail(workspace)
        else if action is "Add or update eBird access key" then
            my editEBirdKey(workspace)
        else if action is "Get an eBird access key" then
            open location "https://ebird.org/st/request"
        else if action is "Remove eBird access key" then
            display dialog "Remove the saved key? New abundance downloads will require a key again. Cached data and existing jobs will remain available." buttons {"Cancel", "Remove key"} default button "Cancel" with title "eBird abundance access"
            do shell script "/bin/rm -f " & quoted form of (workspace & "/.desktop/ebirdst-access-key")
            my markEBirdPrompt(workspace)
        else if action is "Open workspace" then
            do shell script "/bin/mkdir -p " & quoted form of workspace
            do shell script "/usr/bin/open " & quoted form of workspace
        else if action is "Export installation diagnostics" then
            try
                set reportPath to do shell script "/bin/bash " & backend & " diagnostics " & quoted form of workspace
                do shell script "/usr/bin/open -R " & quoted form of reportPath
            on error messageText
                display dialog messageText buttons {"OK"} with title "WINGS diagnostics"
            end try
        else if action is "Stop WINGS service" then
            display dialog "Stop WINGS? Finish or stop every analysis in the browser first. Stopping the service interrupts workflow management; assembly containers already started may continue. Your saved files will remain." buttons {"Cancel", "Stop service"} default button "Cancel" with title "Stop WINGS"
            do shell script "/bin/bash " & backend & " stop " & quoted form of workspace
        end if
end runSettingsAction

on chooseWINGSAction()
    return button returned of (display dialog "Run WINGS on this Mac. Your data and analyses stay in your workspace. Docker Desktop must be installed and running." buttons {"Quit", "Settings", "Open WINGS"} default button "Open WINGS" with title "WINGS Desktop")
end chooseWINGSAction

on launcherMenu(resourcePath, backend, workspace)
    repeat
        set choice to my chooseWINGSAction()
        if choice is "Quit" then return false
        if choice is "Open WINGS" then return true
        try
            my showWINGSSettings(resourcePath, backend, workspace)
        on error messageText number errorNumber
            -- Cancel returns to the launcher, including native folder dialogs.
            if errorNumber is not -128 then
                display dialog messageText buttons {"OK"} with title "WINGS settings"
            end if
        end try
    end repeat
end launcherMenu

on run
    set appPath to POSIX path of (path to me)
    set resourcePath to appPath & "Contents/Resources/"
    -- The uncompiled preview shim supplies the resource directory explicitly.
    try
        set overridePath to system attribute "WINGS_APP_RESOURCES"
        if overridePath is not "" then set resourcePath to overridePath & "/"
    end try
    set backend to quoted form of (resourcePath & "desktop.sh")
    set prefs to (POSIX path of (path to application support from user domain)) & "WINGS Desktop/"
    do shell script "/bin/mkdir -p " & quoted form of prefs
    set workspaceFile to prefs & "workspace.txt"
    set workspace to ""
    try
        set workspace to do shell script "/bin/cat " & quoted form of workspaceFile
    end try
    if workspace is "" then
        display dialog "WINGS keeps run data, reference downloads, and its analysis runtime in a dedicated workspace. First setup needs internet access and substantial disk space.\n\nChoose where to create your WINGS Workspace folder." buttons {"Cancel", "Choose folder"} default button "Choose folder" with title "Set up WINGS"
        set parentFolder to POSIX path of (choose folder with prompt "Create WINGS Workspace inside this folder:")
        set workspace to parentFolder & "WINGS Workspace"
        do shell script "/usr/bin/printf '%s\\n' " & quoted form of workspace & " > " & quoted form of workspaceFile
    end if
    if not my launcherMenu(resourcePath, backend, workspace) then return
    try
        do shell script "test -e " & quoted form of (workspace & "/.desktop/ebirdst-prompted") & " || test -s " & quoted form of (workspace & "/.desktop/ebirdst-access-key")
    on error
        my editEBirdKey(workspace)
    end try
    try
        do shell script "/bin/bash " & backend & " doctor"
    on error
        set choice to button returned of (display dialog "WINGS could not connect to Docker Desktop. Install it if needed, then start it and wait until Docker is ready." buttons {"Cancel", "Download Docker", "Start Docker"} default button "Start Docker" with title "Docker Desktop required")
        if choice is "Cancel" then return
        if choice is "Download Docker" then
            open location "https://docs.docker.com/desktop/setup/install/mac-install/"
            return
        end if
        try
            do shell script "/usr/bin/open -a Docker"
        on error
            display dialog "Docker Desktop was not found. Install Docker Desktop and reopen WINGS." buttons {"OK"}
            return
        end try
        set dockerReady to false
        repeat 120 times
            delay 1
            try
                do shell script "/bin/bash " & backend & " doctor"
                set dockerReady to true
                exit repeat
            end try
        end repeat
        if not dockerReady then
            display dialog "Docker Desktop is still starting. Reopen WINGS when Docker is ready." buttons {"OK"}
            return
        end if
    end try
    set emailAddress to ""
    try
        do shell script "test -e " & quoted form of (workspace & "/.desktop/ncbi-prompted") & " || test -s " & quoted form of (workspace & "/.desktop/ncbi-email")
    on error
        my editNCBIEmail(workspace)
    end try
    do shell script "/bin/mkdir -p " & quoted form of (workspace & "/logs") & " " & quoted form of (workspace & "/.desktop")
    set taskID to do shell script "/usr/bin/uuidgen"
    set donePath to workspace & "/.desktop/launch-" & taskID & ".done"
    set logPath to workspace & "/logs/setup-" & taskID & ".log"
    -- Detach the coordinator before returning: never wait for setup
    -- in the process that displayed the email prompt.
    set sessionCommand to "/bin/bash " & quoted form of (resourcePath & "/setup-session.sh") & " " & quoted form of resourcePath & " " & quoted form of workspace & " " & quoted form of emailAddress & " " & quoted form of donePath & " " & quoted form of logPath
    do shell script "/usr/bin/nohup " & sessionCommand & " > " & quoted form of logPath & " 2>&1 < /dev/null &"
    set emailAddress to ""
    return
end run
