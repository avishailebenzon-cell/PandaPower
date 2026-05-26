-- Migration: Add RPC function for overriding job assignments
-- Date: 2026-05-25
-- Description: Creates a stored procedure to handle job assignment overrides, bypassing schema cache issues

-- Create the function to override job assignment
CREATE OR REPLACE FUNCTION override_job_assignment(
    p_job_id UUID,
    p_new_agent_code TEXT,
    p_updated_at TIMESTAMPTZ DEFAULT NOW()
) RETURNS TABLE (
    success BOOLEAN,
    message TEXT,
    old_agent_code TEXT,
    new_agent_code TEXT
) AS $$
DECLARE
    v_old_agent_code TEXT;
BEGIN
    -- Get the current agent code before updating
    SELECT assigned_agent_code INTO v_old_agent_code
    FROM jobs
    WHERE id = p_job_id;

    -- Check if job exists
    IF v_old_agent_code IS NULL AND NOT EXISTS (SELECT 1 FROM jobs WHERE id = p_job_id) THEN
        RETURN QUERY SELECT false, 'Job not found'::TEXT, NULL::TEXT, p_new_agent_code;
        RETURN;
    END IF;

    -- Update the job assignment
    UPDATE jobs
    SET assigned_agent_code = p_new_agent_code,
        updated_at = p_updated_at
    WHERE id = p_job_id;

    -- Return success
    RETURN QUERY SELECT true, 'Job assignment updated successfully'::TEXT, v_old_agent_code, p_new_agent_code;
END;
$$ LANGUAGE plpgsql;

-- Add comment for documentation
COMMENT ON FUNCTION override_job_assignment(UUID, TEXT, TIMESTAMPTZ) IS
'Updates job assignment to a new agent. Bypasses schema cache issues by using stored procedure.
Returns: success (boolean), message (text), old_agent_code (text), new_agent_code (text)';
