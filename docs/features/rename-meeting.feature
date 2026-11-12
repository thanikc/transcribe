Feature: Rename a meeting

  Scenario: Rename a meeting from the page
    Given I am viewing the meeting "2026-11-11-1430-weekly-sync"
    When I click its title and enter "Budget review"
    Then the title shows "Budget review" in the view, the list and search hits
    And the meeting id stays "2026-11-11-1430-weekly-sync"

  Scenario: An empty title leaves it untitled
    When I rename a meeting to "   "
    Then it is untitled and shows its id where the title would be

  Scenario: Rename while recording
    Given a recording "Untitled call" is active
    When I rename it to "Customer call"
    Then the recording indicator shows "Customer call"
    And the meeting keeps that title after I stop

  Scenario: Rename while transcribing
    Given a meeting is being transcribed
    When I rename it to "Customer call"
    Then it is still called "Customer call" when the transcript is ready

  Scenario: Rename an unknown meeting
    When I rename meeting "nope"
    Then I am told no meeting "nope" exists

  Scenario: Rename from the CLI
    When I run "transcribe rename 2026-11-11-1430-weekly-sync Budget review"
    Then it prints that the meeting is now called "Budget review"

  Scenario: Claude renames a meeting
    When Claude calls rename_meeting with "2026-11-11-1430-weekly-sync" and "Budget review"
    Then the reply says the meeting is now called "Budget review"
