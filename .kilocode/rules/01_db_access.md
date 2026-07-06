@rule codeНИКОГДА не используй SQLAlchemy, ORM или raw SQL (psycopg2) для бизнес-логики. Всё работает через HTTP-клиент к PostgREST. В RPC-функциях PostgREST ВСЕГДА используй:

LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
current_setting('request.jwt.claim.app_role', true) (НЕ role)
FOR UPDATE для предотвращения race conditions.
