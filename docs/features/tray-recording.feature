Feature: Start and stop recording from the tray

  Scenario: Start an online call from the tray
    Given no recording is active
    When I choose "Start recording (online call)" in the tray menu
    Then an untitled "mic+system" recording starts
    And the tray shows it is recording

  Scenario: Start an in-person meeting from the tray
    When I choose "Start recording (in person)"
    Then an untitled "mic" recording starts

  Scenario: Stop from the tray
    Given a recording is active, started from anywhere
    Then the tray menu shows "Stop recording" instead of the start items
    When I choose it
    Then the recording stops and its transcription starts

  Scenario: A device that will not open
    When I start a recording from the tray and the microphone can't be opened
    Then the tray shows a notification with the reason
