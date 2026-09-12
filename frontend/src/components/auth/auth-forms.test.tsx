import { render, screen, fireEvent } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, expect, it, vi } from "vitest";
import messages from "../../../messages/zh.json";
import { ApiError } from "@/lib/api-client";
import { LoginForm } from "./login-form";
import { RegisterForm } from "./register-form";

const { login, register } = vi.hoisted(() => ({ login: vi.fn(), register: vi.fn() }));
vi.mock("@/hooks", () => ({ useAuth: () => ({ login, register }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
beforeEach(() => {
  vi.clearAllMocks();
});
function show(form: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="zh" messages={{ auth: messages.auth }}>
      {form}
    </NextIntlClientProvider>,
  );
}
it.each([
  [401, "邮箱或密码错误"],
  [429, "操作过于频繁，请稍后重试。"],
  [503, "服务暂时不可用，请稍后重试。"],
])(
  "shows a Chinese login error for HTTP %s without leaking backend text",
  async (status, expected) => {
    login.mockRejectedValueOnce(new ApiError(Number(status), "Internal English backend detail"));
    show(<LoginForm />);
    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("密码", { exact: true }), {
      target: { value: "example-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(String(expected));
    expect(screen.queryByText("Internal English backend detail")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeEnabled();
  },
);
it("lets users reveal and conceal the same password with Chinese accessible controls", () => {
  show(<LoginForm />);
  const password = screen.getByLabelText("密码", { exact: true });
  fireEvent.change(password, { target: { value: "my-password" } });
  fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
  expect(password).toHaveAttribute("type", "text");
  expect(password).toHaveValue("my-password");
  fireEvent.click(screen.getByRole("button", { name: "隐藏密码" }));
  expect(password).toHaveAttribute("type", "password");
});
it("localizes registration strength and prevents a mismatched password submission", () => {
  show(<RegisterForm />);
  fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "test@example.com" } });
  fireEvent.change(screen.getByLabelText("密码", { exact: true }), {
    target: { value: "abc12345" },
  });
  fireEvent.change(screen.getByLabelText("确认密码"), { target: { value: "different" } });
  expect(screen.getByText("一般")).toBeVisible();
  expect(screen.getByText("至少 8 位")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "注册" }));
  expect(screen.getByRole("alert")).toHaveTextContent("两次输入的密码不一致");
  expect(register).not.toHaveBeenCalled();
});
