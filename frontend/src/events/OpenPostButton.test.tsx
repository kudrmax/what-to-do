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
    source_kind: "telegram",
    post_url: `https://t.me/${title}/${id}`,
    post_text: "",
    published_at: "2026-11-03T10:00:00Z",
    data: { from_organizer: fromOrganizer } as Mention["data"],
    photos: [],
    event_photo: null,
    event_lines: [],
  };
}

describe("open post button", () => {
  it("names a site page as a page, not a post", () => {
    render(<OpenPostButton mentions={[{ ...mention(1, "Polako", false), source_kind: "web", post_url: "https://polakohedonist.club/ru/events/a" }]} />);
    expect(screen.getByText("Open on website").closest("a")).toHaveAttribute("href", "https://polakohedonist.club/ru/events/a");
  });

  it("names an Instagram post and an Instagram highlight by what they are", () => {
    const post = { ...mention(1, "eje", false), source_kind: "instagram" as const, post_url: "https://www.instagram.com/p/DfmlSc4DQL_/" };
    const { unmount } = render(<OpenPostButton mentions={[post]} />);
    expect(screen.getByText("Open post on Instagram").closest("a")).toHaveAttribute("href", post.post_url);
    unmount();
    render(<OpenPostButton mentions={[{ ...post, post_url: "https://www.instagram.com/stories/highlights/17901/" }]} />);
    expect(screen.getByText("Open highlight on Instagram")).toBeInTheDocument();
  });

  it("is not shown without sources", () => {
    render(<OpenPostButton mentions={[]} />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("opens the only post, with no source picker", () => {
    render(<OpenPostButton mentions={[mention(1, "afisha", false)]} />);
    expect(screen.getByText("Open post in Telegram").closest("a")).toHaveAttribute("href", "https://t.me/afisha/1");
    expect(screen.queryByLabelText("Choose source")).toBeNull();
  });

  it("opens the organizer's post by default and lists every source behind the arrow", () => {
    render(<OpenPostButton mentions={[mention(1, "afisha", false), mention(2, "teahouse", true)]} />);
    expect(screen.getByText("Open post in Telegram").closest("a")).toHaveAttribute("href", "https://t.me/teahouse/2");
    fireEvent.click(screen.getByLabelText("Choose source"));
    expect(screen.getAllByRole("menuitem").map((item) => item.getAttribute("href"))).toEqual(["https://t.me/teahouse/2", "https://t.me/afisha/1"]);
  });
});
