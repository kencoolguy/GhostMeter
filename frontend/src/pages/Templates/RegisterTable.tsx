import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Input, InputNumber, Select, Table } from "antd";
import type { RegisterDefinition } from "../../types";

const DATA_TYPE_OPTIONS = [
  { value: "int16", label: "int16" },
  { value: "uint16", label: "uint16" },
  { value: "int32", label: "int32" },
  { value: "uint32", label: "uint32" },
  { value: "float32", label: "float32" },
  { value: "float64", label: "float64" },
];

const BYTE_ORDER_OPTIONS = [
  { value: "big_endian", label: "Big Endian" },
  { value: "little_endian", label: "Little Endian" },
  { value: "big_endian_word_swap", label: "Big Endian (Word Swap)" },
  { value: "little_endian_word_swap", label: "Little Endian (Word Swap)" },
];

const FC_OPTIONS = [
  { value: 3, label: "FC03 (Holding)" },
  { value: 4, label: "FC04 (Input)" },
];

interface RegisterTableProps {
  registers: Omit<RegisterDefinition, "id">[];
  onChange: (registers: Omit<RegisterDefinition, "id">[]) => void;
  disabled?: boolean;
  protocol?: string;
}

export function RegisterTable({
  registers,
  onChange,
  disabled = false,
  protocol = "modbus_tcp",
}: RegisterTableProps) {
  const isSnmp = protocol === "snmp";

  const updateRow = (index: number, field: string, value: unknown) => {
    const updated = [...registers];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  };

  const addRow = () => {
    onChange([
      ...registers,
      {
        name: "",
        address: registers.length,
        function_code: isSnmp ? 4 : 3,
        data_type: "float32",
        byte_order: "big_endian",
        scale_factor: 1.0,
        unit: null,
        description: null,
        sort_order: registers.length,
        ...(isSnmp ? { oid: "" } : {}),
      },
    ]);
  };

  const deleteRow = (index: number) => {
    const updated = registers.filter((_, i) => i !== index);
    onChange(updated.map((r, i) => ({ ...r, sort_order: i, address: isSnmp ? i : r.address })));
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      width: 140,
      render: (_: string, __: unknown, index: number) => (
        <Input
          value={registers[index].name}
          onChange={(e) => updateRow(index, "name", e.target.value)}
          disabled={disabled}
          size="small"
        />
      ),
    },
    ...(isSnmp
      ? [
          {
            title: "OID",
            dataIndex: "oid",
            width: 260,
            render: (_: string | null | undefined, __: unknown, index: number) => (
              <Input
                value={registers[index].oid ?? ""}
                placeholder="1.3.6.1.2.1.33..."
                onChange={(e) => updateRow(index, "oid", e.target.value)}
                disabled={disabled}
                size="small"
                style={{ fontFamily: "monospace", fontSize: 12 }}
              />
            ),
          },
        ]
      : [
          {
            title: "Address",
            dataIndex: "address",
            width: 90,
            render: (_: number, __: unknown, index: number) => (
              <InputNumber
                value={registers[index].address}
                onChange={(val) => updateRow(index, "address", val ?? 0)}
                disabled={disabled}
                size="small"
                min={0}
                style={{ width: "100%" }}
              />
            ),
          },
          {
            title: "FC",
            dataIndex: "function_code",
            width: 130,
            render: (_: number, __: unknown, index: number) => (
              <Select
                value={registers[index].function_code}
                onChange={(val) => updateRow(index, "function_code", val)}
                options={FC_OPTIONS}
                disabled={disabled}
                size="small"
                style={{ width: "100%" }}
              />
            ),
          },
        ]),
    {
      title: "Data Type",
      dataIndex: "data_type",
      width: 110,
      render: (_: string, __: unknown, index: number) => (
        <Select
          value={registers[index].data_type}
          onChange={(val) => updateRow(index, "data_type", val)}
          options={DATA_TYPE_OPTIONS}
          disabled={disabled}
          size="small"
          style={{ width: "100%" }}
        />
      ),
    },
    ...(!isSnmp
      ? [
          {
            title: "Byte Order",
            dataIndex: "byte_order",
            width: 170,
            render: (_: string, __: unknown, index: number) => (
              <Select
                value={registers[index].byte_order}
                onChange={(val) => updateRow(index, "byte_order", val)}
                options={BYTE_ORDER_OPTIONS}
                disabled={disabled}
                size="small"
                style={{ width: "100%" }}
              />
            ),
          },
        ]
      : []),
    {
      title: "Scale",
      dataIndex: "scale_factor",
      width: 80,
      render: (_: number, __: unknown, index: number) => (
        <InputNumber
          value={registers[index].scale_factor}
          onChange={(val) => updateRow(index, "scale_factor", val ?? 1.0)}
          disabled={disabled}
          size="small"
          step={0.1}
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "Unit",
      dataIndex: "unit",
      width: 70,
      render: (_: string | null, __: unknown, index: number) => (
        <Input
          value={registers[index].unit ?? ""}
          onChange={(e) => updateRow(index, "unit", e.target.value || null)}
          disabled={disabled}
          size="small"
        />
      ),
    },
    {
      title: "Description",
      dataIndex: "description",
      render: (_: string | null, __: unknown, index: number) => (
        <Input
          value={registers[index].description ?? ""}
          onChange={(e) =>
            updateRow(index, "description", e.target.value || null)
          }
          disabled={disabled}
          size="small"
        />
      ),
    },
    ...(disabled
      ? []
      : [
          {
            title: "",
            width: 40,
            render: (_: unknown, __: unknown, index: number) => (
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => deleteRow(index)}
              />
            ),
          },
        ]),
  ];

  return (
    <div>
      <Table
        columns={columns}
        dataSource={registers.map((r, i) => ({ ...r, _key: i }))}
        rowKey="_key"
        pagination={false}
        size="small"
        scroll={{ x: 1000 }}
      />
      {!disabled && (
        <Button
          type="dashed"
          onClick={addRow}
          icon={<PlusOutlined />}
          style={{ width: "100%", marginTop: 8 }}
        >
          Add Register
        </Button>
      )}
    </div>
  );
}
