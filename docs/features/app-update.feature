Feature: App version and updates
  So that I run the newest Transcribe without hunting for installers
  As someone who installed Transcribe with the Windows installer
  I want to see my version, be told about a newer one, and install it in one step

  Background:
    Given Transcribe 0.3.1 is installed

  Scenario: The page shows the installed version
    When I open the recorder page
    Then it shows "Transcribe 0.3.1"

  Scenario: A newer release is offered
    Given release 0.4.0 has a setup file
    When the update check runs
    Then the page offers "Update to 0.4.0"
    And the tray shows one notification about 0.4.0
    And the tray menu offers "Install update 0.4.0"

  Scenario: The same release is not offered again
    Given release 0.3.1 has a setup file
    When the update check runs
    Then the page says Transcribe is up to date
    And the tray shows no notification

  Scenario: A build made after a tag counts as that tag
    Given Transcribe 0.3.1-4-gabc1234 is installed
    And release 0.3.1 has a setup file
    When the update check runs
    Then no update is offered

  Scenario: A release without a setup file is ignored
    Given release 0.4.0 has no setup file
    When the update check runs
    Then no update is offered

  Scenario: The tray notifies once per update
    Given release 0.4.0 has a setup file
    When the update check runs twice
    Then the tray shows one notification

  Scenario: Offline, the check fails quietly
    Given GitHub can't be reached
    When the update check runs
    Then the page says it couldn't check for updates
    And recording still works

  Scenario: Running from a git checkout
    Given Transcribe runs from source with no VERSION file
    When I open the recorder page
    Then it shows "Transcribe dev"
    And GitHub is not asked for releases

  Scenario: Installing an update
    Given release 0.4.0 has a setup file with a matching SHA-256
    When I choose "Update to 0.4.0"
    Then the setup file is downloaded and its checksum verified
    And the setup wizard starts

  Scenario: The update option is disabled while recording
    Given release 0.4.0 has a setup file
    And a recording is running
    Then the page's "Update to 0.4.0" button is disabled
    And the tray's "Install update 0.4.0" item is disabled
    And when the recording stops, both are enabled again

  Scenario: Installing is refused while recording
    Given release 0.4.0 has a setup file
    And a recording is running
    When the service is asked to install the update anyway
    Then I am told to stop the recording first
    And nothing is downloaded

  Scenario: Installing is refused while transcribing
    Given release 0.4.0 has a setup file
    And a meeting is transcribing
    When I choose "Update to 0.4.0"
    Then I am told to wait for the transcription to finish

  Scenario: A corrupted download is never run
    Given release 0.4.0 has a setup file whose download doesn't match its SHA-256
    When I choose "Update to 0.4.0"
    Then I am told the download was damaged
    And the setup file is deleted and not started

  Scenario: A release without a checksum is not installed
    Given release 0.4.0 has a setup file with no SHA-256 digest
    When I choose "Update to 0.4.0"
    Then I am told the update can't be verified
