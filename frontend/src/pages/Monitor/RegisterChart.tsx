import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RegisterHistoryPoint } from "../../types";

interface RegisterChartProps {
  history: RegisterHistoryPoint[];
  registerName: string;
  unit: string;
}

export function RegisterChart({ history, registerName, unit }: RegisterChartProps) {
  const chartData = useMemo(() => {
    return history.map((p) => ({
      time: new Date(p.timestamp).toLocaleTimeString(),
      value: p.value,
    }));
  }, [history]);

  if (chartData.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 20, color: "#999" }}>
        No data yet
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: 250 }}>
      <ResponsiveContainer>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11 }}
            label={{
              value: `${registerName} (${unit})`,
              angle: -90,
              position: "insideLeft",
              style: { fontSize: 12 },
            }}
          />
          <Tooltip />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#1677ff"
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
