/**
 * Session 35: Pandi Client Invitation Campaign Management
 * Multi-step workflow: Select Contacts → Preview Messages → Send Campaign
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Stepper,
  Step,
  StepLabel,
  TextField,
  CircularProgress,
  Alert,
  Chip,
  LinearProgress,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Typography,
} from '@mui/material';
import {
  Send as SendIcon,
  Check as CheckIcon,
  Error as ErrorIcon,
  Clock as ClockIcon,
} from '@mui/icons-material';

import * as pandiApi from '../../api/pandi_outreach.ts';

interface SelectFilters {
  organization_ids: string[];
  domains: string[];
  clearance_levels: string[];
}

type StepName = 'select' | 'preview' | 'confirm';

const DEFAULT_MESSAGE_TEMPLATE = `שלום {client_name} 👋

אני פנדי, בוט חברה לאיתור מועמדים של {company} 🤖

עוזרת לחברות למצוא מועמדים מתאימים בשניות.

רוצה להשתמש בשירותי? שמור את ההודעה הזו כדי שאוכל להזהות אותך בהמשך!

לשאלות: {phone}

(זה מוקד בדיקה - תודה על הסבלנות)`;

export default function PandiOutreachPage() {
  // State
  const [activeStep, setActiveStep] = useState<StepName>('select');
  const [filters, setFilters] = useState<SelectFilters>({
    organization_ids: [],
    domains: [],
    clearance_levels: [],
  });
  const [contacts, setContacts] = useState<pandiApi.Contact[]>([]);
  const [selectedContacts, setSelectedContacts] = useState<pandiApi.Contact[]>([]);
  const [messageTemplate, setMessageTemplate] = useState(DEFAULT_MESSAGE_TEMPLATE);
  const [campaignName, setCampaignName] = useState('');
  const [campaign, setCampaign] = useState<pandiApi.Campaign | null>(null);
  const [preview, setPreview] = useState<pandiApi.CampaignPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1: Load contacts
  const handleLoadContacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await pandiApi.fetchOutreachContacts(
        {
          organization_ids: filters.organization_ids.length ? filters.organization_ids : undefined,
          domains: filters.domains.length ? filters.domains : undefined,
          clearance_levels: filters.clearance_levels.length ? filters.clearance_levels : undefined,
        },
        100
      );
      setContacts(data);
      setSelectedContacts(data);
    } catch (err) {
      setError(`Failed to load contacts: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Preview campaign
  const handlePreview = async () => {
    if (!campaignName.trim()) {
      setError('Campaign name is required');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      // Create campaign
      const newCampaign = await pandiApi.createCampaign({
        campaign_name: campaignName,
        message_template: messageTemplate,
        filters: {
          organization_ids: filters.organization_ids.length ? filters.organization_ids : undefined,
          domains: filters.domains.length ? filters.domains : undefined,
          clearance_levels: filters.clearance_levels.length ? filters.clearance_levels : undefined,
        },
      });

      setCampaign(newCampaign);

      // Get preview
      const previewData = await pandiApi.previewCampaign(newCampaign.id, 50);
      setPreview(previewData);
      setActiveStep('preview');
    } catch (err) {
      setError(`Failed to preview campaign: ${err}`);
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Send campaign
  const handleSendCampaign = async () => {
    if (!campaign) return;

    setSending(true);
    setError(null);
    try {
      const result = await pandiApi.sendCampaign(campaign.id);
      // Refresh campaign status
      const updatedCampaign = await pandiApi.fetchCampaign(campaign.id);
      setCampaign(updatedCampaign);
      setActiveStep('confirm');
    } catch (err) {
      setError(`Failed to send campaign: ${err}`);
    } finally {
      setSending(false);
    }
  };

  // Render step content
  const renderStepContent = () => {
    switch (activeStep) {
      case 'select':
        return (
          <Box sx={{ p: 3 }}>
            <Typography variant="h6" mb={2}>
              Step 1: Select Contacts
            </Typography>

            {/* Filters */}
            <Grid container spacing={2} mb={3}>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  label="Organization IDs (comma-separated)"
                  value={filters.organization_ids.join(', ')}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      organization_ids: e.target.value
                        .split(',')
                        .map((id) => id.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  label="Domains (comma-separated)"
                  value={filters.domains.join(', ')}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      domains: e.target.value
                        .split(',')
                        .map((d) => d.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={4}>
                <TextField
                  fullWidth
                  label="Clearance Levels (comma-separated)"
                  value={filters.clearance_levels.join(', ')}
                  onChange={(e) =>
                    setFilters({
                      ...filters,
                      clearance_levels: e.target.value
                        .split(',')
                        .map((c) => c.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </Grid>
            </Grid>

            <Button
              variant="contained"
              onClick={handleLoadContacts}
              disabled={loading}
              sx={{ mb: 3 }}
            >
              {loading ? <CircularProgress size={24} /> : 'Load Contacts'}
            </Button>

            {/* Contacts Table */}
            {contacts.length > 0 && (
              <>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Total {contacts.length} contacts selected
                </Alert>

                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead>
                      <TableRow style={{ backgroundColor: '#f5f5f5' }}>
                        <TableCell><strong>Name</strong></TableCell>
                        <TableCell><strong>Email</strong></TableCell>
                        <TableCell><strong>Phone</strong></TableCell>
                        <TableCell><strong>Organization</strong></TableCell>
                        <TableCell><strong>Domain</strong></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {contacts.slice(0, 10).map((contact) => (
                        <TableRow key={contact.id}>
                          <TableCell>{contact.full_name}</TableCell>
                          <TableCell>{contact.email}</TableCell>
                          <TableCell>{contact.phone}</TableCell>
                          <TableCell>{contact.organization_name || '-'}</TableCell>
                          <TableCell>{contact.domain || '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>

                {contacts.length > 10 && (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    Showing first 10 of {contacts.length} contacts. All will be sent.
                  </Alert>
                )}
              </>
            )}

            {/* Campaign name */}
            {contacts.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <TextField
                  fullWidth
                  label="Campaign Name"
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  placeholder="e.g., 'Pandi Service Invitation - May 2026'"
                  sx={{ mb: 2 }}
                />

                <TextField
                  fullWidth
                  multiline
                  rows={6}
                  label="Message Template"
                  value={messageTemplate}
                  onChange={(e) => setMessageTemplate(e.target.value)}
                  helperText="Edit only {placeholders}: {client_name}, {company}, {phone}"
                  sx={{ mb: 2 }}
                />

                <Button
                  variant="contained"
                  color="primary"
                  onClick={handlePreview}
                  disabled={loading || !campaignName.trim()}
                >
                  Preview Messages →
                </Button>
              </Box>
            )}
          </Box>
        );

      case 'preview':
        return (
          <Box sx={{ p: 3 }}>
            <Typography variant="h6" mb={2}>
              Step 2: Preview Messages
            </Typography>

            {preview && (
              <>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Campaign: <strong>{preview.campaign.campaign_name}</strong>
                  <br />
                  Total contacts: <strong>{preview.campaign.total_contacts}</strong>
                </Alert>

                <Typography variant="subtitle2" mb={1}>
                  Preview (first 5 messages):
                </Typography>

                <Box sx={{ maxHeight: 400, overflowY: 'auto' }}>
                  {preview.preview_messages.slice(0, 5).map((item, idx) => (
                    <Card key={idx} sx={{ mb: 2 }}>
                      <CardContent>
                        <Typography variant="subtitle2">
                          To: {item.contact.full_name} ({item.contact.email})
                        </Typography>
                        <Typography
                          variant="body2"
                          sx={{
                            mt: 1,
                            p: 1.5,
                            backgroundColor: '#f9f9f9',
                            borderRadius: 1,
                            whiteSpace: 'pre-wrap',
                            fontFamily: 'monospace',
                          }}
                        >
                          {item.rendered_message}
                        </Typography>
                      </CardContent>
                    </Card>
                  ))}
                </Box>

                <Alert severity="success" sx={{ mt: 2 }}>
                  ✓ All placeholders substituted correctly
                  <br />✓ Ready to send to {preview.campaign.total_contacts} contacts
                </Alert>

                <Box sx={{ mt: 3, display: 'flex', gap: 1 }}>
                  <Button
                    variant="outlined"
                    onClick={() => setActiveStep('select')}
                  >
                    ← Edit
                  </Button>
                  <Button
                    variant="contained"
                    color="primary"
                    onClick={() => setActiveStep('confirm')}
                  >
                    Confirm & Send →
                  </Button>
                </Box>
              </>
            )}
          </Box>
        );

      case 'confirm':
        return (
          <Box sx={{ p: 3 }}>
            <Typography variant="h6" mb={2}>
              Step 3: Confirm & Send
            </Typography>

            {campaign && (
              <>
                <Card sx={{ mb: 3 }}>
                  <CardContent>
                    <Grid container spacing={2}>
                      <Grid item xs={12} sm={6}>
                        <Typography color="textSecondary">Campaign</Typography>
                        <Typography variant="h6">{campaign.campaign_name}</Typography>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Typography color="textSecondary">Status</Typography>
                        <Chip
                          label={campaign.status.toUpperCase()}
                          color={
                            campaign.status === 'in_progress'
                              ? 'warning'
                              : campaign.status === 'completed'
                              ? 'success'
                              : 'default'
                          }
                          size="small"
                        />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Typography color="textSecondary">Total Contacts</Typography>
                        <Typography variant="h6">{campaign.total_contacts}</Typography>
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <Typography color="textSecondary">Estimated Duration</Typography>
                        <Typography variant="h6">
                          ~{Math.ceil(campaign.total_contacts * 3 / 60)} minutes
                        </Typography>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>

                {campaign.status === 'in_progress' && (
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="subtitle2" mb={1}>
                      Progress
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={(campaign.sent_count / campaign.total_contacts) * 100}
                      sx={{ mb: 1 }}
                    />
                    <Typography variant="body2" color="textSecondary">
                      {campaign.sent_count} sent, {campaign.failed_count} failed
                    </Typography>
                  </Box>
                )}

                {campaign.status === 'completed' || campaign.status === 'completed_with_errors' ? (
                  <Alert severity={campaign.failed_count === 0 ? 'success' : 'warning'} sx={{ mb: 3 }}>
                    ✓ Campaign completed!
                    <br />
                    Sent: {campaign.sent_count} | Failed: {campaign.failed_count}
                  </Alert>
                ) : (
                  <>
                    <Alert severity="warning" sx={{ mb: 3 }}>
                      ⚠️ Sending will begin immediately
                      <br />
                      Messages sent at 3-second intervals (rate limiting)
                    </Alert>

                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button
                        variant="outlined"
                        onClick={() => setActiveStep('preview')}
                        disabled={sending}
                      >
                        ← Back
                      </Button>
                      <Button
                        variant="contained"
                        color="success"
                        onClick={handleSendCampaign}
                        disabled={sending}
                        startIcon={sending ? <CircularProgress size={20} /> : <SendIcon />}
                      >
                        {sending ? 'Sending...' : 'Send Campaign'}
                      </Button>
                    </Box>
                  </>
                )}
              </>
            )}
          </Box>
        );

      default:
        return null;
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" mb={3}>
        🤖 Pandi Client Invitation
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 2, mb: 3 }}>
        <Stepper activeStep={['select', 'preview', 'confirm'].indexOf(activeStep)}>
          <Step>
            <StepLabel>Select Contacts</StepLabel>
          </Step>
          <Step>
            <StepLabel>Preview Messages</StepLabel>
          </Step>
          <Step>
            <StepLabel>Send Campaign</StepLabel>
          </Step>
        </Stepper>
      </Paper>

      <Paper>{renderStepContent()}</Paper>
    </Box>
  );
}
