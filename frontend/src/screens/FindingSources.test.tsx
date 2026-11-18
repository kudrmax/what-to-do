import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FindingSources } from "./FindingSources";

describe("finding sources", () => {
  it("has a step of its own for Instagram profiles", () => {
    render(<FindingSources city="London" />);
    const titles = screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent);
    expect(titles).toEqual(["Search Telegram", "Check that it is public", "Instagram profiles too", "Websites work too"]);
    const step = screen.getByRole("heading", { name: "Instagram profiles too" }).closest("li");
    expect(within(step as HTMLElement).getByText("instagram.com/name")).toBeTruthy();
  });
});
