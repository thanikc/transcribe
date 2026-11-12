import { expect, test } from "@playwright/test";

test.describe("Meetings Recorder E2E", () => {
  test("configures settings, records a meeting, views & filters transcript, searches, renames, and deletes", async ({
    page,
  }) => {
    await page.goto("/");

    // 1. Initial idle UI & Settings drawer
    await expect(page.locator("#status")).toHaveText("Not recording");
    await expect(page.locator("#no-meetings")).toBeVisible();
    await expect(page.locator("#view .empty-state")).toHaveText(
      /^No meetings yet\./,
    );

    const settingsSummary = page.locator("#settings-summary");
    await expect(settingsSummary).toContainText("Auto · large-v3");
    await settingsSummary.click();
    await expect(page.locator("#settings-drawer")).toHaveAttribute("open", "");
    await page.locator("#language").selectOption("th");
    await expect(settingsSummary).toContainText("ไทย · large-v3");

    // Escape closes the open popover
    await page.keyboard.press("Escape");
    await expect(page.locator("#settings-drawer")).toHaveJSProperty(
      "open",
      false,
    );

    // 2. Start & stop a recording
    await page.locator("#title").fill("E2E Weekly Sync");
    await page.locator("#toggle").click();

    await expect(page.locator("#toggle")).toHaveText("Stop recording");
    await expect(page.locator("#status")).toContainText("Recording");
    await expect(page.locator("#status")).toContainText("E2E Weekly Sync");
    await expect(page.locator("#meters")).toBeVisible();

    await page.locator("#toggle").click();
    await expect(page.locator("#toggle")).toHaveText("Start recording");

    // 3. Wait for transcription to finish (~8s in FakeSpeechToText + FakeDiarizer)
    await expect(page.locator("ol.transcript")).toBeVisible({ timeout: 20_000 });
    await expect(page.locator("ol.transcript li")).toHaveCount(3);
    await expect(page.locator("ol.transcript")).toContainText(
      "สวัสดีครับ เริ่มประชุมกันเลย",
    );
    await expect(page.locator("ol.transcript")).toContainText(
      "Let's start with the budget.",
    );

    // 4. Filter by speaker
    const filterGroup = page.getByRole("group", { name: "Filter by speaker" });
    await expect(filterGroup).toBeVisible();
    await filterGroup.getByRole("button", { name: "Speaker 2" }).click();
    await expect(page.locator("ol.transcript li:not([hidden])")).toHaveCount(1);
    await filterGroup.getByRole("button", { name: "All speakers" }).click();
    await expect(page.locator("ol.transcript li:not([hidden])")).toHaveCount(3);

    // 5. Rename Speaker 1 -> Somchai in the speaker's popover
    await page
      .locator("ol.transcript button.spk", { hasText: "Speaker 1" })
      .first()
      .click();
    await page.getByRole("textbox", { name: "Name for Speaker 1" }).fill("Somchai");
    await page.keyboard.press("Enter");
    await expect(
      page.locator("ol.transcript button.spk", { hasText: "Somchai" }).first(),
    ).toBeVisible();

    // 6. Rename meeting title -> Q4 Budget Review in place
    await page.locator("button.title-edit").click();
    await page.getByRole("textbox", { name: "Meeting title" }).fill("Q4 Budget Review");
    await page.keyboard.press("Enter");
    await expect(page.locator("button.title-edit")).toHaveText("Q4 Budget Review");
    await expect(page.locator("#meetings")).toContainText("Q4 Budget Review");

    // 7. Search transcripts
    await page.locator("#q").fill("budget");
    await page.locator("#search-form button[type=submit]").click();
    await expect(page.locator("#hits .hit")).toHaveCount(1);
    await expect(page.locator("#hits .hit")).toContainText(
      "Let's start with the budget.",
    );
    await expect(page.locator("#hits .hit mark")).toHaveText("budget");
    await page.locator("#hits .hit").click();
    await expect(page.locator("ol.transcript .seg.focus")).toContainText(
      "Let's start with the budget.",
    );

    // 8. Delete the meeting
    await page.locator("details.meeting-actions summary").click();
    await page.locator("button.danger", { hasText: "Delete meeting" }).click();
    await expect(page.locator(".confirm-delete")).toContainText(
      'Delete "Q4 Budget Review"?',
    );
    await page.locator(".confirm-delete button.danger").click();
    await expect(page.locator("#no-meetings")).toBeVisible();
    await expect(page.locator("#view .empty-state")).toHaveText(
      /^No meetings yet\./,
    );
  });

  test("imports an audio file chosen in the import panel", async ({ page }) => {
    await page.goto("/");
    await page.locator("#import-drawer summary").click();
    await page.locator("#import-file").setInputFiles({
      name: "standup.wav",
      mimeType: "audio/wav",
      buffer: silentWav(1),
    });
    await expect(page.locator("#import-title")).toHaveAttribute("placeholder", "standup");
    await page.locator("#import-title").fill("E2E Import");
    await page.locator("#import").click();

    await expect(page.locator("button.title-edit")).toHaveText("E2E Import");
    await expect(page.locator("ol.transcript")).toBeVisible({ timeout: 20_000 });

    // leave the service empty for the other test
    await page.locator("details.meeting-actions summary").click();
    await page.locator("button.danger", { hasText: "Delete meeting" }).click();
    await page.locator(".confirm-delete button.danger").click();
    await expect(page.locator("#no-meetings")).toBeVisible();
  });
});

/** A mono 16 kHz 16-bit WAV of silence. */
function silentWav(seconds: number): Buffer {
  const rate = 16000;
  const data = rate * seconds * 2;
  const b = Buffer.alloc(44 + data);
  b.write("RIFF", 0);
  b.writeUInt32LE(36 + data, 4);
  b.write("WAVEfmt ", 8);
  b.writeUInt32LE(16, 16);
  b.writeUInt16LE(1, 20);
  b.writeUInt16LE(1, 22);
  b.writeUInt32LE(rate, 24);
  b.writeUInt32LE(rate * 2, 28);
  b.writeUInt16LE(2, 32);
  b.writeUInt16LE(16, 34);
  b.write("data", 36);
  b.writeUInt32LE(data, 40);
  return b;
}
