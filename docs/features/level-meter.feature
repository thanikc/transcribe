Feature: Live sound level while recording

  Scenario: The status reports each track's sound level while recording
    Given a recording in "mic+system" mode is active
    When the page asks for the status
    Then the status carries a level from 0 to 1 for "mic" and for "system"
    And the level is the loudest sample of the last half second

  Scenario: The page shows a meter per track next to the recording indicator
    Given a recording in "mic+system" mode is active
    Then the page shows a "Microphone" and a "System audio" meter beside "● Recording"
    And each meter moves with that track's level

  Scenario: A silent track is easy to spot
    Given a recording is active
    And the microphone has been silent for 10 seconds
    Then its meter says "no sound"

  Scenario: No levels when idle
    Given no recording is active
    Then the status has no levels and the page shows no meters
