Feature: Rename a meeting

  Scenario: Rename a meeting from the page
    Given I am viewing the meeting "2026-11-11-1430-weekly-sync"
    When I click its title, type "Budget review" in its place and press Enter
    Then the title shows "Budget review" in the view, the list and search hits
    And the meeting id stays "2026-11-11-1430-weekly-sync"

  Scenario: Escape cancels renaming on the page
    Given I am editing a meeting's title on the page
    When I press Escape
    Then the title is unchanged and nothing is saved

  Scenario: A refused title stays open on the page
    Given I am editing a meeting's title on the page
    When the service refuses the new title
    Then its reason is shown under the field and the field stays open

  Scenario: An empty title leaves it untitled
    When I rename a meeting to "   "
    Then it is untitled and shows its id where the title would be

  Scenario: Rename while recording
    Given a recording "Untitled call" is active
    When I rename it to "Customer call"
    Then the recording indicator shows "Customer call"
    And the meeting keeps that title after I stop

  Scenario: Rename while recording from the page's title field
    Given a recording "Untitled call" is active and the page's title field shows "Untitled call"
    When I change the title field to "Customer call" and press Enter
    Then the recording indicator shows "Customer call"
    When I press Stop
    Then the title field is empty for the next recording

  Scenario: Escape in the title field while recording
    Given a recording "Standup" is active
    When I type in the title field and press Escape
    Then the field shows "Standup" again and nothing is renamed

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
