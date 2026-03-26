import { CloseOutlined } from "@ant-design/icons";
import { Button, Popover, Tooltip } from "antd";
import { useRef, useState } from "react";
import type { ScenarioStepCreate } from "../../types/scenario";
import { StepPopover } from "./StepPopover";

const ANOMALY_COLORS: Record<string, string> = {
  spike: "#fa8c16",
  drift: "#1890ff",
  flatline: "#8c8c8c",
  out_of_range: "#f5222d",
  data_loss: "#722ed1",
};

interface TimelineBlockProps {
  step: ScenarioStepCreate;
  index: number;
  pxPerSecond: number;
  onUpdate: (index: number, step: ScenarioStepCreate) => void;
  onDelete: (index: number) => void;
  readOnly?: boolean;
}

export function TimelineBlock({ step, index, pxPerSecond, onUpdate, onDelete, readOnly }: TimelineBlockProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [dragging, setDragging] = useState<"move" | "resize-right" | null>(null);
  const [dragOffset, setDragOffset] = useState<{ left?: number; width?: number } | null>(null);
  const dragStartX = useRef(0);
  const dragStartTrigger = useRef(0);
  const dragStartDuration = useRef(0);

  const left = step.trigger_at_seconds * pxPerSecond;
  const width = step.duration_seconds * pxPerSecond;
  const color = ANOMALY_COLORS[step.anomaly_type] ?? "#8c8c8c";

  const handleMouseDown = (e: React.MouseEvent, type: "move" | "resize-right") => {
    if (readOnly) return;
    e.preventDefault();
    e.stopPropagation();
    setDragging(type);
    dragStartX.current = e.clientX;
    dragStartTrigger.current = step.trigger_at_seconds;
    dragStartDuration.current = step.duration_seconds;

    const handleMouseMove = (ev: MouseEvent) => {
      const dx = ev.clientX - dragStartX.current;
      const dSeconds = Math.round(dx / pxPerSecond);
      if (type === "move") {
        const newTrigger = Math.max(0, dragStartTrigger.current + dSeconds);
        setDragOffset({ left: newTrigger * pxPerSecond });
      } else {
        const newDuration = Math.max(1, dragStartDuration.current + dSeconds);
        setDragOffset({ width: newDuration * pxPerSecond });
      }
    };

    const handleMouseUp = (ev: MouseEvent) => {
      const dx = ev.clientX - dragStartX.current;
      const dSeconds = Math.round(dx / pxPerSecond);
      if (type === "move") {
        const newTrigger = Math.max(0, dragStartTrigger.current + dSeconds);
        onUpdate(index, { ...step, trigger_at_seconds: newTrigger });
      } else {
        const newDuration = Math.max(1, dragStartDuration.current + dSeconds);
        onUpdate(index, { ...step, duration_seconds: newDuration });
      }
      setDragging(null);
      setDragOffset(null);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  return (
    <Popover
      open={popoverOpen && !dragging && !readOnly}
      onOpenChange={(open) => { if (!dragging) setPopoverOpen(open); }}
      trigger="click"
      content={
        <StepPopover
          registerName={step.register_name}
          initialValues={step}
          onSave={(updated) => { onUpdate(index, updated); setPopoverOpen(false); }}
          onDelete={() => { onDelete(index); setPopoverOpen(false); }}
          onCancel={() => setPopoverOpen(false)}
        />
      }
    >
      <Tooltip title={`${step.anomaly_type} (${step.trigger_at_seconds}s\u2013${step.trigger_at_seconds + step.duration_seconds}s)`}>
        <div
          style={{
            position: "absolute",
            left: dragOffset?.left ?? left,
            width: Math.max(dragOffset?.width ?? width, 20),
            height: 28,
            top: 2,
            backgroundColor: color,
            borderRadius: 4,
            cursor: readOnly ? "default" : (dragging === "move" ? "grabbing" : "grab"),
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 4px",
            color: "white",
            fontSize: 11,
            userSelect: "none",
            opacity: dragging ? 0.7 : 1,
          }}
          onMouseDown={(e) => handleMouseDown(e, "move")}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {step.anomaly_type}
          </span>
          {!readOnly && (
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined style={{ color: "white", fontSize: 10 }} />}
              onClick={(e) => { e.stopPropagation(); onDelete(index); }}
              style={{ minWidth: 16, padding: 0 }}
            />
          )}
          {!readOnly && (
            <div
              style={{
                position: "absolute",
                right: 0,
                top: 0,
                bottom: 0,
                width: 6,
                cursor: "ew-resize",
              }}
              onMouseDown={(e) => handleMouseDown(e, "resize-right")}
            />
          )}
        </div>
      </Tooltip>
    </Popover>
  );
}
