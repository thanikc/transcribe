Feature: Drop the speakers' sound picked up by the microphone

  In an online call without headphones the microphone also hears the remote speakers,
  so their words came out twice: once as "You" and once from the system audio.

  Scenario: A microphone line that repeats the system audio at the same time is dropped
    Given a "mic+system" meeting
    And the system audio has "Let's start with the budget." from 3.0 to 6.0
    And the microphone has "let's start with the budget" from 3.2 to 6.1
    When it is transcribed
    Then the transcript has that line once, from the system audio

  Scenario: The repeat is found across differently split lines
    Given the system audio has "Let's start" from 3.0 to 4.0 and "with the budget." from 4.0 to 6.0
    And the microphone has "let's start with the budget" from 3.1 to 6.0
    When it is transcribed
    Then the microphone line is dropped

  Scenario: Thai repeats are found too
    Given the system audio has "งบประมาณปีนี้เพิ่มขึ้น" from 6.0 to 9.0
    And the microphone has "งบประมาณปีนี้เพิ่มขึ้นครับ" from 6.1 to 9.0
    When it is transcribed
    Then the microphone line is dropped

  Scenario: What I say myself is kept
    Given the microphone has "I disagree" from 7.0 to 8.0
    And the system audio has "the numbers look fine" from 6.5 to 8.5
    When it is transcribed
    Then "You: I disagree" is in the transcript

  Scenario: The same words at another time are kept
    Given the system audio has "sounds good" from 10.0 to 11.0
    And the microphone has "sounds good" from 40.0 to 41.0
    When it is transcribed
    Then both lines are in the transcript

  Scenario: A meeting says how many lines were dropped
    Given 3 microphone lines repeated the system audio
    When it is transcribed
    Then the meeting notes "left out 3 microphone lines that repeated the system audio"

  Scenario: In-person meetings are untouched
    Given a "mic" meeting
    When it is transcribed
    Then no line is dropped
