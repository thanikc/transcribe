Feature: Import an audio file

  Scenario: Import a file from the page
    Given a phone recording "standup.m4a"
    When I choose it under "Import audio file" with title "Standup" and language "th"
    Then a meeting "Standup" appears in "Imported file" mode, being transcribed
    And it has one track, "Audio file", converted to 16 kHz mono MP3
    And its duration is the file's length
    And it is transcribed and its speakers detected like an in-person meeting

  Scenario: Import from the CLI
    When I run "transcribe import standup.m4a --language th"
    Then a meeting titled "standup" is created and its id printed

  Scenario: A file that is not audio is refused
    When I import a text file
    Then I am told the file could not be read as audio
    And no meeting is left behind

  Scenario: Importing works while a recording is active
    Given a recording is active
    When I import a file
    Then the import becomes its own meeting and the recording goes on

  Scenario: Imports wait their turn
    Given a meeting is being transcribed
    When I import a file
    Then it is transcribed after the first one

  Scenario: Other websites cannot import
    When an import request arrives with a foreign Origin
    Then it is refused and no meeting is created
