import { useMemo } from "react";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import type { RegisterHistoryPoint } from "../../types";

interface SparklineProps {
  data: RegisterHistoryPoint[];
  color?: string;
  height?: number;
}

/**
 * Tiny in-card line chart. No axes, no grid, no tooltip.
 * Animation disabled so 1Hz updates don't jitter.
 */
export function Sparkline({ data, color = "var(--gm-cyan)", height = 36 }: SparklineProps) {
  const chartData = useMemo(
    () => data.map((p) => ({ value: p.value })),
    [data],
  );

  if (chartData.length < 2) {
    return <div style={{ height, opacity: 0.3 }} />;
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={chartData} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
