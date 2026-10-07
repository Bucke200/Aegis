import { Navigate, Route, Routes } from 'react-router-dom'

import { RequireAuth } from './components/RequireAuth'
import { AppShell } from './components/AppShell'
import { IncidentDetailPage } from './pages/IncidentDetailPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { LoginPage } from './pages/LoginPage'
import { VipDetailPage } from './pages/VipDetailPage'
import { VipsPage } from './pages/VipsPage'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/incidents" replace />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/incidents/:incidentId" element={<IncidentDetailPage />} />
        <Route path="/vips" element={<VipsPage />} />
        <Route path="/vips/:vipId" element={<VipDetailPage />} />
        <Route path="*" element={<Navigate to="/incidents" replace />} />
      </Route>
    </Routes>
  )
}
