/*
  # Call Service - Database Schema

  1. New Tables
    - `calls`
      - `id` (uuid, primary key) - Unique call identifier
      - `room_name` (varchar, unique) - Unique Jitsi room identifier
      - `created_by` (uuid) - User ID of the call creator (moderator)
      - `creator_username` (varchar) - Cached username of the creator
      - `is_active` (boolean) - Whether the call is currently active
      - `max_participants` (integer, nullable) - Optional participant limit
      - `ended_at` (timestamptz, nullable) - When the call was ended
      - `created_at` (timestamptz) - Creation timestamp
      - `updated_at` (timestamptz) - Last update timestamp

    - `call_participants`
      - `id` (uuid, primary key) - Unique participation record identifier
      - `call_id` (uuid, FK) - Reference to calls table
      - `user_id` (uuid) - User identifier from users microservice
      - `username` (varchar) - Cached username for display
      - `role` (varchar) - 'moderator' or 'participant'
      - `joined_at` (timestamptz) - When the user joined the call
      - `left_at` (timestamptz, nullable) - When the user left (null if still in call)
      - `kicked` (boolean) - Whether the user was kicked from the call

  2. Security
    - RLS enabled on all tables
    - Service role has full access (backend microservice uses service role key)

  3. Indexes
    - calls indexed by (is_active) for active call lookups
    - call_participants indexed by (call_id, user_id) for membership lookups
    - call_participants indexed by (user_id) for user call history
    - Partial unique index on (call_id, user_id) WHERE left_at IS NULL to prevent duplicate active participation

  4. Notes
    - The creator of a call is automatically a moderator
    - The global admin is always treated as moderator (enforced at application level)
    - Participants with left_at IS NULL are considered currently in the call
    - The kicked flag distinguishes voluntary leave from forced removal
    - Realtime publication enabled on calls table for broadcast events
*/

CREATE TABLE IF NOT EXISTS calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  room_name varchar(255) UNIQUE NOT NULL,
  created_by uuid NOT NULL,
  creator_username varchar(255) DEFAULT '',
  is_active boolean NOT NULL DEFAULT true,
  max_participants integer,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS call_participants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id uuid NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  user_id uuid NOT NULL,
  username varchar(255) DEFAULT '',
  role varchar(20) NOT NULL DEFAULT 'participant',
  joined_at timestamptz NOT NULL DEFAULT now(),
  left_at timestamptz,
  kicked boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_calls_active
  ON calls(is_active)
  WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_call_participants_call_user
  ON call_participants(call_id, user_id);

CREATE INDEX IF NOT EXISTS idx_call_participants_user
  ON call_participants(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_call_participants_active_unique
  ON call_participants(call_id, user_id)
  WHERE left_at IS NULL;

ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_participants ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access to calls"
  ON calls
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role full access to call_participants"
  ON call_participants
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER PUBLICATION supabase_realtime ADD TABLE calls;
