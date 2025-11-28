-- ============================================
-- Supabase Schema for Tenant-Landlord App
-- ============================================
-- Run this SQL in your Supabase SQL Editor:
-- https://supabase.com/dashboard/project/YOUR_PROJECT/sql
-- ============================================

-- Enable UUID extension (usually already enabled)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('tenant', 'landlord')),
    full_name TEXT,
    email TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster username lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- ============================================
-- LEASES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS leases (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    landlord_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    monthly_rent NUMERIC(10, 2) NOT NULL,
    due_day INTEGER NOT NULL DEFAULT 1 CHECK (due_day >= 1 AND due_day <= 31),
    start_date DATE,
    end_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_leases_tenant_id ON leases(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leases_landlord_id ON leases(landlord_id);
CREATE INDEX IF NOT EXISTS idx_leases_active ON leases(is_active);

-- ============================================
-- RENT PAYMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS rent_payments (
    id SERIAL PRIMARY KEY,
    lease_id INTEGER NOT NULL REFERENCES leases(id) ON DELETE CASCADE,
    amount NUMERIC(10, 2) NOT NULL,
    month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
    year INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'Paid',
    paid_at TIMESTAMPTZ DEFAULT NOW(),
    method TEXT,
    note TEXT
);

-- Indexes for rent queries
CREATE INDEX IF NOT EXISTS idx_rent_payments_lease_id ON rent_payments(lease_id);
CREATE INDEX IF NOT EXISTS idx_rent_payments_month_year ON rent_payments(month, year);

-- ============================================
-- MAINTENANCE REQUESTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS maintenance_requests (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Open' CHECK (status IN ('Open', 'In progress', 'Completed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    priority TEXT NOT NULL DEFAULT 'Normal' CHECK (priority IN ('Low', 'Normal', 'High', 'Emergency')),
    image_filename TEXT
);

-- Indexes for maintenance queries
CREATE INDEX IF NOT EXISTS idx_maintenance_requests_tenant_id ON maintenance_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_requests_status ON maintenance_requests(status);
CREATE INDEX IF NOT EXISTS idx_maintenance_requests_created_at ON maintenance_requests(created_at DESC);

-- ============================================
-- ROW LEVEL SECURITY (RLS) - Optional but recommended
-- ============================================
-- Enable RLS on all tables (you can customize policies later)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE leases ENABLE ROW LEVEL SECURITY;
ALTER TABLE rent_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_requests ENABLE ROW LEVEL SECURITY;

-- For now, allow all operations when using service role key
-- (These policies allow the service role to do everything)
CREATE POLICY "Service role full access on users" ON users
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on leases" ON leases
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on rent_payments" ON rent_payments
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access on maintenance_requests" ON maintenance_requests
    FOR ALL USING (true) WITH CHECK (true);

-- ============================================
-- DONE! Your tables are ready.
-- ============================================

