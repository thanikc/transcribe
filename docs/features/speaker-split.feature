Feature: Split a line where the speaker changes

  Scenario: A line spanning two speakers is split between them
    Given Whisper heard "Is the budget ready? Yes, it's done." from 0 to 6 with word times
    And speaker A talks from 0 to 3 and speaker B from 3 to 6
    When the track is labelled
    Then the transcript has "Speaker 1: Is the budget ready?" from 0 to 3
    And "Speaker 2: Yes, it's done." from 3 to 6

  Scenario: A word that is a short blip of another speaker does not split the line
    Given a 6 second line where one word under 1 second falls in another speaker's turn
    When the track is labelled
    Then the line stays whole with the main speaker

  Scenario: Thai words are joined without spaces
    Given Whisper heard Thai words "งบ" "ประมาณ" "ปีนี้" in one speaker's turn
    When the track is labelled
    Then the line reads "งบประมาณปีนี้"

  Scenario: Lines without word times keep the whole-line rule
    Given a line with no word times
    When the track is labelled
    Then it goes to the speaker who spoke most of it

  Scenario: The microphone in an online call stays "You"
    Given a "mic+system" meeting
    When it is transcribed
    Then every microphone line is "You", unsplit
