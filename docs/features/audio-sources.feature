Feature: Choose the audio sources

  Scenario: Without a choice, recordings use the Windows default devices
    Given no audio source has been chosen
    When a recording in "mic+system" mode starts
    Then the microphone and the system audio are recorded from the Windows default devices

  Scenario: The connected devices are listed, with the default marked
    Given microphones "Headset" (default) and "Webcam" are connected
    And speakers "Speakers" (default) and "Headphones" are connected
    When the page asks for the audio sources
    Then it lists "Headset" and "Webcam" for the microphone and "Speakers" and "Headphones" for system audio
    And none is chosen

  Scenario: A chosen microphone is used for the next recording
    Given the microphone "Webcam" is chosen
    When a recording starts
    Then the microphone track is recorded from "Webcam"

  Scenario: A chosen speaker is used for the system audio
    Given the speaker "Headphones" is chosen for system audio
    When a recording in "mic+system" mode starts
    Then the system audio track is recorded from the loopback of "Headphones"

  Scenario: The choice applies to recordings started anywhere
    Given the microphone "Webcam" is chosen on the web page
    When a recording is started from the tray, the CLI or Claude Desktop
    Then the microphone track is recorded from "Webcam"

  Scenario: The choice survives a restart of the service
    Given the microphone "Webcam" is chosen
    When the service restarts
    Then "Webcam" is still the chosen microphone

  Scenario: Going back to the Windows default
    Given the microphone "Webcam" is chosen
    When "Windows default" is chosen for the microphone
    Then the next recording uses the Windows default microphone

  Scenario: A chosen device that is unplugged stops the recording from starting
    Given the microphone "Webcam" is chosen
    And "Webcam" is no longer connected
    When a recording starts
    Then it is refused with "the microphone "Webcam" is not connected; choose another in Settings"
    And no meeting is created

  Scenario: Only a connected device can be chosen
    When a microphone that is not connected is chosen
    Then the choice is refused and the previous choice stays

  Scenario: The page shows the choices in Settings
    Given the page is open
    Then Settings has a "Microphone" and a "System audio from" list, each starting with "Windows default (<its name>)"
    And picking one saves it at once
