import { Flex, Statistic } from "antd";
import type { CommunicationStats } from "../../types";

interface StatsPanelProps {
  stats: CommunicationStats;
}

export function StatsPanel({ stats }: StatsPanelProps) {
  const successRate =
    stats.request_count > 0
      ? ((stats.success_count / stats.request_count) * 100).toFixed(1)
      : "—";

  return (
    <Flex wrap gap={32}>
      <Statistic title="Requests" value={stats.request_count} />
      <Statistic title="Success" value={stats.success_count} valueStyle={{ color: "#52c41a" }} />
      <Statistic
        title="Errors"
        value={stats.error_count}
        valueStyle={stats.error_count > 0 ? { color: "#ff4d4f" } : undefined}
      />
      <Statistic title="Success Rate" value={successRate} suffix="%" />
      <Statistic title="Avg Latency" value={stats.avg_response_ms} suffix="ms" precision={1} />
    </Flex>
  );
}
