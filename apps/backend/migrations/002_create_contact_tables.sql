-- Create contact tables for employees, clients, and potential clients
-- Categorized by relationship type: employees, clients, or potential clients

-- Employees (עובדים) - persons linked to company organization
CREATE TABLE IF NOT EXISTS public.employees (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pipedrive_person_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(20),
    org_id INTEGER,
    contact_type VARCHAR(50) DEFAULT 'employee',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    pipedrive_last_synced_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_employees_pipedrive_id ON public.employees (pipedrive_person_id);
CREATE INDEX IF NOT EXISTS idx_employees_email ON public.employees (email);
CREATE INDEX IF NOT EXISTS idx_employees_created ON public.employees (created_at);

-- Clients (לקוחות) - persons linked to won/completed deals
CREATE TABLE IF NOT EXISTS public.clients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pipedrive_person_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(20),
    org_id INTEGER,
    contact_type VARCHAR(50) DEFAULT 'client',
    revenue_potential DECIMAL(12, 2),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    pipedrive_last_synced_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_clients_pipedrive_id ON public.clients (pipedrive_person_id);
CREATE INDEX IF NOT EXISTS idx_clients_email ON public.clients (email);
CREATE INDEX IF NOT EXISTS idx_clients_created ON public.clients (created_at);

-- Potential Clients (לקוחות פוטנציאלים) - all other persons
CREATE TABLE IF NOT EXISTS public.potential_clients (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pipedrive_person_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(20),
    org_id INTEGER,
    contact_type VARCHAR(50) DEFAULT 'potential_client',
    interest_level VARCHAR(50),
    source VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    pipedrive_last_synced_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_potential_clients_pipedrive_id ON public.potential_clients (pipedrive_person_id);
CREATE INDEX IF NOT EXISTS idx_potential_clients_email ON public.potential_clients (email);
CREATE INDEX IF NOT EXISTS idx_potential_clients_created ON public.potential_clients (created_at);

-- Enable RLS
ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.potential_clients ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for authenticated access
CREATE POLICY "Enable read access for authenticated users on employees" ON public.employees
    FOR SELECT USING (true);

CREATE POLICY "Enable read access for authenticated users on clients" ON public.clients
    FOR SELECT USING (true);

CREATE POLICY "Enable read access for authenticated users on potential_clients" ON public.potential_clients
    FOR SELECT USING (true);
