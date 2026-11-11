CREATE FUNCTION app.accept_invite(p_token_hash text, p_name text, p_password_hash text)
RETURNS TABLE (out_user_id uuid, out_agency_id uuid, out_role text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE inv invites; uid uuid;
BEGIN
  -- FOR UPDATE locks the row. A concurrent second call blocks here; when
  -- the first commits, Postgres re-checks the WHERE, sees status is no
  -- longer 'pending', and returns no row.
  SELECT * INTO inv FROM invites i
   WHERE i.token_hash = p_token_hash AND i.status = 'pending' AND i.expires_at > now()
   FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'invite is invalid, expired or already used' USING ERRCODE = 'P0002';
  END IF;

  INSERT INTO users (email, name, password_hash)
  VALUES (inv.email, p_name, p_password_hash)
  ON CONFLICT (email) DO NOTHING;
  SELECT u.id INTO uid FROM users u WHERE u.email = inv.email;

  INSERT INTO agency_memberships (agency_id, user_id, role, client_id)
  VALUES (inv.agency_id, uid, inv.role, inv.client_id)
  ON CONFLICT ON CONSTRAINT agency_memberships_pkey DO UPDATE
    SET role = EXCLUDED.role, client_id = EXCLUDED.client_id, removed_at = NULL;

  UPDATE invites SET status = 'accepted', accepted_at = now(), accepted_user_id = uid
   WHERE id = inv.id;
  RETURN QUERY SELECT uid, inv.agency_id, inv.role;
END $$;
