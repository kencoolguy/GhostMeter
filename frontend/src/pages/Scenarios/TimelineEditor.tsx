import { MinusOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Popover, Space } from "antd";
import { useState } from "react";
import type { ScenarioStepCreate } from "../../types/scenario";
import { StepPopover } from "./StepPopover";
import { TimelineBlock } from "./TimelineBlock";

interface TimelineEditorProps {
  registerNames: string[];
  steps: ScenarioStepCreate[];
  onChange: (steps: ScenarioStepCreate[]) => void;
  readOnly?: boolean;
}

const MIN_PX_PER_SECOND = 5;
const MAX_PX_PER_SECOND = 40;
const DEFAULT_PX_PER_SECOND = 15;

export function TimelineEditor({ registerNames, steps, onChange, readOnly }: TimelineEditorProps) {
  const [pxPerSecond, setPxPerSecond] = useState(DEFAULT_PX_PER_SECOND);
  const [addPopover, setAddPopover] = useState<{ register: string; triggerAt: number } | null>(null);

  const maxTime = steps.length > 0
    ? Math.max(...steps.map((s) => s.trigger_at_seconds + s.duration_seconds))
    : 30;
  const timelineWidth = Math.max((maxTime + 10) * pxPerSecond, 600);

  const handleUpdate = (index: number, updated: ScenarioStepCreate) => {
    const newSteps = [...steps];
    newSteps[index] = updated;
    onChange(newSteps);
  };

  const handleDelete = (index: number) => {
    onChange(steps.filter((_, i) => i !== index));
  };

  const handleAdd = (step: ScenarioStepCreate) => {
    onChange([...steps, { ...step, sort_order: steps.length }]);
    setAddPopover(null);
  };

  const handleRowClick = (registerName: string, e: React.MouseEvent<HTMLDivElement>) => {
    if (readOnly) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const triggerAt = Math.max(0, Math.round(x / pxPerSecond));
    setAddPopover({ register: registerName, triggerAt });
  };

  // Time axis marks
  const marks: number[] = [];
  const markStep = pxPerSecond >= 15 ? 5 : 10;
  for (let t = 0; t <= maxTime + 10; t += markStep) {
    marks.push(t);
  }

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Button
          size="small"
          icon={<MinusOutlined />}
          onClick={() => setPxPerSecond(Math.max(MIN_PX_PER_SECOND, pxPerSecond - 5))}
        />
        <span style={{ fontSize: 12, color: "#888" }}>{pxPerSecond}px/s</span>
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={() => setPxPerSecond(Math.min(MAX_PX_PER_SECOND, pxPerSecond + 5))}
        />
      </Space>

      <div style={{ overflowX: "auto", border: "1px solid #d9d9d9", borderRadius: 4 }}>
        {/* Time axis */}
        <div style={{ position: "relative", height: 24, borderBottom: "1px solid #d9d9d9", marginLeft: 140 }}>
          {marks.map((t) => (
            <span
              key={t}
              style={{
                position: "absolute",
                left: t * pxPerSecond,
                fontSize: 10,
                color: "#888",
                transform: "translateX(-50%)",
                top: 4,
              }}
            >
              {t}s
            </span>
          ))}
        </div>

        {/* Register rows */}
        {registerNames.map((regName) => {
          const regSteps = steps
            .map((s, i) => ({ step: s, index: i }))
            .filter(({ step: s }) => s.register_name === regName);

          return (
            <div
              key={regName}
              style={{
                display: "flex",
                borderBottom: "1px solid #f0f0f0",
                minHeight: 32,
              }}
            >
              <div
                style={{
                  width: 140,
                  minWidth: 140,
                  padding: "4px 8px",
                  fontSize: 12,
                  borderRight: "1px solid #d9d9d9",
                  display: "flex",
                  alignItems: "center",
                  backgroundColor: "#fafafa",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={regName}
              >
                {regName}
              </div>
              <Popover
                open={addPopover?.register === regName}
                onOpenChange={(open) => { if (!open) setAddPopover(null); }}
                trigger="click"
                content={
                  addPopover?.register === regName ? (
                    <StepPopover
                      registerName={regName}
                      initialValues={{ trigger_at_seconds: addPopover.triggerAt }}
                      onSave={handleAdd}
                      onCancel={() => setAddPopover(null)}
                    />
                  ) : null
                }
              >
                <div
                  style={{
                    position: "relative",
                    flex: 1,
                    minWidth: timelineWidth,
                    cursor: readOnly ? "default" : "crosshair",
                  }}
                  onClick={(e) => handleRowClick(regName, e)}
                >
                  {regSteps.map(({ step: s, index: i }) => (
                    <TimelineBlock
                      key={i}
                      step={s}
                      index={i}
                      pxPerSecond={pxPerSecond}
                      onUpdate={handleUpdate}
                      onDelete={handleDelete}
                      readOnly={readOnly}
                    />
                  ))}
                </div>
              </Popover>
            </div>
          );
        })}
      </div>
    </div>
  );
}
