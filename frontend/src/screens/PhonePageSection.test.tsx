import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createApi, type PhonePage } from "../api/client";
import { ApiContext } from "../api/queries";
import { clock } from "../domain/dates";
import { PhonePageSection } from "./PhonePageSection";

const TOKEN_URL = "https://github.com/settings/personal-access-tokens/new";

const OFF: PhonePage = {
  enabled: false,
  repository: "",
  has_token: false,
  has_password: false,
  page_url: null,
  published_at: null,
  last_error: null,
  publishing: false,
};

function todayAt(hours: number, minutes: number): string {
  const moment = new Date();
  moment.setHours(hours, minutes, 0, 0);
  return moment.toISOString();
}

const ON: PhonePage = {
  enabled: true,
  repository: "max/what-to-do-plans",
  has_token: true,
  has_password: true,
  page_url: "https://max.github.io/what-to-do-plans/",
  published_at: todayAt(18, 40),
  last_error: null,
  publishing: false,
};

function setup(state: PhonePage) {
  const api = createApi("");
  const load = vi.spyOn(api, "phonePage").mockResolvedValue(state);
  const turnOn = vi.spyOn(api, "turnPhonePageOn").mockResolvedValue(ON);
  const turnOff = vi.spyOn(api, "turnPhonePageOff").mockResolvedValue({ ...ON, enabled: false });
  const publish = vi.spyOn(api, "publishPhonePage").mockResolvedValue(ON);
  render(
    <ApiContext.Provider value={api}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <PhonePageSection />
      </QueryClientProvider>
    </ApiContext.Provider>,
  );
  return { load, turnOn, turnOff, publish };
}

async function withClipboard(clipboard: Partial<Clipboard> | undefined, run: () => Promise<void>) {
  const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });
  try {
    await run();
  } finally {
    if (original) Object.defineProperty(navigator, "clipboard", original);
    else delete (navigator as { clipboard?: Clipboard }).clipboard;
  }
}

const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe("phone page", () => {
  it("shows_guide_when_off: each step on its own line with its own link", async () => {
    setup(OFF);
    const steps = within(await screen.findByRole("list", { name: "How to set it up" })).getAllByRole("listitem");
    expect(steps.length).toBeGreaterThanOrEqual(2);
    expect(within(steps[0]).getByRole("link")).toHaveAttribute("href", "https://github.com/new");
    expect(within(steps[1]).getByRole("link")).toHaveAttribute("href", TOKEN_URL);
    expect(within(steps[1]).getByText("Contents")).toBeInTheDocument();
    expect(within(steps[1]).getByText("Pages")).toBeInTheDocument();
    expect(screen.getByLabelText("Repository")).toBeInTheDocument();
    expect(screen.getByLabelText("Token")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Turn on" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish now" })).not.toBeInTheDocument();
  });

  it("shows the password on the eye", async () => {
    setup(OFF);
    fireEvent.click(await screen.findByRole("button", { name: "Show the password" }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
  });

  it("turns on with what was typed", async () => {
    const { turnOn } = setup(OFF);
    await screen.findByLabelText("Repository");
    fill("Repository", " max/what-to-do-plans ");
    fill("Token", "github_pat_1");
    fill("Password", "secret");
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));
    await waitFor(() => expect(turnOn).toHaveBeenCalledWith({ repository: "max/what-to-do-plans", token: "github_pat_1", password: "secret" }));
    expect(await screen.findByRole("button", { name: "Publish now" })).toBeInTheDocument();
  });

  it("turn_on_error_appears_under_field: the repository's own error under Repository", async () => {
    const { turnOn } = setup(OFF);
    turnOn.mockRejectedValue(new ApiError(422, "Repository not found"));
    await screen.findByLabelText("Repository");
    fill("Repository", "max/nothing");
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));
    await waitFor(() => expect(screen.getByLabelText("Repository")).toHaveAccessibleDescription(/Repository not found/));
    expect(screen.getByLabelText("Token")).not.toHaveAccessibleDescription(/Repository not found/);
  });

  it("turn_on_error_appears_under_field: the token's own error under Token", async () => {
    const { turnOn } = setup(OFF);
    turnOn.mockRejectedValue(new ApiError(422, "The token has no access to this repository"));
    fireEvent.click(await screen.findByRole("button", { name: "Turn on" }));
    await waitFor(() => expect(screen.getByLabelText("Token")).toHaveAccessibleDescription(/no access/));
    expect(screen.getByLabelText("Repository")).not.toHaveAccessibleDescription(/no access/);
  });

  it("turn_on_error_appears_under_field: any other error under the buttons", async () => {
    const { turnOn } = setup(OFF);
    turnOn.mockRejectedValue(new ApiError(422, "Could not reach GitHub. Check the internet connection."));
    fireEvent.click(await screen.findByRole("button", { name: "Turn on" }));
    const error = await screen.findByText("Could not reach GitHub. Check the internet connection.");
    expect(error).toHaveClass("error-text");
    expect(screen.getByLabelText("Repository")).not.toHaveAccessibleDescription(/GitHub/);
  });

  it("on_state_shows_link_qr_and_last_publish", async () => {
    setup(ON);
    const link = await screen.findByRole("link", { name: ON.page_url! });
    expect(link).toHaveAttribute("href", ON.page_url);
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "QR code of the page link" })).toBeInTheDocument();
    expect(screen.getByText(`Published today at ${clock("18:40")}`)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn off" })).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "How to set it up" })).not.toBeInTheDocument();
  });

  it("shows the last publish error instead of the time, in the error color", async () => {
    setup({ ...ON, last_error: "The token expired or was revoked" });
    const error = await screen.findByText("The token expired or was revoked");
    expect(error.closest(".error-text")).not.toBeNull();
    expect(screen.queryByText(/^Published/)).not.toBeInTheDocument();
  });

  it("publishes now and turns off", async () => {
    const { publish, turnOff } = setup(ON);
    fireEvent.click(await screen.findByRole("button", { name: "Publish now" }));
    await waitFor(() => expect(publish).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));
    await waitFor(() => expect(turnOff).toHaveBeenCalled());
    expect(await screen.findByRole("button", { name: "Turn on" })).toBeInTheDocument();
  });

  it("says the plans stay on GitHub when turning off failed there", async () => {
    const { load, turnOff } = setup(ON);
    turnOff.mockImplementation(() => {
      load.mockResolvedValue(OFF);
      return Promise.reject(new ApiError(422, "Could not reach GitHub. Check the internet connection."));
    });
    fireEvent.click(await screen.findByRole("button", { name: "Turn off" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/GitHub still has the last published plans/)).toBeInTheDocument();
    expect(within(alert).getByText("Could not reach GitHub. Check the internet connection.")).toHaveClass("error-text");
  });

  it("copies the link", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    await withClipboard({ writeText }, async () => {
      setup(ON);
      fireEvent.click(await screen.findByRole("button", { name: "Copy" }));
      expect(writeText).toHaveBeenCalledWith(ON.page_url);
      expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    });
  });

  it("says it couldn't copy when the browser has no clipboard", async () => {
    await withClipboard(undefined, async () => {
      setup(ON);
      fireEvent.click(await screen.findByRole("button", { name: "Copy" }));
      expect(await screen.findByRole("button", { name: "Couldn’t copy" })).toBeInTheDocument();
    });
  });

  it("forgets a failed turn off once the page is on again", async () => {
    const { load, turnOff, turnOn } = setup(ON);
    turnOff.mockImplementation(() => {
      load.mockResolvedValue(OFF);
      return Promise.reject(new ApiError(422, "Could not reach GitHub. Check the internet connection."));
    });
    turnOn.mockImplementation(() => {
      load.mockResolvedValue(ON);
      return Promise.resolve(ON);
    });
    fireEvent.click(await screen.findByRole("button", { name: "Turn off" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));
    expect(await screen.findByRole("button", { name: "Publish now" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Could not reach GitHub. Check the internet connection.")).not.toBeInTheDocument());
  });

  it("secret_fields_never_show_values: saved ones only say so, and saving keeps them", async () => {
    const { turnOn } = setup(ON);
    const token = await screen.findByLabelText("Token");
    const password = screen.getByLabelText("Password");
    expect(token).toHaveValue("");
    expect(token).toHaveAttribute("placeholder", "Saved");
    expect(token).toHaveAttribute("type", "password");
    expect(password).toHaveValue("");
    expect(password).toHaveAttribute("placeholder", "Saved");
    expect(screen.getByLabelText("Repository")).toHaveValue(ON.repository);

    const save = screen.getByRole("button", { name: "Save and publish" });
    expect(save).toBeDisabled();
    fill("Repository", "max/plans");
    fireEvent.click(save);
    await waitFor(() => expect(turnOn).toHaveBeenCalledWith({ repository: "max/plans", token: null, password: null }));
  });
});
