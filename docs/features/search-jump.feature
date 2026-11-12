Feature: A search hit opens the matching line

  Background:
    Given a transcribed meeting "Q4 Budget Review" with the line "[01:30] Speaker 2: Let's start with the budget."
    And I searched the transcripts for "budget" on the web page

  Scenario: The matched words are marked in the hit
    Then the hit shows "Let's start with the budget." with "budget" marked

  Scenario: Thai matches are marked too
    Given a hit for "งบประมาณ" in "ได้ครับ งบประมาณปีนี้เพิ่มขึ้น"
    Then "งบประมาณ" is marked in that hit

  Scenario: Searching shows that it is busy
    When the search takes a moment
    Then the page says "Searching…" until the hits arrive

  Scenario: Clicking a hit opens the meeting at that line
    When I click the hit
    Then the meeting opens scrolled to the line at 01:30
    And that line is briefly highlighted
    And nothing starts playing

  Scenario: A hidden line is revealed first
    Given I am viewing that meeting filtered to "Speaker 1", with the transcript collapsed
    When I click the hit
    Then the speaker filter is cleared and the transcript expanded
    And the line at 01:30 is scrolled to and highlighted

  Scenario: Clicking the same hit twice scrolls again
    Given I clicked the hit and scrolled away
    When I click the hit again
    Then the line at 01:30 is scrolled to and highlighted again
