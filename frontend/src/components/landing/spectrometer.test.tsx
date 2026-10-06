import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { Spectrometer, type SpectrometerLabels } from "./spectrometer";

const labels: SpectrometerLabels = {
  index: "折射率 n",
  particle: "颗粒",
  sphere: "金纳米球",
  rod: "金纳米棒",
  peak: "共振峰",
  shift: "峰位移",
  fwhm: "半高宽",
  sensitivity: "灵敏度",
  fom: "品质因数",
  axisX: "波长",
  axisY: "消光",
  reference: "参考",
  note: "示意模型",
  plotLabel: "{particle} n={n} 峰 {peak}",
};

const readout = (label: string) => screen.getByText(label).nextElementSibling?.textContent;

it("shifts the resonance linearly with the medium's refractive index", () => {
  render(<Spectrometer labels={labels} />);
  const slider = screen.getByRole("slider", { name: "折射率 n" });
  fireEvent.change(slider, { target: { value: "1.413" } });
  // Rod: 692 nm at n = 1.333, 288 nm/RIU → Δn 0.08 shifts the peak by 23.0 nm.
  expect(readout("共振峰")).toBe("715.0nm");
  expect(readout("峰位移")).toBe("+23.0nm");
  expect(screen.getByRole("img", { name: "金纳米棒 n=1.413 峰 715.0" })).toBeInTheDocument();
});

it("switching to nanospheres shows their lower sensitivity", () => {
  render(<Spectrometer labels={labels} />);
  fireEvent.click(screen.getByRole("radio", { name: "金纳米球" }));
  fireEvent.change(screen.getByRole("slider", { name: "折射率 n" }), {
    target: { value: "1.413" },
  });
  expect(readout("峰位移")).toBe("+7.0nm");
  expect(readout("灵敏度")).toBe("88nm/RIU");
  expect(readout("品质因数")).toBe("1.4");
});
