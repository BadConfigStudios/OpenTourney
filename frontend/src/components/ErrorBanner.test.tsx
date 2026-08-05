import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorBanner } from "./ErrorBanner";

describe("ErrorBanner", () => {
  it("renders nothing when there is no error", () => {
    const { container } = render(<ErrorBanner error={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders an Error's message", () => {
    render(<ErrorBanner error={new Error("date is required")} />);
    expect(screen.getByRole("alert")).toHaveTextContent("date is required");
  });

  it("falls back to a generic message for a non-Error thrown value", () => {
    render(<ErrorBanner error="boom" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });
});
