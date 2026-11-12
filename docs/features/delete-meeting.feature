Feature: Delete a meeting

  Scenario: Delete a finished meeting
    Given a transcribed meeting "2026-11-11-1430-weekly-sync"
    When I delete it
    Then it is gone from the meetings list
    And its folder, audio and transcript are removed from the data directory
    And its lines no longer appear in search results

  Scenario: A failed meeting can be deleted too
    Given a failed meeting
    When I delete it
    Then it is gone from the meetings list

  Scenario: A meeting that is still recording cannot be deleted
    Given a recording is active
    When I delete its meeting
    Then I am told to stop the recording first
    And the meeting is kept

  Scenario: A meeting that is being transcribed cannot be deleted
    Given a meeting is being transcribed
    When I delete it
    Then I am told to wait until transcription finishes
    And the meeting is kept

  Scenario: Deleting an unknown meeting
    When I delete meeting "nope"
    Then I am told no meeting "nope" exists

  Scenario: Delete from the web page asks first
    Given I am viewing a transcribed meeting
    When I choose "Delete meeting" from the meeting's Actions menu
    Then the page asks me to confirm, naming the meeting
    And only after I confirm is it deleted and the page goes back to the list

  Scenario: Delete from the CLI
    When I run "transcribe delete 2026-11-11-1430-weekly-sync"
    Then it prints that the meeting was deleted

  Scenario: Claude deletes a meeting
    When Claude calls delete_meeting with "2026-11-11-1430-weekly-sync"
    Then the reply says the meeting was deleted

  Scenario: Other websites cannot delete meetings
    When a DELETE request arrives with a foreign Origin
    Then it is refused and the meeting is kept
