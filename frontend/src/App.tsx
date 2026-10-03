import { BrowserRouter, Routes, Route } from 'react-router-dom'
import RootLayout from './components/ui/RootLayout'
import DashboardPage from './pages/DashboardPage'
import DownloadsPage from './pages/DownloadsPage'
import QueuePage from './pages/QueuePage'
import HistoryPage from './pages/HistoryPage'
import FilesPage from './pages/FilesPage'
import SettingsPage from './pages/SettingsPage'
import SecurityPage from './pages/SecurityPage'
import AnalyticsPage from './pages/AnalyticsPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="downloads" element={<DownloadsPage />} />
          <Route path="queue" element={<QueuePage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="files" element={<FilesPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App