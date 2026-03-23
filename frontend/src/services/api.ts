import { message } from "antd";
import axios from "axios";
import type { ApiErrorResponse } from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data) {
      const data = error.response.data as ApiErrorResponse;
      message.error(data.detail || "An error occurred");
    } else if (error.message) {
      message.error(error.message);
    }
    return Promise.reject(error);
  }
);

export { api };
