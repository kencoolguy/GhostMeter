export interface TemplateSummary {
  id: string;
  name: string;
  protocol: string;
  description: string | null;
  is_builtin: boolean;
  register_count: number;
  created_at: string;
  updated_at: string;
}

export interface RegisterDefinition {
  id?: string;
  name: string;
  address: number;
  function_code: number;
  data_type: string;
  byte_order: string;
  scale_factor: number;
  unit: string | null;
  description: string | null;
  sort_order: number;
}

export interface TemplateDetail
  extends Omit<TemplateSummary, "register_count"> {
  registers: RegisterDefinition[];
}

export interface CreateTemplate {
  name: string;
  protocol?: string;
  description?: string | null;
  registers: Omit<RegisterDefinition, "id">[];
}

export interface UpdateTemplate extends CreateTemplate {}

export interface TemplateClone {
  new_name?: string;
}

export interface ApiResponse<T> {
  data: T | null;
  message: string | null;
  success: boolean;
}
