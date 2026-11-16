import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createApi, type City, type Settings } from "../api/client";
import { ApiContext } from "../api/queries";
import { CitiesSection } from "./CitiesSection";
import { NoCity } from "./NoCity";

const LONDON: City = { id: 1, name: "London", country: "United Kingdom", timezone: "Europe/London", card_language: "English" };
const BELGRADE: City = { id: 2, name: "Белград", country: "", timezone: "Europe/Belgrade", card_language: "русский" };

function setup(cities: City[], ui = <CitiesSection />) {
  const api = createApi("");
  vi.spyOn(api, "settings").mockResolvedValue({ active_city_id: cities[0]?.id ?? null } as Settings);
  vi.spyOn(api, "cities").mockResolvedValue(cities);
  const add = vi.spyOn(api, "addCity").mockResolvedValue(LONDON);
  const change = vi.spyOn(api, "changeCity").mockResolvedValue(LONDON);
  const remove = vi.spyOn(api, "deleteCity").mockResolvedValue(undefined as never);
  vi.spyOn(api, "cityContents").mockResolvedValue({ sources: 12, events: 340, marked_events: 1 });
  const select = vi.spyOn(api, "changeSettings").mockResolvedValue({} as Settings);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { add, change, remove, select };
}

describe("cities", () => {
  it("shows each city's facts on their own and which city is shown", async () => {
    setup([LONDON, BELGRADE]);
    const [london, belgrade] = within(await screen.findByRole("list", { name: "Cities" })).getAllByRole("listitem");
    expect(within(london).getByRole("radio").getAttribute("aria-checked")).toBe("true");
    expect(within(london).getByText("United Kingdom")).toBeTruthy();
    expect(within(london).getByText("Europe/London")).toBeTruthy();
    expect(within(london).getByText("English")).toBeTruthy();
    expect(within(belgrade).getByRole("button", { name: "Add the country" })).toBeTruthy();
  });

  it("switches to another city", async () => {
    const { select } = setup([LONDON, BELGRADE]);
    fireEvent.click(await screen.findByRole("radio", { name: "Show Белград" }));
    await waitFor(() => expect(select).toHaveBeenCalledWith({ active_city_id: 2 }));
  });

  it("edits a city and warns that a new card language rewrites the recent cards", async () => {
    const { change } = setup([LONDON]);
    fireEvent.click(await screen.findByRole("button", { name: "Edit London" }));
    const language = screen.getByLabelText("Language of event cards");
    fireEvent.change(language, { target: { value: "Spanish" } });
    expect(screen.getByText("The next refresh rewrites the recent cards in this language")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(change).toHaveBeenCalledWith(1, { name: "London", country: "United Kingdom", timezone: "Europe/London", card_language: "Spanish" }));
  });

  it("deletes a city only after a confirmation that counts what goes with it", async () => {
    const { remove } = setup([LONDON]);
    fireEvent.click(await screen.findByRole("button", { name: "Delete London" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete London" });
    await within(dialog).findByText("340");
    expect(within(dialog).getByText("sources")).toBeTruthy();
    expect(within(dialog).getByText("event you marked")).toBeTruthy();
    expect(remove).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete city" }));
    await waitFor(() => expect(remove).toHaveBeenCalledWith(1));
  });

  it("welcomes a new user with the city form, the language taken from the browser", async () => {
    const { add } = setup([], <NoCity />);
    await screen.findByText("Where are you looking for things to do?");
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Lisbon" } });
    fireEvent.change(screen.getByLabelText("Country"), { target: { value: "Portugal" } });
    expect((screen.getByLabelText("Language of event cards") as HTMLInputElement).value).toBe("English");
    fireEvent.click(screen.getByRole("button", { name: "Add city" }));
    await waitFor(() => expect(add).toHaveBeenCalledWith(expect.objectContaining({ name: "Lisbon", country: "Portugal", card_language: "English" })));
  });
});
