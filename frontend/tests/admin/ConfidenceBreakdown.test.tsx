import { render, screen, within } from "@testing-library/react";
import { ConfidenceBreakdown } from "@/components/admin/ConfidenceBreakdown";

describe("ConfidenceBreakdown", () => {
  it("renders an empty state when no deltas are present", () => {
    render(<ConfidenceBreakdown breakdown={null} reasons={null} />);
    expect(
      screen.getByText(/no breakdown captured/i),
    ).toBeInTheDocument();
  });

  it("sorts deltas by absolute magnitude with sign-styled values", () => {
    render(
      <ConfidenceBreakdown
        breakdown={{
          name_match: 25,
          wrong_state: -40,
          geometry_polygon: 20,
          duplicate_of_verified: 0,
        }}
        reasons={["Name partial match", "Wrong state penalty"]}
      />,
    );

    const list = screen.getByTestId("confidence-breakdown");
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3); // zero-delta row dropped

    // First item should be the largest-magnitude delta (-40 wrong_state).
    expect(items[0]).toHaveTextContent(/Wrong state/);
    expect(items[0]).toHaveTextContent(/-40/);

    expect(screen.getByText(/Name partial match/)).toBeInTheDocument();
  });
});
