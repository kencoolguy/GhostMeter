import { message } from "antd";
import { create } from "zustand";
import { profileApi } from "../services/profileApi";
import type {
  CreateProfile,
  SimulationProfile,
  UpdateProfile,
} from "../types";

interface ProfileState {
  profiles: SimulationProfile[];
  loading: boolean;
  fetchProfiles: (templateId: string) => Promise<void>;
  createProfile: (data: CreateProfile) => Promise<boolean>;
  updateProfile: (id: string, data: UpdateProfile) => Promise<boolean>;
  deleteProfile: (id: string) => Promise<boolean>;
  clearProfiles: () => void;
}

export const useProfileStore = create<ProfileState>((set) => ({
  profiles: [],
  loading: false,

  fetchProfiles: async (templateId: string) => {
    set({ loading: true });
    try {
      const response = await profileApi.list(templateId);
      set({ profiles: response.data ?? [] });
    } catch {
      set({ profiles: [] });
    } finally {
      set({ loading: false });
    }
  },

  createProfile: async (data: CreateProfile) => {
    set({ loading: true });
    try {
      await profileApi.create(data);
      message.success("Profile created successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  updateProfile: async (id: string, data: UpdateProfile) => {
    set({ loading: true });
    try {
      await profileApi.update(id, data);
      message.success("Profile updated successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  deleteProfile: async (id: string) => {
    set({ loading: true });
    try {
      await profileApi.delete(id);
      message.success("Profile deleted successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  clearProfiles: () => set({ profiles: [] }),
}));
