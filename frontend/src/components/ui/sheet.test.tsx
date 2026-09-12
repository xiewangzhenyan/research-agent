import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { Sheet, SheetContent, SheetTitle } from "./sheet";

it("opens an accessible drawer, traps keyboard focus and restores the opener on Escape", async () => {
  function Example() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button onClick={() => setOpen(true)}>History</button>
        <Sheet open={open} onOpenChange={setOpen}>
          <SheetContent>
            <SheetTitle>Conversations</SheetTitle>
            <button>First conversation</button>
            <button>Last conversation</button>
          </SheetContent>
        </Sheet>
      </>
    );
  }
  const user = userEvent.setup();
  render(<Example />);
  const opener = screen.getByRole("button", { name: "History" });
  await user.click(opener);
  expect(screen.getByRole("dialog", { name: "Conversations" })).toBeVisible();
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "First conversation" })).toHaveFocus(),
  );
  await user.tab({ shift: true });
  expect(screen.getByRole("button", { name: "Last conversation" })).toHaveFocus();
  await user.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(opener).toHaveFocus();
});
