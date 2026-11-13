Feature: Install and run the recorder from a Windows installer and a tray icon

  Scenario: Install without a terminal
    Given a Windows user without admin rights who has never installed Python
    When they run Transcribe-Setup.exe and click through it
    Then the installer downloads the components, showing a status message while it works
    And then downloads the Whisper and speaker models in a window with progress bars
    And a "Transcribe" Start menu shortcut exists
    And "Start Transcribe when I sign in" is ticked by default
    And the final page offers to launch Transcribe

  Scenario: Choose the speech model
    When I reach the "Speech model" page
    Then I can choose "large-v3" (selected by default) or "large-v3-turbo"
    And each choice says its download size, its speed and how accurate it is, including for Thai
    When I choose "large-v3-turbo" and finish
    Then the installer downloads large-v3-turbo and not large-v3
    And Transcribe transcribes with large-v3-turbo, both right after install and after I sign in again

  Scenario: Upgrading remembers the model
    Given I installed with "large-v3-turbo"
    When I run a newer installer
    Then "large-v3-turbo" is preselected

  Scenario: Component download fails
    Given there is no internet connection
    When the installer reaches the component download
    Then it says the download failed, names the install log, and suggests running the installer again

  Scenario: The first transcription doesn't wait for a download
    Given Transcribe was installed and the model download succeeded
    When I record a meeting and stop
    Then transcription starts without downloading any model

  Scenario: Model download fails during install
    Given the connection drops during the Whisper download
    When the model download exits with an error
    Then the installer asks "Retry" or "Skip"
    And Retry resumes the download without starting the finished files again
    And Skip finishes the install, and the models then download on the first transcription

  Scenario: Download models again from the command line
    Given the models are already downloaded
    When I run "transcribe download-models"
    Then it finishes quickly without downloading anything

  Scenario: The tray app starts the recorder
    When I launch Transcribe
    Then a grey tray icon appears with the tooltip "Transcribe: idle"
    And the recorder page opens at http://127.0.0.1:8765
    And no console window is shown

  Scenario: Started at sign-in
    Given "Start at login" is on
    When I sign in to Windows
    Then the tray icon appears
    But no browser page opens

  Scenario: Launching a second time
    Given Transcribe is already running
    When I launch Transcribe again
    Then the recorder page opens
    And no second tray icon appears

  Scenario: The page opens in its own app window
    Given Microsoft Edge or Google Chrome is installed
    When the tray opens the recorder page
    Then it opens in an app window, without tabs or an address bar
    And Edge is used when both are installed

  Scenario: No app-capable browser
    Given neither Edge nor Chrome is installed, or it fails to launch
    When the tray opens the recorder page
    Then it opens in the default browser

  Scenario: Port taken by another program
    Given another program is listening on port 8765
    When I launch Transcribe
    Then a notification says port 8765 is in use by another program
    And the tray app exits

  Scenario: The icon shows a live recording
    Given Transcribe is running
    When a recording "Weekly sync" starts, from the page, Claude or the CLI
    Then within 2 seconds the tray icon turns red with the tooltip "Recording: Weekly sync"
    And when the recording stops it turns grey again

  Scenario: Tray menu
    When I click the tray icon
    Then the recorder page opens
    And the right-click menu has "Open recorder", "Start at login", "Connect to Claude Desktop", "Open log", "Open meetings folder" and "Quit"

  Scenario: Toggle start at login
    Given "Start at login" is ticked
    When I click it
    Then the Transcribe Run value is removed from the registry and the item is unticked
    When I click it again
    Then the Run value points at transcribe-tray.exe and the item is ticked

  Scenario: Connect to Claude Desktop
    Given Claude Desktop's config has other mcpServers and preferences
    When I choose "Connect to Claude Desktop"
    Then a "transcribe" mcpServers entry runs "<install dir>\venv\Scripts\transcribe.exe" with args ["mcp"]
    And every other key is unchanged
    And the old file is saved as claude_desktop_config.json.bak
    And a notification tells me to quit Claude Desktop from its tray icon and start it again

  Scenario: Connect when both Claude Desktop builds are installed
    Given both %APPDATA%\Claude and a %LOCALAPPDATA%\Claude-Data\claude_<id> folder exist
    When I choose "Connect to Claude Desktop"
    Then both config files get the transcribe entry

  Scenario: Connect when the config file doesn't exist yet
    Given the %APPDATA%\Claude folder exists without a config file
    When I choose "Connect to Claude Desktop"
    Then the file is created with only the transcribe entry

  Scenario: Connect when the config file is broken
    Given claude_desktop_config.json is not valid JSON
    When I choose "Connect to Claude Desktop"
    Then the file is left untouched
    And a notification says the file couldn't be read and names it

  Scenario: Connect without Claude Desktop installed
    Given no Claude config folder exists
    When I choose "Connect to Claude Desktop"
    Then nothing is written
    And a notification says to install Claude Desktop first

  Scenario: Quit
    When I choose "Quit"
    Then the service stops and the tray icon disappears
    But if a recording is running, the recording is stopped first so its audio files are closed properly
    And on the next start that meeting shows as failed ("interrupted") and can be transcribed again

  Scenario: Uninstall keeps meetings
    When I uninstall Transcribe from Windows Settings
    Then the running tray app is closed
    And the install dir, shortcuts, Run value and TRANSCRIBE_MODEL setting are removed
    And ~/Meetings is kept
    And the Whisper model is kept, and the uninstaller says where it is in case I want to free the space

  Scenario: Release build
    When a v* tag is pushed to GitHub
    Then a Windows workflow builds Transcribe-Setup-<version>.exe and attaches it to a GitHub Release
