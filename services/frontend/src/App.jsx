import { BrowserRouter, Routes, Route } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { MainLayout } from "./layouts/MainLayout";

import { LoginPage } from "./pages/LoginPage";
import { HomePage } from "./pages/HomePage";
import { DashboardPage } from "./pages/DashboardPage";
import { AccessDeniedPage } from "./pages/AccessDeniedPage";

import { PublicLayout } from "./layouts/PublicLayout";
import { PublicDashboardPage } from "./pages/PublicDashboardPage";

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route path="/public/:token" element={<PublicLayout />}>
            <Route index element={<HomePage />} />
            <Route
              path="dashboards/:dashboardSlug"
              element={<PublicDashboardPage />}
            />
          </Route>

          <Route path="/public-group/:token" element={<PublicLayout />}>
            <Route index element={<HomePage />} />
            <Route
              path="dashboard/:dashboardSlug"
              element={<PublicDashboardPage />}
            />
          </Route>

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<HomePage />} />
            <Route
              path="dashboards/:dashboardSlug"
              element={<DashboardPage />}
            />
            <Route path="access-denied" element={<AccessDeniedPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;