import { Button } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { templateApi } from "../../services/templateApi";
import type { TemplateSummary } from "../../types";

/**
 * Shown when there are zero devices in the system.
 * Offers built-in template shortcuts and a "create device" CTA.
 */
export function EmptyState() {
  const navigate = useNavigate();
  const [builtins, setBuiltins] = useState<TemplateSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    templateApi
      .list()
      .then((res) => {
        if (cancelled) return;
        setBuiltins((res.data ?? []).filter((t) => t.is_builtin).slice(0, 3));
      })
      .catch(() => {
        if (!cancelled) setBuiltins([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div
      style={{
        textAlign: "center",
        padding: "60px 20px",
        color: "var(--gm-text-2)",
      }}
    >
      <div style={{ fontSize: 48, opacity: 0.4, marginBottom: 12 }}>⚡</div>
      <div style={{ color: "var(--gm-text-1)", fontSize: 18, fontWeight: 600, marginBottom: 6 }}>
        還沒有設備
      </div>
      <div style={{ fontSize: 13, marginBottom: 18 }}>
        從內建模板快速建立第一台
      </div>

      {builtins.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 8,
            justifyContent: "center",
            flexWrap: "wrap",
            marginBottom: 18,
          }}
        >
          {builtins.map((t) => (
            <span
              key={t.id}
              onClick={() => navigate("/devices")}
              style={{
                padding: "6px 12px",
                background: "var(--gm-bg-1)",
                border: "1px solid rgba(34,211,238,0.3)",
                borderRadius: 6,
                fontSize: 11,
                color: "var(--gm-cyan)",
                cursor: "pointer",
              }}
            >
              {t.name}
            </span>
          ))}
        </div>
      )}

      <Button type="primary" onClick={() => navigate("/devices")}>
        + 建立設備
      </Button>
    </div>
  );
}
