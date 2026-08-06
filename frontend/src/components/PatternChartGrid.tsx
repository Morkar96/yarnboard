/** Renders a Stitch Fiddle chart's grid as an actual colored <table> --
 * one cell per stitch, matching how Stitch Fiddle's own chart view reads,
 * rather than a flattened static image. `cells` is row-major; each value
 * is a 0-indexed lookup into `palette` for that cell's color. Wrapped in
 * a scrollable box since a large chart (hundreds of cells per side) at
 * even a few pixels per cell can otherwise overflow the page. */
import type { ChartGrid } from "../types/models";

const CELL_SIZE = 8; // px

interface Props {
  grid: ChartGrid;
}

export default function PatternChartGrid({ grid }: Props) {
  const { column_count, row_count, palette, cells } = grid;

  return (
    <div style={{ overflow: "auto", maxWidth: "100%", maxHeight: "70vh" }} className="mb-3">
      <table
        style={{
          borderCollapse: "collapse",
          width: column_count * CELL_SIZE,
          height: row_count * CELL_SIZE,
        }}
      >
        <tbody>
          {Array.from({ length: row_count }, (_, row) => (
            <tr key={row}>
              {Array.from({ length: column_count }, (_, col) => {
                const value = cells[row * column_count + col];
                const color = palette[value]?.hex ?? "#ffffff";
                return (
                  <td
                    key={col}
                    style={{
                      width: CELL_SIZE,
                      height: CELL_SIZE,
                      padding: 0,
                      backgroundColor: color,
                      // Thin cell borders, like Stitch Fiddle's own chart
                      // view -- without these, small same-colored cells
                      // visually blend together and the grid reads as a
                      // smooth picture instead of an obvious per-cell
                      // table (borderCollapse on the <table> above merges
                      // adjacent cells' borders into single grid lines).
                      border: "1px solid #ddd",
                    }}
                  />
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
