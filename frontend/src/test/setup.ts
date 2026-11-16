import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

import { LocaleConventions, setConventions } from "../domain/locale";

beforeEach(() => setConventions(new LocaleConventions("en-GB")));
afterEach(cleanup);
