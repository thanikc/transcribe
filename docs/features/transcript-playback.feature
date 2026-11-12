Feature: Play the audio from a transcript line

  Scenario: Clicking a timestamp plays that moment
    Given I am viewing a transcribed "mic" meeting
    When I click the timestamp "[02:15]"
    Then the microphone player jumps to 2:15 and plays

  Scenario: In an online call the right track plays
    Given I am viewing a transcribed "mic+system" meeting
    When I click the timestamp of a "You" line
    Then the microphone player plays from there and the system audio player pauses
    When I click the timestamp of a "Speaker 1" line
    Then the system audio player plays from there and the microphone player pauses

  Scenario: The line being played is highlighted
    Given a track is playing
    Then the sentence of that track whose time span holds the play position is highlighted
    And no other sentence is highlighted

  Scenario: Clicking a sentence plays from it
    Given I am viewing a transcribed meeting
    When I click a sentence inside a speaker's turn
    Then its track plays from that sentence's start
    But a click that ends a text selection does not start playback

  Scenario: Timestamps work from the keyboard
    When I tab to a timestamp and press Enter
    Then it plays from there
