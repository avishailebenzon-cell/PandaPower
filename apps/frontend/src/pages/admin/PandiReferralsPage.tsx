/**
 * Phase 34: Pandi Referrals Management Dashboard
 * Track client referrals, SLA deadlines, and referral progress
 */

import React, { useState, useEffect } from 'react';
import { format, formatDistanceToNow } from 'date-fns';
import { he } from 'date-fns/locale';
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Select,
  MenuItem,
  TextField,
  Box,
  Card,
  CardContent,
  Grid,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Clock as ClockIcon,
  Error as ErrorIcon,
  Hourglass as HourglassIcon,
} from '@mui/icons-material';

interface Referral {
  referral_number: string;
  candidate_number: string;
  client_name: string | null;
  status: string;
  sla_deadline: string | null;
  is_sla_breached: boolean;
  presented_at: string;
  created_at: string;
}

interface ReferralDetail extends Referral {
  referral_id: string;
  client_phone: string | null;
  job_context: any;
  presented_payload: any;
  llm_match_reasoning: string | null;
  status_notes: string | null;
}

// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || '';

const STATUS_LABELS: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'info' | 'default' }> = {
  presented: { label: 'הוצג', color: 'info' },
  client_interested: { label: 'לקוח בעניין', color: 'warning' },
  client_declined: { label: 'לקוח דחה', color: 'error' },
  in_recruitment_process: { label: 'תהליך גיוס', color: 'warning' },
  hired: { label: 'נשכר! ✓', color: 'success' },
  rejected_by_client: { label: 'לקוח דחה', color: 'error' },
};

export default function PandiReferralsPage() {
  const [referrals, setReferrals] = useState<Referral[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [slaFilter, setSlaFilter] = useState<string>('');
  const [selectedReferral, setSelectedReferral] = useState<ReferralDetail | null>(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [newStatus, setNewStatus] = useState<string>('');
  const [statusNotes, setStatusNotes] = useState<string>('');

  // Load referrals
  useEffect(() => {
    loadReferrals();
  }, [statusFilter, slaFilter]);

  const loadReferrals = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append('status', statusFilter);
      if (slaFilter === 'breached') params.append('sla_breached', 'true');
      if (slaFilter === 'active') params.append('sla_breached', 'false');

      const response = await fetch(`${API_BASE}/admin/pandi/referrals?${params.toString()}`);
      const data = await response.json();
      setReferrals(data);
    } catch (error) {
      console.error('Failed to load referrals:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadReferralDetail = async (referralNumber: string) => {
    try {
      const response = await fetch(`${API_BASE}/admin/pandi/referrals/${referralNumber}`);
      const data = await response.json();
      setSelectedReferral(data);
      setDetailDialogOpen(true);
      setNewStatus(data.status);
    } catch (error) {
      console.error('Failed to load referral detail:', error);
    }
  };

  const handleStatusChange = async () => {
    if (!selectedReferral || newStatus === selectedReferral.status) {
      setStatusDialogOpen(false);
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/admin/pandi/referrals/${selectedReferral.referral_number}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          new_status: newStatus,
          notes: statusNotes,
        }),
      });

      if (response.ok) {
        setStatusDialogOpen(false);
        loadReferrals();
        setDetailDialogOpen(false);
      }
    } catch (error) {
      console.error('Failed to update status:', error);
    }
  };

  const getSLAStatus = (deadline: string | null, breached: boolean) => {
    if (!deadline) return null;

    const deadlineDate = new Date(deadline);
    const now = new Date();
    const hoursLeft = (deadlineDate.getTime() - now.getTime()) / (1000 * 60 * 60);

    if (breached) {
      return (
        <Chip
          icon={<ErrorIcon />}
          label={`חרג ב-${Math.abs(Math.floor(hoursLeft))} שעות`}
          color="error"
          size="small"
        />
      );
    }

    if (hoursLeft < 24) {
      return (
        <Chip
          icon={<HourglassIcon />}
          label={`${Math.floor(hoursLeft)} שעות נותרו`}
          color="warning"
          size="small"
        />
      );
    }

    return (
      <Chip
        icon={<ClockIcon />}
        label={formatDistanceToNow(deadlineDate, { locale: he })}
        color="success"
        size="small"
      />
    );
  };

  // Stats cards
  const stats = {
    total: referrals.length,
    breached: referrals.filter(r => r.is_sla_breached).length,
    inProgress: referrals.filter(r => r.status === 'client_interested' || r.status === 'in_recruitment_process').length,
    hired: referrals.filter(r => r.status === 'hired').length,
  };

  return (
    <div style={{ padding: '24px' }}>
      <h1>🎯 ניהול פניות - אלעד</h1>

      {/* Stats Cards */}
      <Grid container spacing={2} style={{ marginBottom: '24px' }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <h3>סה"כ פניות</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold' }}>{stats.total}</p>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <h3>בתהליך</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold', color: '#ff9800' }}>{stats.inProgress}</p>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <h3>חרגו SLA</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold', color: '#f44336' }}>{stats.breached}</p>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <h3>נשכרו</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold', color: '#4caf50' }}>{stats.hired}</p>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Box style={{ marginBottom: '24px', display: 'flex', gap: '12px' }}>
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ width: '200px' }}
          displayEmpty
        >
          <MenuItem value="">כל הסטטוסים</MenuItem>
          <MenuItem value="client_interested">לקוח בעניין</MenuItem>
          <MenuItem value="in_recruitment_process">בתהליך גיוס</MenuItem>
          <MenuItem value="hired">נשכרו</MenuItem>
        </Select>

        <Select
          value={slaFilter}
          onChange={(e) => setSlaFilter(e.target.value)}
          style={{ width: '200px' }}
          displayEmpty
        >
          <MenuItem value="">כל ה-SLAs</MenuItem>
          <MenuItem value="breached">חרגו SLA</MenuItem>
          <MenuItem value="active">בתוקף</MenuItem>
        </Select>
      </Box>

      {/* Referrals Table */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead style={{ backgroundColor: '#f5f5f5' }}>
            <TableRow>
              <TableCell><strong>מס' פנייה</strong></TableCell>
              <TableCell><strong>מועמד</strong></TableCell>
              <TableCell><strong>לקוח</strong></TableCell>
              <TableCell><strong>סטטוס</strong></TableCell>
              <TableCell><strong>SLA</strong></TableCell>
              <TableCell><strong>פעולות</strong></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {referrals.map((ref) => (
              <TableRow key={ref.referral_number} style={{ opacity: ref.is_sla_breached ? 0.7 : 1 }}>
                <TableCell>
                  <strong>{ref.referral_number}</strong>
                </TableCell>
                <TableCell>{ref.candidate_number}</TableCell>
                <TableCell>{ref.client_name || 'לא זוהה'}</TableCell>
                <TableCell>
                  {STATUS_LABELS[ref.status] && (
                    <Chip
                      label={STATUS_LABELS[ref.status].label}
                      color={STATUS_LABELS[ref.status].color}
                      size="small"
                    />
                  )}
                </TableCell>
                <TableCell>{getSLAStatus(ref.sla_deadline, ref.is_sla_breached)}</TableCell>
                <TableCell>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => loadReferralDetail(ref.referral_number)}
                  >
                    פרטים
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Detail Dialog */}
      <Dialog open={detailDialogOpen} onClose={() => setDetailDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>📋 פרטי הפנייה: {selectedReferral?.referral_number}</DialogTitle>
        <DialogContent>
          {selectedReferral && (
            <Box style={{ marginTop: '16px' }}>
              <div><strong>מועמד:</strong> {selectedReferral.candidate_number}</div>
              <div><strong>לקוח:</strong> {selectedReferral.client_name} ({selectedReferral.client_phone})</div>
              <div><strong>סטטוס:</strong> {STATUS_LABELS[selectedReferral.status]?.label}</div>
              <div><strong>SLA Deadline:</strong> {selectedReferral.sla_deadline ? format(new Date(selectedReferral.sla_deadline), 'dd/MM/yyyy HH:mm') : 'N/A'}</div>
              <div><strong>Match Reasoning:</strong> {selectedReferral.llm_match_reasoning}</div>
              <div><strong>Status Notes:</strong> {selectedReferral.status_notes || '-'}</div>

              <TextField
                fullWidth
                multiline
                rows={4}
                label="תיאור העבודה"
                value={selectedReferral.job_context?.title || ''}
                disabled
                style={{ marginTop: '16px' }}
              />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailDialogOpen(false)}>סגור</Button>
          <Button variant="contained" onClick={() => setStatusDialogOpen(true)}>
            עדכן סטטוס
          </Button>
        </DialogActions>
      </Dialog>

      {/* Status Update Dialog */}
      <Dialog open={statusDialogOpen} onClose={() => setStatusDialogOpen(false)}>
        <DialogTitle>עדכן סטטוס פנייה</DialogTitle>
        <DialogContent style={{ paddingTop: '16px' }}>
          <Select
            fullWidth
            value={newStatus}
            onChange={(e) => setNewStatus(e.target.value)}
            style={{ marginBottom: '16px' }}
          >
            <MenuItem value="client_interested">לקוח בעניין</MenuItem>
            <MenuItem value="in_recruitment_process">בתהליך גיוס</MenuItem>
            <MenuItem value="hired">נשכר!</MenuItem>
            <MenuItem value="rejected_by_client">לקוח דחה</MenuItem>
          </Select>

          <TextField
            fullWidth
            multiline
            rows={3}
            label="הערות"
            value={statusNotes}
            onChange={(e) => setStatusNotes(e.target.value)}
            placeholder="הוסף הערות לעדכון זה..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStatusDialogOpen(false)}>ביטול</Button>
          <Button variant="contained" onClick={handleStatusChange}>
            אישור
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
}
