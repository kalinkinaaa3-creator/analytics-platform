import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api",
});

let refreshPromise = null;
let unauthorizedNotified = false;

api.interceptors.request.use((config) => {
  const access = localStorage.getItem("access");

  if (access) {
    config.headers.Authorization = `Bearer ${access}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
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
