import { ApiError } from "./api-client";

/** Translate public form errors instead of displaying raw backend messages. */
export function authFormErrorKey(error: unknown, action: "login" | "register" | "reset") {
  if (error instanceof ApiError) {
    if (error.status === 429) return "tooManyAttempts";
    if (error.status >= 500) return "serviceUnavailable";
    if (error.status === 403) return "accountDisabled";
    if (action === "login" && error.status === 401) return "invalidCredentials";
    if (action === "register" && error.status === 409) return "emailExists";
    if (error.status === 422) return "invalidInput";
  }
  return action === "login"
    ? "loginFailed"
    : action === "register"
      ? "registerFailed"
      : "resetPassword.invalidLink";
}
