import axios from "axios";
import { getOrganizationId } from "../organizations/storage";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api",
});

let refreshPromise = null;
let unauthorizedNotified = false;

api.interceptors.request.use((config) => {
  const session = localStorage.getItem("refresh");
  if (config._authSession !== undefined && config._authSession !== session) {
    throw new axios.CanceledError("Authentication session changed before retry");
  }
  config._authSession = session;
  const url = String(config.url || "");
  const organizationId = getOrganizationId();
  const path = new URL(url, window.location.origin).pathname;
  const isPublic = /^\/(?:api\/)?v1\/(?:dashboards|datasets)\/public(?:-group)?\/[0-9a-f-]{36}\//i.test(path);
  if (organizationId && !path.includes("/token/") && !isPublic) {
    config.headers["X-Organization-ID"] = organizationId;
  }
  const access = localStorage.getItem("access");

  if (access) {
    config.headers.Authorization = `Bearer ${access}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => {
    if (response.config?._authSession !== localStorage.getItem("refresh")) {
      throw new axios.CanceledError("Authentication session changed during request");
    }
    if (String(response.config?.url || "").endsWith("/token/")) unauthorizedNotified = false;
    return response;
  },
  async (error) => {
    const originalRequest = error.config;
    if (originalRequest && originalRequest._authSession !== localStorage.getItem("refresh")) {
      return Promise.reject(new axios.CanceledError("Authentication session changed during request"));
    }
    const status = error.response?.status;
    const requestUrl = String(
      originalRequest?.url || ""
    );
    const isTokenRequest = (
      requestUrl.includes("/token/")
    );

    if (
      status !== 401
      || !originalRequest
      || originalRequest._retry
      || isTokenRequest
    ) {
      return Promise.reject(error);
    }

    const refresh = localStorage.getItem("refresh");

    if (!refresh) {
      if (!unauthorizedNotified) {
        unauthorizedNotified = true;
        window.dispatchEvent(
          new CustomEvent("auth:unauthorized")
        );
      }
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    if (!refreshPromise) {
      refreshPromise = axios.post(
        `${api.defaults.baseURL}/token/refresh/`,
        { refresh },
      )
        .then((response) => {
          if (localStorage.getItem("refresh") !== refresh) {
            throw new axios.CanceledError("Authentication session changed during refresh");
          }
          const access = response.data?.access;

          if (!access) {
            throw new Error(
              "Token refresh response has no access token"
            );
          }

          localStorage.setItem("access", access);
          unauthorizedNotified = false;
          return access;
        })
        .finally(() => {
          refreshPromise = null;
        });
    }

    try {
      const access = await refreshPromise;
      originalRequest.headers = {
        ...originalRequest.headers,
        Authorization: `Bearer ${access}`,
      };
      return api(originalRequest);
    } catch (refreshError) {
      if (localStorage.getItem("refresh") !== refresh) {
        return Promise.reject(new axios.CanceledError("Authentication session changed during refresh"));
      }
      if (axios.isCancel(refreshError)) return Promise.reject(refreshError);
      if (!unauthorizedNotified) {
        unauthorizedNotified = true;
        window.dispatchEvent(
          new CustomEvent("auth:unauthorized")
        );
      }
      return Promise.reject(refreshError);
    }
  },
);
