/**
 * Pipedrive Data Display API Client
 * Endpoints for fetching synced Pipedrive data: employees, clients, organizations, jobs
 */

async function handleApiResponse<T>(response: Response, context: string): Promise<T> {
  if (!response.ok) {
    const contentType = response.headers.get('content-type');
    let errorMessage = `${context}: ${response.statusText}`;

    try {
      if (contentType?.includes('application/json')) {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.message || errorMessage;
      } else if (contentType?.includes('text/html')) {
        // Server returned HTML error page - likely auth issue or endpoint not found
        errorMessage = `${context}: Server error (${response.status}). Check backend connection and API endpoints.`;
      } else {
        const text = await response.text();
        errorMessage = text || errorMessage;
      }
    } catch (e) {
      // If we can't parse the error, just use the status
      errorMessage = `${context}: HTTP ${response.status}`;
    }

    throw new Error(errorMessage);
  }

  const contentType = response.headers.get('content-type');
  if (!contentType?.includes('application/json')) {
    throw new Error(`${context}: Response is not JSON (received ${contentType || 'unknown'})`);
  }

  return response.json();
}

export interface EmployeeResponse {
  id: string;
  name: string;
  full_name?: string;
  email?: string;
  phone?: string;
  title?: string;
  department?: string;
  professional_domain?: string;
  security_clearance_level?: string;
  organization_id?: string;
  pipedrive_id?: string;
  pipedrive_person_id?: number;
  contact_status?: string;
  sync_status: string;
  last_synced?: string;
  contact_type: string;
}

export interface ClientResponse {
  id: string;
  name?: string;
  full_name?: string;
  company_name?: string;
  contact_person?: string;
  email?: string;
  phone?: string;
  status?: string;
  professional_domain?: string;
  security_clearance_level?: string;
  organization_id?: string;
  revenue_potential?: number;
  pipedrive_id?: string;
  pipedrive_person_id?: number;
  contact_status?: string;
  sync_status: string;
  last_synced?: string;
  contact_type: string;
}

export interface PotentialClientResponse {
  id: string;
  name?: string;
  full_name?: string;
  company_name?: string;
  contact_person?: string;
  email?: string;
  phone?: string;
  interest_level?: string;
  source?: string;
  professional_domain?: string;
  security_clearance_level?: string;
  organization_id?: string;
  pipedrive_id?: string;
  pipedrive_person_id?: number;
  contact_status?: string;
  sync_status: string;
  last_synced?: string;
  contact_type: string;
}

export interface OrganizationResponse {
  id: string;
  name: string;
  industry?: string;
  size?: string;
  location?: string;
  employee_count?: number;
  contacts_count?: number;
  pipedrive_id?: string;
  pipedrive_org_id?: number;  // Pipedrive organization ID from sync
  sync_status: string;
  last_synced?: string;
  created_at?: string;
}

export interface JobResponse {
  id: string;
  title: string;
  job_title?: string;
  company: string;
  org_id?: number;
  location?: string;
  job_location?: string;
  description?: string;
  job_description?: string;
  qualifications?: string;
  job_qualifications?: string;
  security_clearance?: string;
  job_security_clearance?: string;
  deadline?: string;
  priority?: number;
  priority_label?: string;
  classification_level?: string;
  department?: string;
  status: string;
  posted_date?: string;
  candidates_count?: number;
  pipedrive_id?: string;
  pipedrive_deal_id?: number;  // 4-digit job code from Pipedrive
  sync_status: string;
  last_synced?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  count: number;
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  last_sync?: string;
}

/**
 * Fetch employees from Pipedrive
 */
export async function fetchEmployees(
  page: number = 1,
  limit: number = 50,
  search?: string,
  sortBy: string = 'name',
  sortOrder: 'asc' | 'desc' = 'asc'
): Promise<PaginatedResponse<EmployeeResponse>> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  if (search) {
    params.append('search', search);
  }

  const response = await fetch(`/admin/pipedrive/data/employees?${params}`);
  return handleApiResponse<PaginatedResponse<EmployeeResponse>>(response, 'Failed to fetch employees');
}

/**
 * Fetch clients from Pipedrive
 */
export async function fetchClients(
  page: number = 1,
  limit: number = 50,
  search?: string,
  status?: string,
  sortBy: string = 'name',
  sortOrder: 'asc' | 'desc' = 'asc'
): Promise<PaginatedResponse<ClientResponse>> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  if (search) {
    params.append('search', search);
  }
  if (status) {
    params.append('status', status);
  }

  const response = await fetch(`/admin/pipedrive/data/clients?${params}`);
  return handleApiResponse<PaginatedResponse<ClientResponse>>(response, 'Failed to fetch clients');
}

/**
 * Fetch potential clients from Pipedrive
 */
export async function fetchPotentialClients(
  page: number = 1,
  limit: number = 50,
  search?: string,
  interestLevel?: string,
  sortBy: string = 'name',
  sortOrder: 'asc' | 'desc' = 'asc'
): Promise<PaginatedResponse<PotentialClientResponse>> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  if (search) {
    params.append('search', search);
  }
  if (interestLevel) {
    params.append('interest_level', interestLevel);
  }

  const response = await fetch(`/admin/pipedrive/data/potential-clients?${params}`);
  return handleApiResponse<PaginatedResponse<PotentialClientResponse>>(response, 'Failed to fetch potential clients');
}

/**
 * Fetch organizations from Pipedrive
 */
export async function fetchOrganizations(
  page: number = 1,
  limit: number = 50,
  search?: string,
  industry?: string,
  sortBy: string = 'name',
  sortOrder: 'asc' | 'desc' = 'asc'
): Promise<PaginatedResponse<OrganizationResponse>> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  if (search) {
    params.append('search', search);
  }
  if (industry) {
    params.append('industry', industry);
  }

  const response = await fetch(`/admin/pipedrive/data/organizations?${params}`);
  return handleApiResponse<PaginatedResponse<OrganizationResponse>>(response, 'Failed to fetch organizations');
}

/**
 * Fetch jobs from Pipedrive
 */
export async function fetchJobs(
  page: number = 1,
  limit: number = 50,
  search?: string,
  status?: string,
  sortBy: string = 'title',
  sortOrder: 'asc' | 'desc' = 'asc'
): Promise<PaginatedResponse<JobResponse>> {
  const params = new URLSearchParams({
    page: String(page),
    limit: String(limit),
    sort_by: sortBy,
    sort_order: sortOrder,
  });

  if (search) {
    params.append('search', search);
  }
  if (status) {
    params.append('status', status);
  }

  const response = await fetch(`/admin/pipedrive/data/jobs?${params}`);
  return handleApiResponse<PaginatedResponse<JobResponse>>(response, 'Failed to fetch jobs');
}
