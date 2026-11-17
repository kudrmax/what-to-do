import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { Modal } from "./Modal";
import { Popover } from "./Popover";

afterEach(cleanup);

it("Esc closes a menu without closing the window it is in", async () => {
  const closeWindow = vi.fn();
  render(
    <Modal label="Window" onClose={closeWindow}>
      <Popover trigger={(_, toggle) => <button onClick={toggle}>Open</button>}>{() => <span>Menu item</span>}</Popover>
    </Modal>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(screen.getByText("Menu item")).toBeInTheDocument();
  fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
  await waitFor(() => expect(screen.queryByText("Menu item")).not.toBeInTheDocument());
  expect(closeWindow).not.toHaveBeenCalled();
});
