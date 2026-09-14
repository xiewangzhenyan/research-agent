import { test, expect, type Page } from "@playwright/test";
import { mockWorkspace } from "./fixtures";

async function setup(page: Page) {
  await mockWorkspace(page);
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => {
          // Synthetic microphone, real browser MediaRecorder + decoder + PCM encoder.
          const audio = new AudioContext();
          await audio.resume();
          const source = audio.createOscillator();
          const destination = audio.createMediaStreamDestination();
          source.connect(destination);
          source.start();
          const track = destination.stream.getAudioTracks()[0]!;
          const stop = track.stop.bind(track);
          track.stop = () => {
            stop();
            source.stop();
            void audio.close();
          };
          return destination.stream;
        },
      },
    });
  });
  await page.route("**/api/chat/**", (route) =>
    route.fulfill({ json: { messages: [], runs: [], before: null } }),
  );
  await page.route("**/api/audio/config", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        provider: "siliconflow",
        model: "Qwen/Qwen3-ASR-1.7B",
        fallback_model: "XingChenAGI/XingChenASR-V3.2-Ultra",
        max_duration_seconds: 60,
      },
    }),
  );
  await page.goto("/chat");
}

test("real browser audio conversion, retry, draft preservation and editable transcription", async ({
  page,
}) => {
  await setup(page);
  let calls = 0;
  let original: Buffer | undefined;
  await page.route("**/api/audio/transcriptions", (route) => {
    const bytes = route.request().postDataBuffer()!;
    expect(bytes.subarray(0, 4).toString()).toBe("RIFF");
    expect(bytes.readUInt32LE(24)).toBe(16000);
    expect(bytes.readUInt16LE(22)).toBe(1);
    expect(bytes.length).toBeGreaterThan(8044);
    calls++;
    if (calls === 1) {
      original = bytes;
      return route.fulfill({ status: 503, json: { error: { message: "语音服务暂时繁忙" } } });
    }
    expect(bytes.equals(original!)).toBe(true);
    return route.fulfill({ json: { text: "请解释 LSPR 的原理。", model: "Qwen/Qwen3-ASR-1.7B" } });
  });
  const input = page.getByRole("textbox", { name: "输入消息" });
  await input.fill("已有草稿。");
  await page.getByRole("button", { name: "语音输入" }).click();
  await expect(page.getByText(/正在录音/)).toBeVisible();
  await expect(page.getByRole("button", { name: "发送消息" })).toBeDisabled();
  await expect(page.getByText(/正在录音 [1-9]/)).toBeVisible();
  await page.getByRole("button", { name: "结束录音" }).click();
  await expect(page.getByRole("button", { name: "重试转写" })).toBeVisible();
  await expect(input).toHaveValue("已有草稿。");
  await input.fill("修改后的草稿。");
  await page.getByRole("button", { name: "重试转写" }).click();
  await expect(input).toHaveValue("修改后的草稿。 请解释 LSPR 的原理。");
  await expect(page.getByRole("button", { name: "发送消息" })).toBeEnabled();
  expect(calls).toBe(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("cancel never posts audio and speech configuration shows the selected model order", async ({
  page,
}) => {
  await setup(page);
  let calls = 0;
  await page.route("**/api/audio/transcriptions", (route) => {
    calls++;
    return route.fulfill({ json: { text: "unexpected" } });
  });
  await page.getByRole("button", { name: "语音输入" }).click();
  await expect(page.getByText(/正在录音/)).toBeVisible();
  await page.locator(".chat-composer").getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "输入消息" })).toHaveValue("");
  expect(calls).toBe(0);
  await page.goto("/models");
  await page.getByRole("tab", { name: "语音模型" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel.getByText("Qwen/Qwen3-ASR-1.7B", { exact: true })).toBeVisible();
  await expect(
    panel.getByText("XingChenAGI/XingChenASR-V3.2-Ultra", { exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
