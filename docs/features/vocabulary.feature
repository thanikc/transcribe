Feature: Vocabulary for names and jargon

  Scenario: Words in the vocabulary are passed to Whisper
    Given vocabulary.txt in the data directory lists "Somchai" and "Kubernetes", one per line
    When a meeting is transcribed
    Then Whisper is given "Somchai, Kubernetes" as words to expect

  Scenario: No vocabulary file
    Given there is no vocabulary.txt
    When a meeting is transcribed
    Then Whisper is given no words

  Scenario: Blank lines and "#" comments are ignored
    Given vocabulary.txt has blank lines and lines starting with "#"
    Then they are not passed to Whisper

  Scenario: A long vocabulary is cut to what Whisper can take
    Given vocabulary.txt lists more than 800 characters of words
    When a meeting is transcribed
    Then only the first words that fit in 800 characters are passed

  Scenario: Edit the vocabulary from the tray
    When I choose "Edit vocabulary" in the tray menu
    Then vocabulary.txt opens in the text editor, created with a short how-to if missing
