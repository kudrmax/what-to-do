import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { createApi } from "../api/client";
import { ApiContext } from "../api/queries";
import { EventPhotoGrid } from "./EventPhotoGrid";

afterEach(cleanup);

function grid(paths: (string | null)[]) {
  return render(
    <ApiContext.Provider value={createApi("")}>
      <EventPhotoGrid paths={paths} className="card__photo" />
    </ApiContext.Provider>,
  ).container;
}

const photos = (count: number) => Array.from({ length: count }, (_, i) => `/images/p${i}.jpg`);

describe("EventPhotoGrid", () => {
  it("shows one photo as the card always did", () => {
    const view = grid(["/images/p0.jpg"]);
    expect(view.querySelector(".photo-grid")).toBeNull();
    expect(view.querySelectorAll(".photo__image")).toHaveLength(1);
  });

  it("shows nothing without photos", () => {
    expect(grid([null]).innerHTML).toBe("");
  });

  it("puts the main photo first and large", () => {
    const view = grid(photos(3));
    expect(view.querySelector(".photo-grid")?.getAttribute("data-count")).toBe("3");
    expect(view.querySelector(".photo-grid__main .photo__image")?.getAttribute("src")).toContain("p0.jpg");
    expect(view.querySelectorAll(".photo-grid__small")).toHaveLength(2);
  });

  it("shows at most five photos and does not mark the rest", () => {
    const view = grid(photos(7));
    expect(view.querySelector(".photo-grid")?.getAttribute("data-count")).toBe("5");
    expect(view.querySelectorAll(".photo-grid__small")).toHaveLength(4);
    expect(view.textContent).toBe("");
  });

  it("a photo that fails to load gives its place to the next one", () => {
    const view = grid(photos(6));
    fireEvent.error(view.querySelectorAll(".photo-grid__small")[0]);
    const small = [...view.querySelectorAll(".photo-grid__small")].map((img) => img.getAttribute("src"));
    expect(small).toHaveLength(4);
    expect(small.some((src) => src?.includes("p1.jpg"))).toBe(false);
    expect(small.some((src) => src?.includes("p5.jpg"))).toBe(true);
  });
});
