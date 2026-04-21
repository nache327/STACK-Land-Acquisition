/**
 * Phase 1 smoke test — landing page renders without crashing.
 */
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock the router (used inside JurisdictionForm)
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

import HomePage from "@/app/page";

describe("HomePage", () => {
  it("renders heading", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("heading", { name: /zoning finder/i })
    ).toBeInTheDocument();
  });

  it("renders jurisdiction input", () => {
    render(<HomePage />);
    expect(
      screen.getByPlaceholderText(/draper.*UT/i)
    ).toBeInTheDocument();
  });

  it("renders all four target-use chips", () => {
    render(<HomePage />);
    // Scope to buttons — the intro paragraph copy also mentions these phrases,
    // so getByText would match multiple elements.
    expect(screen.getByRole("button", { name: /self.storage/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mini.warehouse/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /light industrial/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /luxury garage/i })).toBeInTheDocument();
  });

  it("renders submit button", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("button", { name: /find candidate parcels/i })
    ).toBeInTheDocument();
  });
});
