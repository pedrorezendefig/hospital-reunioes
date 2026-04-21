-- =====================================================
-- Seed: Usuário Admin Inicial
-- Email: admin@hospital.com / Senha: Admin@123!
-- =====================================================

-- Cria usuário na tabela auth.users do Supabase
INSERT INTO auth.users (
  id,
  instance_id,
  role,
  aud,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at,
  confirmation_token,
  recovery_token,
  email_change_token_new,
  email_change
) VALUES (
  gen_random_uuid(),
  '00000000-0000-0000-0000-000000000000',
  'authenticated',
  'authenticated',
  'admin@hospital.com',
  crypt('Admin@123!', gen_salt('bf')),
  now(),
  '{"provider":"email","providers":["email"]}',
  '{"nome":"Administrador","cargo":"Gerência"}',
  now(),
  now(),
  '',
  '',
  '',
  ''
);

-- Cria identidade vinculada ao usuário
INSERT INTO auth.identities (
  id,
  user_id,
  provider_id,
  identity_data,
  provider,
  last_sign_in_at,
  created_at,
  updated_at
)
SELECT
  gen_random_uuid(),
  id,
  email,
  jsonb_build_object('sub', id::text, 'email', email),
  'email',
  now(),
  now(),
  now()
FROM auth.users
WHERE email = 'admin@hospital.com';

-- =====================================================
-- Seed: Diretor Pedro (Real Email)
-- Email: pmrdef@gmail.com / Senha: Admin@123!
-- =====================================================

INSERT INTO auth.users (
  id,
  instance_id,
  role,
  aud,
  email,
  encrypted_password,
  email_confirmed_at,
  raw_app_meta_data,
  raw_user_meta_data,
  created_at,
  updated_at,
  confirmation_token,
  recovery_token,
  email_change_token_new,
  email_change
) VALUES (
  gen_random_uuid(),
  '00000000-0000-0000-0000-000000000000',
  'authenticated',
  'authenticated',
  'pmrdef@gmail.com',
  crypt('Admin@123!', gen_salt('bf')),
  now(),
  '{"provider":"email","providers":["email"]}',
  '{"nome":"Pedro Rezende","cargo":"Diretor"}',
  now(),
  now(),
  '',
  '',
  '',
  ''
);

INSERT INTO auth.identities (
  id,
  user_id,
  provider_id,
  identity_data,
  provider,
  last_sign_in_at,
  created_at,
  updated_at
)
SELECT
  gen_random_uuid(),
  id,
  email,
  jsonb_build_object('sub', id::text, 'email', email),
  'email',
  now(),
  now(),
  now()
FROM auth.users
WHERE email = 'pmrdef@gmail.com';
