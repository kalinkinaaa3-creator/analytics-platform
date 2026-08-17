import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { api } from "../api/client";

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

    localStorage.setItem("access", response.data.access);
    localStorage.setItem("refresh", response.data.refresh);
    localStorage.setItem("username", usernameValue);

    setAccess(response.data.access);
    setRefresh(response.data.refresh);
    setUsername(usernameValue);
  }

  const logout = useCallback(() => {
    localStorage.removeItem("access");
    localStorage.removeItem("refresh");
    localStorage.removeItem("username");

    setAccess(null);
    setRefresh(null);
    setUsername(null);
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
