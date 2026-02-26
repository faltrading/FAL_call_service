/*
  # Add jitsi_room_id column to calls table
  
  Stores the Jitsi-specific room identifier separately from the user-facing room name.
  This allows users to set a friendly display name while keeping a unique Jitsi room ID.
  
  Also drops the UNIQUE constraint on room_name since display names don't need uniqueness.
*/

ALTER TABLE calls ADD COLUMN IF NOT EXISTS jitsi_room_id varchar(255) DEFAULT '';

-- Drop the unique constraint on room_name (display name)
ALTER TABLE calls DROP CONSTRAINT IF EXISTS calls_room_name_key;
DROP INDEX IF EXISTS calls_room_name_key;
