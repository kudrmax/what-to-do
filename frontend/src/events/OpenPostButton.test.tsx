import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Mention } from "../api/client";
import { OpenPostButton } from "./OpenPostButton";

function mention(id: number, title: string, fromOrganizer: boolean): Mention {
  return {
    id,
    locked: false,
    source_id: id,
    source_title: title,
    post_url: `https://t.me/${title}/${id}`,
    post_text: "",
    published_at: "2026-11-03T10:00:00Z",
    data: { from_organizer: fromOrganizer } as Mention["data"],
  };
}

describe("open post button", () => {
  it("is not shown without sources", () => {
    render(<OpenPostButton mentions={[]} />);
    expect(screen.queryByText("Открыть пост")).toBeNull();
  });

  it("opens the only post, with no source picker", () => {
    render(<OpenPostButton mentions={[mention(1, "afisha", false)]} />);
    expect(screen.getByText("Открыть пост").closest("a")).toHaveAttribute("href", "https://t.me/afisha/1");
    expect(screen.queryByLabelText("Выбрать источник")).toBeNull();
  });

  it("opens the organizer's post by default and lists every source behind the arrow", () => {
    render(<OpenPostButton mentions={[mention(1, "afisha", false), mention(2, "teahouse", true)]} />);
    expect(screen.getByText("Открыть пост").closest("a")).toHaveAttribute("href", "https://t.me/teahouse/2");
    fireEvent.click(screen.getByLabelText("Выбрать источник"));
    expect(screen.getAllByRole("menuitem").map((item) => item.getAttribute("href"))).toEqual(["https://t.me/teahouse/2", "https://t.me/afisha/1"]);
  });
});
