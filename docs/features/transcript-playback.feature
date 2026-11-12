Feature: Play the audio from a transcript line

  Scenario: Clicking a timestamp plays that moment
    Given I am viewing a transcribed "mic" meeting
    When I click the timestamp "[02:15]"
    Then the player jumps to 2:15 and plays

  Scenario: In an online call both tracks play together
    Given I am viewing a transcribed "mic+system" meeting
    When I click the timestamp of a "Speaker 1" line
    Then the microphone and system audio both play from that moment, in step
    And if one track is shorter, it stays stopped at its end while the other plays on

  Scenario: One set of controls for all tracks
    Given I am viewing a transcribed "mic+system" meeting
    Then there is one player with play/pause, back 10 s, forward 10 s, a position slider, "elapsed / length" and a speed picker
    And a mute toggle for "Microphone" and for "System audio"
    When I mute "Microphone"
    Then only the system audio is heard

  Scenario: The speed is remembered
    When I choose 1.5× and later open another meeting
    Then it plays at 1.5×

  Scenario: Keyboard shortcuts
    Given the focus is not in a text field, list or button
    When I press Space
    Then playback starts or pauses
    When I press ← or →
    Then the position moves 5 seconds back or forward

  Scenario: The transcript follows the playing line
    Given a long meeting is playing
    Then the line being played is kept in view
    But for 5 seconds after I scroll with the wheel, touch or keys, it stops following

  Scenario: The line being played is highlighted
    Given a track is playing
    Then the sentence whose time span holds the play position is highlighted
    And when sentences of two tracks overlap, the one that started last is highlighted
    And no other sentence is highlighted

  Scenario: Clicking a sentence plays from it
    Given I am viewing a transcribed meeting
    When I click a sentence inside a speaker's turn
    Then its track plays from that sentence's start
    But a click that ends a text selection does not start playback

  Scenario: Timestamps work from the keyboard
    When I tab to a timestamp and press Enter
    Then it plays from there
