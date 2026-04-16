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
    expect(screen.getByText(/self.storage/i)).toBeInTheDocument();
    expect(screen.getByText(/mini.warehouse/i)).toBeInTheDocument();
    expect(screen.getByText(/light industrial/i)).toBeInTheDocument();
    expect(screen.getByText(/luxury garage/i)).toBeInTheDocument();
  });

  it("renders submit button", () => {
    render(<HomePage />);
    expect(
      screen.getByRole("button", { name: /find candidate parcels/i })
    ).toBeInTheDocument();
  });
});
