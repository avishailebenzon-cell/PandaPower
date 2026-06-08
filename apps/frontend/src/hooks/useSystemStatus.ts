/**
 * Hook to fetch system status from backend
 */

import { useEffect, useState } from 'react';

export interface SystemStatus {
  id: string;
  name: string;
  status: 'active' | 'idle' | 'processing' | 'offline';
  detail?: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Fetch system status metrics
 */
async function fetchSystemStatus(): Promise<SystemStatus[]> {
  try {
    const responses = await Promise.allSettled([
      // Recruiter status
      fetch(`${API_BASE}/admin/recruiter/status`),
      // Pandi clients status
      fetch(`${API_BASE}/admin/pandi/clients?limit=1`),
      // Analytics summary
      fetch(`${API_BASE}/admin/analytics/kpi-summary`),
    ]);

    const statuses: SystemStatus[] = [];

    // Process recruiter status
    if (responses[0].status === 'fulfilled') {
      const res = await responses[0].value.json();
      if (res) {
        // Format the candidate/job an agent is currently working on.
        const workDetail = (cur: any): string | undefined => {
          if (!cur) return undefined;
          return `👤 ${cur.candidate_name} ← 💼 ${cur.job_title}`;
        };

        const totalMatches =
          (res.pending_tal || 0) +
          (res.in_conversation_tal || 0) +
          (res.awaiting_elad || 0) +
          (res.in_conversation_elad || 0);
        statuses.push({
          id: 'recruiter',
          name: 'מנהלת גיוס',
          status: totalMatches > 0 ? 'active' : 'idle',
          detail: `${totalMatches} התאמות בתהליך`,
        });

        statuses.push({
          id: 'carmit',
          name: 'כרמית - מיון ראשוני',
          status: res.carmit_current ? 'processing' : 'idle',
          detail:
            workDetail(res.carmit_current) ||
            `${res.pending_carmit || 0} בתור ביקורת`,
        });

        statuses.push({
          id: 'tal',
          name: 'טל - סוכנת ראשונית',
          status:
            (res.in_conversation_tal || 0) > 0 || res.tal_current
              ? 'processing'
              : 'idle',
          detail:
            workDetail(res.tal_current) || `${res.pending_tal || 0} בתור`,
        });

        statuses.push({
          id: 'elad',
          name: 'אלעד - הצבות',
          status:
            (res.in_conversation_elad || 0) > 0 || res.elad_current
              ? 'processing'
              : 'idle',
          detail:
            workDetail(res.elad_current) ||
            `${res.awaiting_elad || 0} ממתינים`,
        });
      }
    }

    // Process Pandi status
    if (responses[1].status === 'fulfilled') {
      const res = await responses[1].value.json();
      statuses.push({
        id: 'pandi',
        name: 'בוט Pandi WhatsApp',
        status: res && res.length > 0 ? 'active' : 'idle',
        detail: '🤖 פעיל',
      });
    }

    // Process email scan status
    const emailStatuses = await Promise.allSettled([
      fetch(`${API_BASE}/admin/email/status`),
    ]);

    if (emailStatuses[0].status === 'fulfilled') {
      const res = await emailStatuses[0].value.json();
      if (res) {
        let detail = '📧 מוכן';
        if (res.current_file_scanning) {
          detail = `📧 סורק: ${res.current_file_scanning}`;
        } else if (res.emails_processed_today > 0) {
          detail = `📧 ${res.emails_processed_today} מיילים היום • ${res.cv_files_extracted_today} CV`;
        }
        statuses.push({
          id: 'system',
          name: 'מערכת סריקת מיילים',
          status: res.current_file_scanning ? 'processing' : res.emails_processed_today > 0 ? 'active' : 'idle',
          detail,
        });
      }
    }

    return statuses;
  } catch (error) {
    console.error('Failed to fetch system status:', error);
    return [];
  }
}

/**
 * Hook to fetch and monitor system status
 */
export function useSystemStatus() {
  const [statuses, setStatuses] = useState<SystemStatus[]>([
    {
      id: 'agents',
      name: 'סוכני גיוס',
      status: 'active',
      detail: '7 סוכנים פעילים',
    },
    {
      id: 'recruiter',
      name: 'מנהלת גיוס',
      status: 'active',
      detail: 'טוען...',
    },
    {
      id: 'carmit',
      name: 'כרמית - מיון ראשוני',
      status: 'idle',
      detail: 'טוען...',
    },
    {
      id: 'tal',
      name: 'טל - סוכנת ראשונית',
      status: 'idle',
      detail: 'טוען...',
    },
    {
      id: 'elad',
      name: 'אלעד - הצבות',
      status: 'idle',
      detail: 'טוען...',
    },
    {
      id: 'pandi',
      name: 'בוט Pandi WhatsApp',
      status: 'active',
      detail: '🤖 פעיל',
    },
    {
      id: 'system',
      name: 'מערכת סריקת מיילים',
      status: 'active',
      detail: '📧 טוען...',
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Initial fetch
    const loadStatus = async () => {
      setIsLoading(true);
      const newStatuses = await fetchSystemStatus();
      if (newStatuses.length > 0) {
        // Merge with default statuses, prioritizing fetched data
        setStatuses((prev) => {
          const merged = [...prev];
          newStatuses.forEach((newStatus) => {
            const idx = merged.findIndex((s) => s.id === newStatus.id);
            if (idx !== -1) {
              merged[idx] = newStatus;
            } else {
              merged.push(newStatus);
            }
          });
          return merged;
        });
      }
      setIsLoading(false);
    };

    loadStatus();

    // Poll for updates every 15 seconds
    const interval = setInterval(loadStatus, 15000);

    return () => clearInterval(interval);
  }, []);

  return { statuses, isLoading };
}
