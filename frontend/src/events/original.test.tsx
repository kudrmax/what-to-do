import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { createApi } from "../api/client";
import { ApiContext } from "../api/queries";
import { PhotoViewer } from "./PhotoViewer";
import { PostText } from "./PostText";

const DIGEST = "Афиша недели\n\n17:00 Керамика (https://t.me/a/1)\n19:00 Alex Solely (https://t.me/a/2)";

describe("post text", () => {
  it("keeps the post's words and turns each stored link into a link mark", () => {
    render(<PostText text={DIGEST} highlighted={[]} />);
    expect(screen.getByText("19:00 Alex Solely")).toBeTruthy();
    expect(screen.getByLabelText("Link: https://t.me/a/2").getAttribute("href")).toBe("https://t.me/a/2");
    expect(screen.queryByText(/\(https/)).toBeNull();
  });

  it("highlights this event's lines and scrolls to the first of them", () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(<PostText text={DIGEST} highlighted={[3]} />);
    const line = screen.getByText("19:00 Alex Solely");
    expect(line.className).toContain("post-text__line--marked");
    expect(screen.getByText("17:00 Керамика").className).not.toContain("marked");
    expect(scroll).toHaveBeenCalledOnce();
  });

  it("says when a post has only photos", () => {
    render(<PostText text="  " highlighted={[]} />);
    expect(screen.getByText("The post has only photos, no text.")).toBeTruthy();
  });
});

function viewer(onClose = vi.fn()) {
  const photos = [
    { url: "/images/a.jpg", text: "ВС, 22.11\n18:00" },
    { url: "/images/b.jpg", text: null },
    { url: "/images/c.jpg", text: "" },
  ];
  render(
    <ApiContext.Provider value={createApi("http://test")}>
      <PhotoViewer photos={photos} start={0} onClose={onClose} />
    </ApiContext.Provider>,
  );
  return onClose;
}

describe("photo viewer", () => {
  it("shows each photo with the text Claude read on it", () => {
    viewer();
    expect(screen.getByText("Photo 1 of 3")).toBeTruthy();
    expect(screen.getByText(/ВС, 22.11/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Next photo"));
    expect(screen.getByText("The text in this photo hasn’t been read yet.")).toBeTruthy();
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(screen.getByText("There’s no text in this photo.")).toBeTruthy();
  });

  it("closes on Esc without letting the event window close too", async () => {
    const behind = vi.fn();
    document.addEventListener("keydown", behind);
    const onClose = viewer();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(behind).not.toHaveBeenCalled();
    document.removeEventListener("keydown", behind);
  });
});
