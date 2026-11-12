# Transcribe

Record your meetings on your Windows PC and get a written transcript, in Thai or English. You can
read and search your transcripts yourself, or ask Claude Desktop about them.

- **Private:** everything happens on your computer. Your audio is never uploaded.
- **In person or online:** record just your microphone, or your microphone plus what your speakers
  play (for Zoom, Teams, Meet and other calls).
- **Who said what:** Transcribe tells speakers apart by their voices, and you can give them names.
- **Works with Claude Desktop:** ask Claude to start a recording, summarise a meeting, or find what
  was said about a topic.

## Install

1. Download `Transcribe-Setup-<version>.exe` from the [Releases page](https://github.com/thanikc/transcribe/releases).
2. Run it. If Windows says "Windows protected your PC", click **More info**, then **Run anyway** (the installer isn't code-signed).
3. Click through it. On the **Speech model** page, choose:
   - **large-v3** (default): the most accurate, and best for Thai. It's a 3 GB download and needs about 4 GB of free
     memory while transcribing. Without an NVIDIA graphics card, transcribing takes about 1–2× the meeting length.
   - **large-v3-turbo**: half the download (1.6 GB), about 2 GB of free memory, and several times faster. It makes
     a few more mistakes, noticeably more in Thai than in English. Pick it on an 8 GB computer.

   To switch later, run the installer again and pick the other one.

   Setup then downloads the speech files (about 500 MB plus the model) and shows its progress.
   Keep the computer online, and expect it to take a while on a slow connection.
4. When it finishes, the recorder page opens in your browser. A microphone icon appears in the
   notification area (by the clock; it may be under the **^** arrow). It turns red while a recording runs.

## Record a meeting

1. Open the recorder page: click the microphone icon by the clock, or go to http://127.0.0.1:8765.
2. Give the meeting a title, pick the **Language** (ไทย, English or Auto), and choose the **Mode**:
   - **In person (mic)** for a meeting in the room
   - **Online call (mic + system audio)** for Zoom, Teams, Meet and other calls
3. Click **Start recording**, and **Stop recording** when the meeting is over. Transcribing starts
   right after, and the transcript appears on the page when it's ready.

You can choose which **Microphone** to use and which speakers to record **System audio from**. You can
also **Import audio file** to transcribe a recording you made elsewhere.

Tips:

- **Use headphones on calls.** Without them, your microphone also picks up the other people, and their
  words appear twice in the transcript.
- The page lets you pick the **Speech model** for each meeting, and you can **Transcribe again** with
  another model or language. If `large-v3` doesn't fit in free memory, the meeting is transcribed with
  `large-v3-turbo` instead and says so.

## The tray icon

Right-click the microphone icon for:

- **Open recorder**: the recorder page (a left click does the same)
- **Start at login**: on by default
- **Connect to Claude Desktop**: see below
- **Open log**, **Open meetings folder**
- **Quit**: stops the recorder. A recording that's running is stopped first. A meeting still being transcribed
  shows as failed ("interrupted") next time, and **Transcribe again** finishes it.

## Use it from Claude Desktop

1. Right-click the tray icon and choose **Connect to Claude Desktop**.
2. Quit Claude Desktop from its own tray icon and start it again (closing the window isn't enough).

Then, in the **Chat** tab, ask things like "start recording my meeting", "summarise yesterday's sync" or
"what did we decide about the budget?". Claude can also list, search, rename speakers in and delete
your meetings. Transcribe must be running (the microphone icon is by the clock).

Your existing Claude Desktop settings are kept; the previous file is saved next to it as
`claude_desktop_config.json.bak`.

## Your recordings

Meetings are saved in the **Meetings** folder in your user folder (tray icon → **Open meetings folder**).
Each meeting has its own folder with the audio (MP3) and the transcript.

## Updating and uninstalling

When a new version is released, the recorder page and the tray icon offer to download and install it.
You can also run a newer installer by hand.

To uninstall, use Windows Settings → Apps. Your recordings in the Meetings folder are kept, and so is
the speech model (1.6–3 GB) in `%USERPROFILE%\.cache\huggingface`. Delete that folder to free the space.

## Good to know

- The transcript is made after the recording ends, not live. With `large-v3` on a computer without an
  NVIDIA graphics card, that takes about 1–2× the meeting length.
- Telling speakers apart is approximate, so check the names.
- Each meeting is transcribed in one language.
- The recorder page is only reachable from your own computer, and has no password.

## For developers

Running from source, setting up Claude Desktop by hand, the command line and the settings are in
[DEV.md](DEV.md).
