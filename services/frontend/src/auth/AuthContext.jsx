import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "../api/client";
import axios from "axios";
import { setOrganizationId } from "../organizations/storage";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [access, setAccess] = useState(localStorage.getItem("access"));
  const [refresh, setRefresh] = useState(localStorage.getItem("refresh"));
  const [username, setUsername] = useState(localStorage.getItem("username"));

  const isAuthenticated = Boolean(access);

  async function login(usernameValue, password) {
    const response = await api.post("/token/", {
      username: usernameValue,
      password,
    });

    return { ...response.data, username: usernameValue };
  }

  async function completeLogin(session, organizationId) {
    // Keep the pending login in memory until the organization is selected.
    // Use its own credentials, independently of any previous browser session.
    let organization = session.organization;
    if (session.organizations.length > 1) {
      const { data } = await axios.post(`${api.defaults.baseURL}/v1/organizations/switch/`, {
        organization_id: organizationId,
      }, { headers: {
        Authorization: `Bearer ${session.access}`,
        "X-Organization-ID": String(session.organization.id),
      } });
      organization = data.organization;
    }
    localStorage.setItem("access", session.access);
    localStorage.setItem("refresh", session.refresh);
    localStorage.setItem("username", session.username);
    setOrganizationId(organization.id);

    setAccess(session.access);
    setRefresh(session.refresh);
    setUsername(session.username);
  }

  const logout = useCallback(() => {
    setOrganizationId(null);
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    localStorage.removeItem("username");

    setAccess(null);
    setRefresh(null);
    setUsername(null);
  }, []);

  useEffect(() => {
    function handleAuthStorage(event) {
      if (event.key === "username" || (event.key === "access" && !event.newValue)) window.location.reload();
    }
    window.addEventListener("storage", handleAuthStorage);
    return () => window.removeEventListener("storage", handleAuthStorage);
  }, []);

  useEffect(() => {
    function handleUnauthorized() {
      logout();
    }

    window.addEventListener(
      "auth:unauthorized",
      handleUnauthorized,
    );

    return () => {
      window.removeEventListener(
        "auth:unauthorized",
        handleUnauthorized,
      );
    };
  }, [logout]);

  return (
    <AuthContext.Provider
      value={{
        access,
        refresh,
        username,
        isAuthenticated,
        login,
        completeLogin,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
