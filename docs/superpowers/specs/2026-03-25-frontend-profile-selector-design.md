# Frontend Profile Selector — Design Spec

**Date:** 2026-03-25
**Status:** Reviewed
**Phase:** 8.3

## Goal

Add frontend UI for simulation profile management and selection. Users can browse, create, edit, and delete profiles within each template, and select a profile when creating devices.

## Context

Backend profile CRUD API is already implemented at `/api/v1/simulation-profiles` with full support for list, get, create, update, delete. Built-in profiles exist for all three seed templates. The `profile_id` field on device creation is already supported by the backend.

The frontend currently has zero profile-related code — no types, API client, store, or UI components.

## Design Decisions

- **Profile management location:** Profiles tab inside the template detail page (TemplateForm). Profiles are bound to templates, so co-locating them is natural.
- **Profile selection in device creation:** Visible dropdown (not hidden in advanced settings). Automatically appears after template selection, pre-selects the default profile.
- **Profile CRUD scope:** Full CRUD including per-register config editing. The config editor follows the same pattern as the Simulation page's DataModeTab.

## New Files

| File | Purpose |
|------|---------|
| `frontend/src/types/profile.ts` | TypeScript interfaces for profile data |
| `frontend/src/services/profileApi.ts` | API client for `/api/v1/simulation-profiles` |
| `frontend/src/stores/profileStore.ts` | Zustand store for profile state and actions |
| `frontend/src/pages/Templates/ProfilesTab.tsx` | Profile list table inside template detail |
| `frontend/src/pages/Templates/ProfileFormModal.tsx` | Modal for creating/editing profiles with config table |

## Modified Files

| File | Change |
|------|--------|
| `frontend/src/pages/Templates/TemplateForm.tsx` | Wrap content in Tabs: "Register Map" + "Profiles" (edit/view mode, not create) |
| `frontend/src/pages/Devices/CreateDeviceModal.tsx` | Add profile Select dropdown after template selection |
| `frontend/src/types/device.ts` | Add `profile_id?: string \| null` to `CreateDevice` and `BatchCreateDevice` |
| `frontend/src/types/index.ts` | Export profile types |

## Component Design

### 1. Profile Selection in CreateDeviceModal

When the user selects a template:

1. Fetch profiles for that template via `profileStore.fetchProfiles(templateId)`
2. Show a `Select` dropdown below the template selector
3. While loading: show disabled Select with placeholder "Loading profiles..."
4. If fetch fails: show disabled Select with placeholder "Failed to load profiles"
5. If no profiles exist for the template: hide the dropdown entirely
6. Options: each profile by name, plus a "None (no profile)" option
7. Pre-select the profile where `is_default === true`
8. Map selection to `profile_id` in the create request:
   - Selected profile → `profile_id: uuid`
   - "None" → `profile_id: null` (explicit skip)
   - No selection / absent → omit `profile_id` (backend auto-applies default)

Both Single and Batch tabs share the same profile dropdown state — when the user switches tabs, the selected profile is preserved (managed via shared state outside the individual form instances).

Template change clears the profile selection and re-fetches profiles for the new template.

### 2. ProfilesTab (Template Detail)

Renders inside the "Profiles" tab of TemplateForm. Shown for both edit and view (read-only/built-in) modes — users can always view profiles, but create/delete actions are hidden in view mode for built-in templates.

**Table columns:**
- Name
- Description (truncated)
- Built-in badge (`Tag` component)
- Default badge (`Tag` component, green)
- Actions: Edit, Delete, Set as Default

**Behavior:**
- Built-in profiles: Edit opens modal with name/description editable, configs read-only. Delete is disabled (button hidden or greyed out with tooltip).
- User profiles: Full edit and delete (with confirmation modal).
- Set as Default: calls `profileApi.update(id, { is_default: true })`. Only one default per template (backend enforces). The button is hidden/disabled for the profile that is already default. After success, refresh the profile list to reflect the old default losing its flag.
- "New Profile" button opens ProfileFormModal in create mode.

### 3. ProfileFormModal

Modal with two sections:

**Top section — metadata:**
- Name (required, text input)
- Description (optional, text area)

**Bottom section — register configs:**
- Table with one row per register from the template
- Columns: Register Name (read-only), Data Mode (select: static/random/daily_curve/computed/accumulator), Mode Params (JSON or structured inputs), Enabled (switch), Interval ms (number input)
- Registers are pre-populated from the template's register definitions
- For edit mode: existing config values are loaded; unconfigured registers show defaults (static, enabled, 1000ms)

**Submit:** Sends `configs` array with all register entries to the create/update API endpoint.

**Built-in profile edit:** Config table is rendered read-only (all inputs disabled). Only name and description are editable.

### 4. Data Flow

```
profileApi.ts
  → list(templateId): GET /simulation-profiles?template_id={id}
  → get(profileId): GET /simulation-profiles/{id}
  → create(data): POST /simulation-profiles
  → update(profileId, data): PUT /simulation-profiles/{id}
  → delete(profileId): DELETE /simulation-profiles/{id}

profileStore.ts
  → profiles: SimulationProfile[]
  → loading: boolean
  → fetchProfiles(templateId)
  → createProfile(data) → profileApi.create
  → updateProfile(id, data) → profileApi.update
  → deleteProfile(id) → profileApi.delete
  (errors surfaced via antd message.error, matching existing store pattern)

CreateDeviceModal
  → on template change → profileStore.fetchProfiles(templateId)
  → profile dropdown renders from profileStore.profiles
  → selected profile_id sent with device create request

TemplateForm (edit/view mode)
  → Tab "Profiles" → <ProfilesTab templateId={id} registers={registers} />
  → ProfilesTab fetches profiles on mount
  → CRUD actions via profileStore
```

### 5. TypeScript Types

```typescript
// Use the existing DataMode union from simulation.ts for type safety
type DataMode = "static" | "random" | "daily_curve" | "computed" | "accumulator";

interface ProfileConfigEntry {
  register_name: string;
  data_mode: DataMode;
  mode_params: Record<string, unknown>;
  is_enabled: boolean;
  update_interval_ms: number;
}

interface SimulationProfile {
  id: string;
  template_id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  is_default: boolean;
  configs: ProfileConfigEntry[];
  created_at: string;
  updated_at: string;
}

interface CreateProfile {
  template_id: string;
  name: string;
  description?: string | null;
  is_default?: boolean;
  configs: ProfileConfigEntry[];
}

interface UpdateProfile {
  name?: string;
  description?: string | null;
  is_default?: boolean;
  configs?: ProfileConfigEntry[];
}
```

Note: Backend returns `configs` as `list[dict]`. The frontend applies the `ProfileConfigEntry` type overlay — the keys are guaranteed by the backend seed/service logic.

Additionally, add `profile_id` to existing device types:

```typescript
// In types/device.ts
interface CreateDevice {
  // ... existing fields ...
  profile_id?: string | null;
}

interface BatchCreateDevice {
  // ... existing fields ...
  profile_id?: string | null;
}
```

## Testing

- Profile CRUD operations via the Profiles tab
- Profile selection in device creation (single + batch)
- Default profile pre-selection
- Built-in profile protection (configs read-only, no delete)
- Template change resets profile dropdown
- Set as Default refreshes list and updates badges
- Zero profiles hides dropdown in CreateDeviceModal

## Out of Scope

- "Save current simulation config as profile" shortcut from the Simulation page (future enhancement)
- Profile duplication/clone feature
- Profile import/export as standalone files
