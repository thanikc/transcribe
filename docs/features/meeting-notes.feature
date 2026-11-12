Feature: Meeting notes

  Scenario: Claude saves notes for a meeting
    Given a transcribed meeting "2026-11-11-1430-weekly-sync"
    When Claude calls save_meeting_notes with a summary and action items
    Then the meeting folder holds them in notes.md
    And the reply says the notes were saved

  Scenario: Saving notes again replaces them
    Given a meeting with notes
    When notes are saved again
    Then only the new notes are kept

  Scenario: Empty notes remove them
    When empty notes are saved for a meeting
    Then it has no notes and no notes.md

  Scenario: Notes come with the transcript
    Given a meeting with notes
    When Claude calls get_transcript or I run "transcribe show"
    Then the notes are shown between the header and the transcript

  Scenario: The page shows the notes above the transcript
    Given I am viewing a meeting with notes
    Then the notes are shown above the transcript as plain text, line breaks kept

  Scenario: Notes survive transcribing again
    Given a meeting with notes
    When it is transcribed again
    Then its notes are kept

  Scenario: Notes for an unknown meeting
    When notes are saved for meeting "nope"
    Then I am told no meeting "nope" exists
