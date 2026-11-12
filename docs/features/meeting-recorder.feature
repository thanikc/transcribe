Feature: Record, transcribe and read local meetings

  Background:
    Given an empty meetings data directory

  # --- Recording ---

  Scenario: Record an in-person meeting from the microphone
    When I start recording "Weekly sync" in "mic" mode at 2026-11-11 14:30
    And I stop the recording
    Then meeting "2026-11-11-1430-weekly-sync" exists with a mic track and no system track
    And its status is "transcribing"

  Scenario: Record an online call with mic and system audio
    When I start recording "Client call" in "mic+system" mode
    And I stop the recording
    Then the meeting has a mic track and a system track

  Scenario: Starting a second recording while one is active is refused
    Given a recording is active
    When I start another recording
    Then I am told a recording is already in progress
    And no second meeting is created

  Scenario: Stopping when nothing is recording
    When I stop the recording
    Then I am told no recording is in progress

  Scenario: Audio device unavailable
    Given the audio capture cannot open the system loopback device
    When I start recording "Call" in "mic+system" mode
    Then I am told the device could not be opened
    And no meeting is left behind

  Scenario: Two meetings with the same title in the same minute
    When I record "Standup" twice at 2026-11-11 09:00
    Then the meeting ids are "2026-11-11-0900-standup" and "2026-11-11-0900-standup-2"

  # --- Transcription ---

  Scenario: Online call transcript attributes speakers and interleaves by time
    Given the mic track transcribes to "Hi all" at 0.0s and "Sounds good" at 5.0s
    And the system track transcribes to "Hello, let's start" at 2.0s and "Agreed" at 7.0s
    And diarization of the system track finds speaker A from 1.5s to 4.0s and speaker B from 6.5s to 9.0s
    When the meeting is transcribed
    Then its status is "transcribed"
    And the transcript reads:
      """
      [00:00] You: Hi all
      [00:02] Speaker 1: Hello, let's start
      [00:05] You: Sounds good
      [00:07] Speaker 2: Agreed
      """

  Scenario: In-person transcript labels speakers by voice
    Given a "mic" meeting whose mic track transcribes to "Let's begin" at 0.0s and "Okay" at 3.0s
    And diarization finds one speaker from 0.0s to 2.5s and another from 2.8s to 4.0s
    When the meeting is transcribed
    Then the transcript reads:
      """
      [00:00] Speaker 1: Let's begin
      [00:03] Speaker 2: Okay
      """

  Scenario: A segment spanning a speaker change goes to the majority speaker
    Given a segment from 10.0s to 14.0s
    And speaker A talks from 9.0s to 11.0s and speaker B from 11.0s to 15.0s
    When speakers are assigned
    Then the segment is attributed to speaker B

  Scenario: Diarization fails
    Given diarization raises "model download failed"
    When a "mic+system" meeting is transcribed
    Then its status is "transcribed"
    And system-track segments are labelled "Others"
    And the meeting shows the warning "speaker detection failed: model download failed"

  Scenario: Rename a speaker on the web page
    Given a transcribed meeting with "Speaker 2" in its transcript
    When I click "Speaker 2", type "Somchai" in the box that opens under it and press Enter
    Then every "Speaker 2" line now shows "Somchai"
    And get_transcript in Claude Desktop shows "Somchai"
    When I click "Somchai" and press "Reset to Speaker 2"
    Then every line shows "Speaker 2" again
    When I click "Speaker 2", type a name and press Escape
    Then nothing is renamed

  Scenario: Claude names a speaker from context
    When Claude calls rename_speaker for "Speaker 1" with name "Khun Nok"
    Then the transcript shows "Khun Nok" in place of "Speaker 1"

  Scenario: Renaming an unknown speaker is refused
    When I rename "Speaker 9" in a meeting that has only 2 speakers
    Then I am told there is no "Speaker 9" in that meeting

  Scenario: Transcribing again clears speaker names
    Given a meeting where "Speaker 1" is named "Somchai"
    When I transcribe it again
    Then its transcript uses "Speaker 1", "Speaker 2", … without names

  Scenario: Transcription fails
    Given speech-to-text raises "model download failed"
    When the meeting is transcribed
    Then its status is "failed" with error "model download failed"
    And its audio tracks are kept

  Scenario: Choose the speech model
    When I record a meeting with the speech model "large-v3-turbo"
    Then it is transcribed with "large-v3-turbo"
    And the meeting shows the speech model "large-v3-turbo"

  Scenario: Transcribe again with another speech model
    Given a meeting transcribed with "large-v3"
    When I transcribe it again with the speech model "large-v3-turbo"
    Then its transcript is replaced by one made with "large-v3-turbo"

  Scenario: Not enough memory for large-v3
    Given "large-v3" does not fit in free memory
    When an online call is transcribed with "large-v3"
    Then both tracks are transcribed with "large-v3-turbo"
    And the meeting shows the warning "not enough free memory for large-v3, so this was transcribed with large-v3-turbo"
    And the meeting shows the speech model "large-v3-turbo"

  Scenario: Meetings are transcribed one at a time
    Given a meeting is being transcribed
    When I stop the recording of a second meeting
    Then the second meeting's status is "transcribing" with no step yet
    And its transcription starts when the first one has finished
    And both meetings end up "transcribed"

  Scenario: Not enough memory for any model
    Given neither "large-v3" nor "large-v3-turbo" fits in free memory
    When the meeting is transcribed
    Then its status is "failed" with an error telling me to close other apps and transcribe again
    And its audio tracks are kept

  Scenario: Re-transcribe a failed meeting
    Given a meeting with status "failed"
    When I transcribe it again and it succeeds
    Then its status is "transcribed"

  # --- Languages (Thai and English) ---

  Scenario Outline: Record a meeting in a chosen language
    When I record a meeting with language "<language>"
    Then speech-to-text is asked to transcribe each track as "<language>"
    And the meeting records language "<language>"

    Examples:
      | language |
      | th       |
      | en       |

  Scenario: Auto-detect the language
    Given speech-to-text detects "th" on the mic track
    When I record a meeting with language "auto" and it is transcribed
    Then speech-to-text is asked to detect the language
    And the meeting shows detected language "th" for the mic track

  Scenario: Re-transcribe with a different language when detection was wrong
    Given a transcribed meeting whose language was detected as "en"
    When I transcribe it again with language "th"
    Then its transcript is replaced with the Thai transcription
    And the meeting records language "th"

  Scenario: Thai title gives a timestamp-only meeting id
    When I start recording "ประชุมทีม" at 2026-11-11 14:30
    Then the meeting id is "2026-11-11-1430"
    And the meeting title is "ประชุมทีม"

  Scenario: A meeting without a title is shown by its id
    When I start recording with an empty title at 2026-11-11 14:30
    Then the meeting id is "2026-11-11-1430"
    And start_recording, list_meetings and get_transcript show "2026-11-11-1430" where the title would be

  Scenario: Thai text survives storage, the API and MCP unchanged
    Given a mic track that transcribes to "สวัสดีครับ เริ่มประชุมกันเลย"
    When the meeting is transcribed
    Then transcript.json contains "สวัสดีครับ เริ่มประชุมกันเลย" as UTF-8 text, not \u escapes
    And the web API and get_transcript both return "[00:00] สวัสดีครับ เริ่มประชุมกันเลย"

  Scenario: Search Thai transcripts
    Given a transcribed meeting containing "งบประมาณไตรมาสหน้า"
    When I search for "งบประมาณ"
    Then I get that hit

  Scenario: A meeting saved with an engine still loads
    Given a meeting.json from before the engine choice was removed, with "engine": "gemini-cli"
    When I list meetings
    Then that meeting is listed and opens like any other

  # --- Reading (CLI and Claude Desktop) ---

  Scenario: List meetings newest first with status
    Given meetings recorded at 09:00 (transcribed) and 14:30 (transcribing)
    When I list meetings
    Then I see the 14:30 meeting first, then the 09:00 meeting, each with title, start time, duration, audio size and status

  Scenario: A corrupt meeting folder does not break listing
    Given one meeting folder has an unreadable meeting.json
    When I list meetings
    Then the other meetings are listed

  Scenario: Get the transcript of a meeting still being transcribed
    Given a meeting with status "transcribing"
    When I get its transcript
    Then I am told the transcript is not ready yet, with its status

  Scenario: Get the transcript of an unknown meeting
    When I get the transcript of "nope"
    Then I am told no meeting "nope" exists

  Scenario: Search transcripts case-insensitively
    Given transcribed meetings mentioning "Budget" and "budget review"
    When I search for "BUDGET"
    Then I get both hits, each with meeting id, timestamp, speaker and text

  Scenario: An interrupted recording is recovered on service startup
    Given a meeting left with status "recording" by a service that crashed
    When the recorder service starts
    Then that meeting's status is "failed" with error "interrupted"
    And its audio can be transcribed again

  # --- Web UI ---

  Scenario: Start and stop a recording from the web page
    Given the web page shows "Not recording"
    When I enter title "Design review", choose "Online call" on the mode switch next to Start and press Start
    Then the page shows "● Recording" with an elapsed time that increases
    When I press Stop
    Then the page shows "Not recording"
    And the meeting appears at the top of the list as "transcribing"
    And the page opens that meeting showing "Transcribing…"
    And when transcription finishes, its transcript appears and its status shows "transcribed", without a page reload

  Scenario: The page remembers the mode and locks it while recording
    Given I chose "Online call" on the mode switch
    When I open the web page again
    Then "Online call" is still chosen
    When a recording in "mic" mode is active
    Then the mode switch shows "In person" and cannot be changed until it stops

  Scenario: The web page reflects a recording started elsewhere
    Given Claude started a recording "Standup"
    When I open the web page
    Then it shows "● Recording" for "Standup" and offers Stop

  Scenario: View a meeting on the web page
    Given a transcribed "mic+system" meeting
    When I open it on the web page
    Then I see its transcript with timestamps and speakers
    And one audio player for both the mic and the system track

  Scenario: The transcript reads as speaker turns
    Given a transcribed meeting where "Speaker 1" says two lines in a row, then "Speaker 2" answers
    When I open it on the web page
    Then "Speaker 1"'s two lines are one turn with the speaker named once, followed by a turn for "Speaker 2"

  Scenario: A long monologue is broken into paragraphs
    Given one speaker talks for three minutes without a pause over 2 seconds
    Then their lines are shown as turns of at most 60 seconds each
    And a pause over 2 seconds also starts a new paragraph

  Scenario: Filtering by speaker hides whole turns
    When I filter the transcript by "Speaker 2"
    Then only "Speaker 2"'s turns are shown

  Scenario: First run says how to make a meeting
    Given there are no meetings yet
    When I open the web page
    Then it says "No meetings yet. Press Start recording, or use Import audio to transcribe a file you already have."

  Scenario: A slow meeting load says it is loading
    When I open a meeting that takes a moment to load
    Then the meeting view says "Loading…" until it arrives

  Scenario: A speaker keeps their colour
    Given a transcribed meeting with "Speaker 1" and "Speaker 2"
    When I open it, open another meeting, and open it again
    Then "Speaker 1" has the same colour both times, the first colour of the palette

  Scenario: Audio keeps playing while the meeting is transcribing
    Given a meeting with status "transcribing"
    And I am playing its audio on the web page
    When the page refreshes the transcription progress
    Then the audio keeps playing without restarting or flickering

  Scenario: Choose the speaker the audio plays through
    Given the browser can pick an audio output device
    When I choose "Headphones" under "Play through" in a meeting view
    Then every track plays through "Headphones"
    And the choice is remembered the next time I open the page

  Scenario: Output device choice unavailable
    Given the browser cannot pick an audio output device
    When I open a meeting
    Then there is no "Play through" picker and audio plays through the Windows default output

  Scenario: Re-transcribe a failed meeting from the web page
    Given a meeting with status "failed"
    When I open it and press "Transcribe again…" beside the failure message
    Then the meeting's Actions menu opens
    When I press "Transcribe again" in it
    Then its status changes to "transcribing"

  Scenario: Meeting actions are in the header
    Given I am viewing a transcribed, failed or transcribing meeting
    Then an Actions menu beside its title offers "Transcribe again" with a language and speech model picker
    And "Delete meeting" only for a transcribed or failed meeting
    And a meeting that is still recording has no Actions menu

  Scenario: Another website cannot start a recording
    When a request to start a recording arrives with Origin "https://evil.example"
    Then it is refused with 403
    And no recording starts

  Scenario: Requesting audio outside a meeting folder is refused
    When audio is requested for meeting "../../Windows" or track "secrets"
    Then it is refused with 404

  # --- Claude Desktop ---

  Scenario: Claude Desktop starts and stops a recording
    When Claude calls start_recording with title "Design review" and mode "mic+system"
    And Claude calls stop_recording
    Then the reply contains the meeting id and says transcription has started
    And list_meetings later shows that meeting as "transcribed"

  Scenario: Claude stops a recording started from the web page
    Given a recording was started from the web page
    When Claude calls stop_recording
    Then that recording stops

  Scenario: The recorder service is not running
    Given the recorder service is not running
    When Claude calls start_recording
    Then the reply says the recorder service is not running and to start it with "transcribe serve"

  Scenario: The web page loses the recorder service
    Given the web page is open
    When three status checks in a row get no answer from the recorder service
    Then the page says "Disconnected" and that it can't reach the recorder
    And the Start button is disabled and the elapsed time stops
    When the service answers again
    Then the message goes away and the meetings list and speech models are reloaded
