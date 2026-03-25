import { Button, Card, Form, Input, Select, Space, Tabs, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { RegisterDefinition } from "../../types";
import { useTemplateStore } from "../../stores/templateStore";
import { ProfilesTab } from "./ProfilesTab";
import { RegisterTable } from "./RegisterTable";

const PROTOCOL_OPTIONS = [{ value: "modbus_tcp", label: "Modbus TCP" }];

export default function TemplateForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const {
    currentTemplate,
    loading,
    fetchTemplate,
    createTemplate,
    updateTemplate,
    clearCurrentTemplate,
  } = useTemplateStore();

  const isEdit = Boolean(id);
  const isReadOnly = Boolean(currentTemplate?.is_builtin);
  const [registers, setRegisters] = useState<Omit<RegisterDefinition, "id">[]>(
    []
  );

  useEffect(() => {
    if (id) {
      fetchTemplate(id);
    }
    return () => clearCurrentTemplate();
  }, [id, fetchTemplate, clearCurrentTemplate]);

  useEffect(() => {
    if (currentTemplate && isEdit) {
      form.setFieldsValue({
        name: currentTemplate.name,
        protocol: currentTemplate.protocol,
        description: currentTemplate.description,
      });
      setRegisters(
        currentTemplate.registers.map(({ id: _id, ...rest }) => rest)
      );
    }
  }, [currentTemplate, isEdit, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = {
      ...values,
      registers: registers.map((r, i) => ({ ...r, sort_order: i })),
    };

    let result;
    if (isEdit && id) {
      result = await updateTemplate(id, payload);
    } else {
      result = await createTemplate(payload);
    }

    if (result) {
      navigate("/templates");
    }
  };

  const pageTitle = isReadOnly
    ? "View Template"
    : isEdit
      ? "Edit Template"
      : "New Template";

  return (
    <div>
      <Space align="center" style={{ marginBottom: 16 }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          {pageTitle}
        </Typography.Title>
        {isReadOnly && <Tag color="blue">Built-in</Tag>}
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ protocol: "modbus_tcp" }}
        >
          <Form.Item
            name="name"
            label="Template Name"
            rules={[{ required: true, message: "Please enter a name" }]}
          >
            <Input
              placeholder="e.g. My Custom Meter"
              disabled={isReadOnly}
            />
          </Form.Item>
          <Form.Item name="protocol" label="Protocol">
            <Select options={PROTOCOL_OPTIONS} disabled={isReadOnly} />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea
              rows={2}
              placeholder="Optional description"
              disabled={isReadOnly}
            />
          </Form.Item>
        </Form>
      </Card>

      {isEdit ? (
        <Card style={{ marginBottom: 16 }}>
          <Tabs
            defaultActiveKey="registers"
            items={[
              {
                key: "registers",
                label: "Register Map",
                children: (
                  <RegisterTable
                    registers={registers}
                    onChange={setRegisters}
                    disabled={isReadOnly}
                  />
                ),
              },
              {
                key: "profiles",
                label: "Profiles",
                children: id ? (
                  <ProfilesTab
                    templateId={id}
                    registers={registers}
                    readOnly={isReadOnly}
                  />
                ) : null,
              },
            ]}
          />
        </Card>
      ) : (
        <Card title="Register Map" style={{ marginBottom: 16 }}>
          <RegisterTable
            registers={registers}
            onChange={setRegisters}
            disabled={isReadOnly}
          />
        </Card>
      )}

      {isReadOnly ? (
        <Button onClick={() => navigate("/templates")}>Back</Button>
      ) : (
        <Space>
          <Button type="primary" onClick={handleSubmit} loading={loading}>
            {isEdit ? "Save Changes" : "Create Template"}
          </Button>
          <Button onClick={() => navigate("/templates")}>Cancel</Button>
        </Space>
      )}
    </div>
  );
}
