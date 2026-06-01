// Test comment - checking if Vite watches main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { queryClient } from '@/lib/queryClient'
import { AdminLayout } from '@/components/AdminLayout'
import { WorkLayout } from '@/components/WorkLayout'
import { ProtectedRoute } from '@/components/ProtectedRoute'

// Admin Pages
import { AdminDashboard } from '@/pages/admin/AdminDashboard'
import { IntegrationsPage } from '@/pages/admin/IntegrationsPage'
import { EmailIntakePage } from '@/pages/admin/EmailIntakePage'
import { CVParsingPage } from '@/pages/admin/CVParsingPage'
import { ManualCVUploadPage } from '@/pages/admin/ManualCVUploadPage'
import { CVUploadStatusPage } from '@/pages/admin/CVUploadStatusPage'
import { CandidateManagementPage } from '@/pages/admin/CandidateManagementPage'
import JobMatchStatusDashboard from '@/pages/admin/JobMatchStatusDashboard'
import { SkillManagementPage } from '@/pages/admin/SkillManagementPage'
import { SecurityClassificationPage } from '@/pages/admin/SecurityClassificationPage'
import { AlertsPage } from '@/pages/admin/AlertsPage'
import { AgentManagementPage } from '@/pages/admin/AgentManagementPage'
import { CarmitPage } from '@/pages/admin/CarmitPage'
import { AnalyticsDashboard } from '@/pages/admin/AnalyticsDashboard'
import { SystemHealthPage } from '@/pages/admin/SystemHealthPage'
import WhatsAppAgentsSettingsPage from '@/pages/admin/WhatsAppAgentsSettingsPage'
import { PipedriveConfigPage } from '@/pages/admin/PipedriveConfigPage'
import { PandiPage } from '@/pages/admin/PandiPage'
import { PandiClientRequestPage } from '@/pages/admin/PandiClientRequestPage'
import { EmployeesPage } from '@/pages/admin/EmployeesPage'
import { ClientsPage } from '@/pages/admin/ClientsPage'
import { PotentialClientsPage } from '@/pages/admin/PotentialClientsPage'
import { OrganizationsPage } from '@/pages/admin/OrganizationsPage'
import { JobsListPage } from '@/pages/admin/JobsListPage'

// Work Pages
import { WorkDashboard } from '@/pages/work/WorkDashboard'
import { ConversationsPage } from '@/pages/work/ConversationsPage'
import { RecruitmentDepartment } from '@/pages/admin/RecruitmentDepartment'
import { RecruiterDashboard } from '@/pages/admin/RecruiterDashboard'
import { EladPageNew } from '@/pages/admin/EladPageNew'
import EladOutreachPage from '@/pages/admin/EladOutreachPage'
import PandiOutreachPage from '@/pages/admin/PandiOutreachPage'
import { TalPage } from '@/pages/admin/TalPage'
import { MatchFlowDashboard } from '@/pages/admin/MatchFlowDashboard'

// Other Pages
import { PandiAgent } from '@/pages/agents/PandiAgent'
import { StatusBar } from '@/components/StatusBar'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <StatusBar />
        <Routes>
          {/* ADMIN SECTION - System Administration */}
          <Route element={<AdminLayout />}>
            <Route path="/admin" element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>} />
            <Route path="/admin/integrations" element={<ProtectedRoute><IntegrationsPage /></ProtectedRoute>} />
            <Route path="/admin/pipedrive-config" element={<ProtectedRoute><PipedriveConfigPage /></ProtectedRoute>} />
            <Route path="/admin/pipedrive-employees" element={<ProtectedRoute><EmployeesPage /></ProtectedRoute>} />
            <Route path="/admin/pipedrive-clients" element={<ProtectedRoute><ClientsPage /></ProtectedRoute>} />
            <Route path="/admin/pipedrive-potential-clients" element={<ProtectedRoute><PotentialClientsPage /></ProtectedRoute>} />
            <Route path="/admin/pipedrive-organizations" element={<ProtectedRoute><OrganizationsPage /></ProtectedRoute>} />
            <Route path="/admin/pipedrive-jobs" element={<ProtectedRoute><JobsListPage /></ProtectedRoute>} />
            <Route path="/admin/email-intake" element={<ProtectedRoute><EmailIntakePage /></ProtectedRoute>} />
            <Route path="/admin/cv-parsing" element={<ProtectedRoute><CVParsingPage /></ProtectedRoute>} />
            <Route path="/admin/cv-upload" element={<ProtectedRoute><ManualCVUploadPage /></ProtectedRoute>} />
            <Route path="/admin/cv-upload-status/:batchId" element={<ProtectedRoute><CVUploadStatusPage /></ProtectedRoute>} />
            <Route path="/admin/candidates" element={<ProtectedRoute><CandidateManagementPage /></ProtectedRoute>} />
            <Route path="/admin/job-match-status" element={<ProtectedRoute><JobMatchStatusDashboard /></ProtectedRoute>} />
            <Route path="/admin/skills" element={<ProtectedRoute><SkillManagementPage /></ProtectedRoute>} />
            <Route path="/admin/security" element={<ProtectedRoute><SecurityClassificationPage /></ProtectedRoute>} />
            <Route path="/admin/alerts" element={<ProtectedRoute><AlertsPage /></ProtectedRoute>} />
            <Route path="/admin/agents" element={<ProtectedRoute><AgentManagementPage /></ProtectedRoute>} />
            <Route path="/admin/analytics" element={<ProtectedRoute><AnalyticsDashboard /></ProtectedRoute>} />
            <Route path="/admin/system-health" element={<ProtectedRoute><SystemHealthPage /></ProtectedRoute>} />
            <Route path="/admin/match-flow" element={<ProtectedRoute><MatchFlowDashboard /></ProtectedRoute>} />
            <Route path="/admin/whatsapp-agents" element={<ProtectedRoute><WhatsAppAgentsSettingsPage /></ProtectedRoute>} />
          </Route>

          {/* WORK SECTION - Recruiting Department Operations */}
          <Route element={<WorkLayout />}>
            {/* Main Work Dashboard */}
            <Route path="/recruiting" element={<ProtectedRoute><WorkDashboard /></ProtectedRoute>} />

            {/* Recruitment Departments (7 agents) */}
            <Route path="/recruiting/departments/:departmentCode" element={<ProtectedRoute><RecruitmentDepartment /></ProtectedRoute>} />

            {/* Recruiters */}
            <Route path="/recruiting/tal" element={<ProtectedRoute><TalPage /></ProtectedRoute>} />
            <Route path="/recruiting/elad" element={<ProtectedRoute><EladPageNew /></ProtectedRoute>} />
            <Route path="/recruiting/elad/outreach" element={<ProtectedRoute><EladOutreachPage /></ProtectedRoute>} />
            <Route path="/recruiting/pandi/outreach" element={<ProtectedRoute><PandiOutreachPage /></ProtectedRoute>} />

            {/* Conversations */}
            <Route path="/recruiting/conversations" element={<ProtectedRoute><ConversationsPage /></ProtectedRoute>} />

            {/* Recruitment Manager (Carmit) - Part of Work Area */}
            <Route path="/admin/carmit" element={<ProtectedRoute><CarmitPage /></ProtectedRoute>} />

            {/* Pipeline Flow Dashboard */}
            <Route path="/recruiting/match-flow" element={<ProtectedRoute><MatchFlowDashboard /></ProtectedRoute>} />

            {/* Pandi (WhatsApp client-intake agent) — works alongside the other
                AI recruiters, so its pages render inside the Work-area shell,
                not the admin shell. Both URL paths are kept for backwards
                compat with existing links/bookmarks. */}
            <Route path="/admin/pandi" element={<ProtectedRoute><PandiPage /></ProtectedRoute>} />
            <Route path="/admin/pandi-conversations" element={<ProtectedRoute><PandiClientRequestPage /></ProtectedRoute>} />
            <Route path="/recruiting/pandi" element={<ProtectedRoute><PandiClientRequestPage /></ProtectedRoute>} />
          </Route>

          {/* AGENT PAGES - AI Agents */}
          <Route path="/agents/pandi" element={<ProtectedRoute><PandiAgent /></ProtectedRoute>} />

          {/* Default Routes */}
          <Route path="/" element={<Navigate to="/recruiting" replace />} />
          <Route path="*" element={<Navigate to="/recruiting" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)
