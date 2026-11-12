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
    await expect(settingsSummary).toContainText("Mic · Auto · large-v3");
    await settingsSummary.click();
    await expect(page.locator("#settings-drawer")).toHaveAttribute("open", "");
    await page.locator("#language").selectOption("th");
    await expect(settingsSummary).toContainText("Mic · ไทย · large-v3");

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
});
