-- WARNING: This script will DELETE all data for the "truckerp" tenant
-- and DROP the platform_tenants table entirely.
-- This is a DESTRUCTIVE operation. Run at your own risk.

-- Step 1: Get the tenant_id for "truckerp"
DO $$
DECLARE
    truckerp_tenant_id INTEGER;
BEGIN
    SELECT id INTO truckerp_tenant_id FROM platform_tenants WHERE slug = 'truckerp';
    
    IF truckerp_tenant_id IS NULL THEN
        RAISE NOTICE 'Tenant "truckerp" not found. Nothing to delete.';
        RETURN;
    END IF;
    
    RAISE NOTICE 'Found truckerp tenant with id: %', truckerp_tenant_id;
    
    -- Step 2: Delete all related data (CASCADE should handle most, but being explicit)
    -- Delete platform_company_profiles
    DELETE FROM platform_company_profiles WHERE tenant_id = truckerp_tenant_id;
    RAISE NOTICE 'Deleted platform_company_profiles for truckerp';
    
    -- Delete platform_subscriptions
    DELETE FROM platform_subscriptions WHERE tenant_id = truckerp_tenant_id;
    RAISE NOTICE 'Deleted platform_subscriptions for truckerp';
    
    -- Delete platform_tenant_members (this will cascade to platform_users if needed)
    DELETE FROM platform_tenant_members WHERE tenant_id = truckerp_tenant_id;
    RAISE NOTICE 'Deleted platform_tenant_members for truckerp';
    
    -- Step 3: Delete the tenant itself
    DELETE FROM platform_tenants WHERE id = truckerp_tenant_id;
    RAISE NOTICE 'Deleted truckerp tenant from platform_tenants';
    
END $$;

-- Step 4: Drop foreign key constraints that reference platform_tenants
-- (Needed before we can drop the table)

-- Drop FK from platform_tenant_members
ALTER TABLE IF EXISTS platform_tenant_members 
    DROP CONSTRAINT IF EXISTS platform_tenant_members_tenant_id_fkey;

-- Drop FK from platform_subscriptions
ALTER TABLE IF EXISTS platform_subscriptions 
    DROP CONSTRAINT IF EXISTS platform_subscriptions_tenant_id_fkey;

-- Drop FK from platform_company_profiles
ALTER TABLE IF EXISTS platform_company_profiles 
    DROP CONSTRAINT IF EXISTS platform_company_profiles_tenant_id_fkey;

-- Step 5: Drop the platform_tenants table
DROP TABLE IF EXISTS platform_tenants CASCADE;

-- Done! The platform_tenants table has been dropped.
