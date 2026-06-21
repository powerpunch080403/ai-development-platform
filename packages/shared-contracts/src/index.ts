export type HealthStatus = {
  status: "ok";
  service: string;
};

export type AuthUser = {
  id: string;
  display_name: string;
  account_id: string | null;
  account_link_status: string;
};

export type AuthDevice = {
  id: string;
  display_name: string;
  device_type: string;
  created_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
};

export type AuthSession = {
  id: string;
  device_id: string;
  created_at: string;
  last_seen_at: string;
  idle_expires_at: string;
  absolute_expires_at: string;
  revoked_at: string | null;
};

export type AuthState = {
  user: AuthUser;
  device: AuthDevice;
  session: AuthSession;
};
