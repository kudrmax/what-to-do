import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import { LocaleConventions, setConventions } from "../domain/locale";

beforeEach(() => setConventions(new LocaleConventions("en-GB")));
afterEach(cleanup);

// jsdom has no matchMedia; the page's theme asks it whether the system is dark.
window.matchMedia ??= vi.fn((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn() })) as unknown as typeof window.matchMedia;
