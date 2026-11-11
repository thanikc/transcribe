Feature: Show what the recorder is doing while it works

  Scenario: A transcribing meeting reports its current step
    Given a "mic+system" meeting is being transcribed
    When speech-to-text is 40% through the system track
    Then the meeting shows "Transcribing system audio", step 2 of 3, 40% done

  Scenario: The steps of each mode
    Then a "mic" meeting goes through "Transcribing microphone", "Detecting speakers"
    And a "mic+system" meeting goes through "Transcribing microphone", "Transcribing system audio", "Detecting speakers"

  Scenario: A step that has not reported progress yet
    Given speech-to-text is still loading its model
    Then the step shows no percentage, only how long it has been running

  Scenario: Progress goes away when transcription ends
    When the meeting is transcribed, or transcription fails
    Then the meeting shows no progress

  Scenario: The web page shows a progress bar while transcribing
    When I open a transcribing meeting
    Then I see the step name, "step 2 of 3", a progress bar and the time spent on the step
    And the meetings list badge shows the percentage

  Scenario: The CLI and Claude see the step too
    When I run "transcribe show" on a transcribing meeting
    Then it says the transcript is not ready yet and names the current step and percentage

  Scenario: Start and stop say they are working
    When I press Start recording or Stop recording
    Then the status reads "Starting…" or "Stopping…" until the service answers
