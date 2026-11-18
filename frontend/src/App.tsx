import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactElement } from 'react'
import { useAuth } from './lib/auth'
import { FullPageSpinner } from './components/ui'
import { Layout, DatasetShell } from './components/shell'
import { Login, Signup } from './pages/auth'
import { Projects, ProjectDetail } from './pages/projects'
import { ProfileTab } from './pages/profile'
import { CleanTab } from './pages/clean'
import { ExploreTab } from './pages/explore'
import { StatsTab } from './pages/stats'
import { AnalystTab } from './pages/analyst'
import { ReportsTab } from './pages/reports'

function Protected({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <FullPageSpinner label="Restoring your session…" />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return children
}

function PublicOnly({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth()
  if (loading) return <FullPageSpinner label="Loading DATAPILOT…" />
  if (user) return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
      <Route path="/signup" element={<PublicOnly><Signup /></PublicOnly>} />

      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<Projects />} />
        <Route path="projects/:projectId" element={<ProjectDetail />} />
        <Route path="datasets/:datasetId" element={<DatasetShell />}>
          <Route index element={<ProfileTab />} />
          <Route path="clean" element={<CleanTab />} />
          <Route path="explore" element={<ExploreTab />} />
          <Route path="stats" element={<StatsTab />} />
          <Route path="analyst" element={<AnalystTab />} />
          <Route path="reports" element={<ReportsTab />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
