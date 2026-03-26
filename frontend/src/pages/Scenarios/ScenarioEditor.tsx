import { Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { scenarioApi } from "../../services/scenarioApi";
import { useScenarioStore } from "../../stores/scenarioStore";
import type { ScenarioStepCreate } from "../../types/scenario";
import type { TemplateSummary } from "../../types/template";
import type { ApiResponse } from "../../types/template";
import { TimelineEditor } from "./TimelineEditor";
import axios from "axios";

export default function ScenarioEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentScenario, fetchScenario, clearCurrentScenario } = useScenarioStore();
  const [form] = Form.useForm();
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [registerNames, setRegisterNames] = useState<string[]>([]);
  const [steps, setSteps] = useState<ScenarioStepCreate[]>([]);
  const [saving, setSaving] = useState(false);

  const isEdit = !!id;
  const isBuiltin = currentScenario?.is_builtin ?? false;

  useEffect(() => {
    // Load templates for dropdown
    axios.get<ApiResponse<TemplateSummary[]>>("/api/v1/templates").then((resp) => {
      setTemplates(resp.data.data ?? []);
    });
    if (id) fetchScenario(id);
    return () => clearCurrentScenario();
  }, [id, fetchScenario, clearCurrentScenario]);

  useEffect(() => {
    if (currentScenario && isEdit) {
      form.setFieldsValue({
        name: currentScenario.name,
        description: currentScenario.description,
        template_id: currentScenario.template_id,
      });
      setSelectedTemplateId(currentScenario.template_id);
      setSteps(
        currentScenario.steps.map((s) => ({
          register_name: s.register_name,
          anomaly_type: s.anomaly_type,
          anomaly_params: s.anomaly_params,
          trigger_at_seconds: s.trigger_at_seconds,
          duration_seconds: s.duration_seconds,
          sort_order: s.sort_order,
        })),
      );
    }
  }, [currentScenario, isEdit, form]);

  useEffect(() => {
    if (selectedTemplateId) {
      // Fetch template detail to get register names
      axios.get<ApiResponse<{ registers: { name: string }[] }>>(`/api/v1/templates/${selectedTemplateId}`).then((resp) => {
        const regs = resp.data.data?.registers ?? [];
        setRegisterNames(regs.map((r) => r.name));
      });
    }
  }, [selectedTemplateId]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      if (isEdit && id) {
        await scenarioApi.update(id, {
          name: values.name,
          description: values.description,
          steps,
        });
        message.success("Scenario updated");
      } else {
        const resp = await scenarioApi.create({
          template_id: values.template_id,
          name: values.name,
          description: values.description,
          steps,
        });
        message.success("Scenario created");
        navigate(`/scenarios/${resp.data?.id}`, { replace: true });
      }
    } catch {
      message.error("Failed to save scenario");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate("/scenarios")}>Back to List</Button>
      </Space>

      <Typography.Title level={3}>{isEdit ? "Edit Scenario" : "New Scenario"}</Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input disabled={isBuiltin} />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} disabled={isBuiltin} />
          </Form.Item>
          <Form.Item name="template_id" label="Template" rules={[{ required: true }]}>
            <Select
              disabled={isEdit}
              placeholder="Select template"
              onChange={(v) => { setSelectedTemplateId(v); setSteps([]); }}
              options={templates.map((t) => ({ value: t.id, label: t.name }))}
            />
          </Form.Item>
        </Form>
      </Card>

      {registerNames.length > 0 && (
        <Card title="Timeline" style={{ marginBottom: 16 }}>
          <TimelineEditor
            registerNames={registerNames}
            steps={steps}
            onChange={setSteps}
            readOnly={isBuiltin}
          />
        </Card>
      )}

      {!isBuiltin && (
        <Space>
          <Button type="primary" onClick={handleSave} loading={saving}>
            {isEdit ? "Save Changes" : "Create Scenario"}
          </Button>
          <Button onClick={() => navigate("/scenarios")}>Cancel</Button>
        </Space>
      )}
    </div>
  );
}
