-- ============================================
-- Supabase Storage Setup for Maintenance Images
-- ============================================
-- Run this SQL in your Supabase SQL Editor AFTER running supabase_schema.sql
-- ============================================

-- Create a storage bucket for maintenance request images
INSERT INTO storage.buckets (id, name, public)
VALUES ('maintenance-images', 'maintenance-images', true)
ON CONFLICT (id) DO NOTHING;

-- Allow public read access to images (anyone can view)
CREATE POLICY "Public read access for maintenance images"
ON storage.objects FOR SELECT
USING (bucket_id = 'maintenance-images');

-- Allow authenticated uploads (service role can upload)
CREATE POLICY "Service role can upload maintenance images"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'maintenance-images');

-- Allow service role to delete images
CREATE POLICY "Service role can delete maintenance images"
ON storage.objects FOR DELETE
USING (bucket_id = 'maintenance-images');

-- ============================================
-- DONE! Storage bucket is ready.
-- ============================================
-- Images will be accessible at:
-- https://YOUR_PROJECT.supabase.co/storage/v1/object/public/maintenance-images/FILENAME
-- ============================================

