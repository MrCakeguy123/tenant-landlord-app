-- ============================================
-- Supabase Schema for Announcements
-- ============================================
-- Run this SQL in your Supabase SQL Editor
-- ============================================

-- Announcements table for landlord notices
CREATE TABLE IF NOT EXISTS announcements (
    id SERIAL PRIMARY KEY,
    landlord_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_announcements_landlord_id ON announcements(landlord_id);
CREATE INDEX IF NOT EXISTS idx_announcements_active ON announcements(is_active);
CREATE INDEX IF NOT EXISTS idx_announcements_created_at ON announcements(created_at DESC);

-- RLS Policy
ALTER TABLE announcements ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on announcements" ON announcements
    FOR ALL USING (true) WITH CHECK (true);

-- ============================================
-- DONE! Announcements table is ready.
-- ============================================

