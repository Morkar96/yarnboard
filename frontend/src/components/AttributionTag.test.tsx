import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import AttributionTag from "./AttributionTag";
import type { Pattern } from "../types/models";

const basePattern: Pattern = {
  id: 1,
  original_url: "https://example.com/my-pattern",
  title: "Cozy Beanie",
  author: "Jane Designer",
  source_site_name: "Wooly Blog",
  source_domain: "woolyblog.example.com",
  materials: null,
  abbreviations: null,
  instructions: {},
  uploader: "knitter123",
  uploader_id: 2,
  created_at: null,
};

describe("AttributionTag", () => {
  it("shows the uploader and the original author/site", () => {
    render(<AttributionTag pattern={basePattern} />);

    expect(screen.getByText("knitter123")).toBeInTheDocument();
    expect(screen.getByText("Jane Designer")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Wooly Blog" });
    expect(link).toHaveAttribute("href", "https://example.com/my-pattern");
  });

  it("falls back to source_domain when source_site_name is missing", () => {
    render(<AttributionTag pattern={{ ...basePattern, source_site_name: null }} />);

    expect(screen.getByRole("link", { name: "woolyblog.example.com" })).toBeInTheDocument();
  });

  it("falls back to a generic label when neither site field is set", () => {
    render(
      <AttributionTag pattern={{ ...basePattern, source_site_name: null, source_domain: null }} />,
    );

    expect(screen.getByRole("link", { name: "the original site" })).toBeInTheDocument();
  });

  it("shows Unknown when there's no author on record", () => {
    render(<AttributionTag pattern={{ ...basePattern, author: null }} />);

    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });
});
