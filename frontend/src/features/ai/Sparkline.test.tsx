import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Sparkline from "./Sparkline";

describe("Sparkline", () => {
  it("draws staged values in date order whatever their order", () => {
    render(
      <Sparkline
        values={[
          { date: "2031-03-01", value: 30 },
          { date: "2031-01-01", value: 10 },
          { date: "2031-02-01", value: 20 }
        ]}
      />
    );

    const sparkline = screen.getByRole("img", {
      name: "Sparkline of 3 values from 2031-01-01 to 2031-03-01, between 10 and 30"
    });
    expect(sparkline.querySelector("polyline")).toHaveAttribute(
      "points",
      "2.0,34.0 80.0,18.0 158.0,2.0"
    );
  });

  it("renders nothing with fewer than two numeric values", () => {
    const { container } = render(
      <Sparkline
        values={[
          { date: "2031-01-01", value: 10 },
          { date: "2031-02-01", value: "n/a" }
        ]}
      />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
