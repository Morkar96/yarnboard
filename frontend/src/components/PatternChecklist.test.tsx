import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PatternChecklist from "./PatternChecklist";
import * as api from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { InstructionsMap, User } from "../types/models";

vi.mock("../context/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const loggedInUser: User = { id: 1, username: "jane", email: "jane@example.com", is_admin: false };

function mockAuth(user: User | null) {
  vi.mocked(useAuth).mockReturnValue({
    user,
    loading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  });
}

const instructions: InstructionsMap = {
  "Part 1": [
    { step: "Cast on 10.", completed: false },
    { step: "Knit 5 rows.", completed: false },
  ],
};

beforeEach(() => {
  mockAuth(loggedInUser);
  window.localStorage.clear();
});

describe("PatternChecklist", () => {
  it("optimistically checks a step and persists it via toggleProgress", async () => {
    const toggleSpy = vi.spyOn(api, "toggleProgress").mockResolvedValue({ completed_steps: {} });
    render(<PatternChecklist patternId={5} instructions={instructions} />);

    const checkbox = screen.getByLabelText("Cast on 10.");
    fireEvent.click(checkbox);

    expect(checkbox).toBeChecked();
    await waitFor(() => expect(toggleSpy).toHaveBeenCalledWith(5, "Part 1", 0, true));
  });

  it("reverts the checkbox if the API call fails", async () => {
    vi.spyOn(api, "toggleProgress").mockRejectedValue(new Error("network error"));
    render(<PatternChecklist patternId={5} instructions={instructions} />);

    const checkbox = screen.getByLabelText("Cast on 10.");
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    await waitFor(() => expect(checkbox).not.toBeChecked());
  });

  it("lets anonymous viewers check steps too, cached locally instead of via the API", () => {
    mockAuth(null);
    // vi.spyOn re-wraps whatever's currently exported -- since earlier
    // tests in this file already replaced toggleProgress with their own
    // mocks (never restored), the returned spy shares call history with
    // those; clear it so this assertion only reflects this test's clicks.
    const toggleSpy = vi.spyOn(api, "toggleProgress");
    toggleSpy.mockClear();
    render(<PatternChecklist patternId={5} instructions={instructions} />);

    expect(screen.getByText(/checking items off as a guest/i)).toBeInTheDocument();

    const checkbox = screen.getByLabelText("Cast on 10.");
    expect(checkbox).not.toBeDisabled();
    fireEvent.click(checkbox);

    expect(checkbox).toBeChecked();
    expect(toggleSpy).not.toHaveBeenCalled();
    expect(JSON.parse(window.localStorage.getItem("yarnboard:guest-progress:5")!)).toEqual({
      "Part 1": [true],
    });
  });

  it("restores a guest's cached progress on a later render of the same pattern", () => {
    mockAuth(null);
    window.localStorage.setItem("yarnboard:guest-progress:5", JSON.stringify({ "Part 1": [true] }));

    render(<PatternChecklist patternId={5} instructions={instructions} />);

    expect(screen.getByLabelText("Cast on 10.")).toBeChecked();
    expect(screen.getByLabelText("Knit 5 rows.")).not.toBeChecked();
  });

  it("collapses and expands a part's steps when its header is clicked", () => {
    render(<PatternChecklist patternId={5} instructions={instructions} />);

    const header = screen.getByText("Part 1").closest('[role="button"]') as HTMLElement;
    expect(header).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
  });
});
