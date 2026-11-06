import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";
import { configureRequestAuthentication } from "../api/client";

let removeAuthentication: (() => void) | null = null;

beforeEach(() => {
  removeAuthentication = configureRequestAuthentication({
    getCsrfToken: () => "test-csrf-token",
    onUnauthorized: () => undefined
  });
});

afterEach(() => {
  cleanup();
  removeAuthentication?.();
  removeAuthentication = null;
});
