-- Execute este script no SQL Editor do projeto Supabase.
create table if not exists public.dias (
  dia date primary key,
  marcacoes text[] not null default '{}',
  envolvidos_na_briga text,
  observacao text not null default '',
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  constraint dias_marcacoes_check check (cardinality(marcacoes) > 0),
  constraint dias_envolvido_check check (envolvidos_na_briga is null or envolvidos_na_briga in ('Os dois', 'Eduardo', 'Jéssica'))
);

create table if not exists public.votos (
  dia date not null references public.dias(dia) on delete cascade,
  participante text not null,
  estrelas smallint not null,
  comentario text not null default '',
  criado_em timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  primary key (dia, participante),
  constraint votos_participante_check check (participante in ('eduardo', 'jessica')),
  constraint votos_estrelas_check check (estrelas between 1 and 5)
);

create or replace function public.atualizar_atualizado_em()
returns trigger
language plpgsql
as $$
begin
  new.atualizado_em = now();
  return new;
end;
$$;

drop trigger if exists dias_atualizado_em on public.dias;
create trigger dias_atualizado_em
before update on public.dias
for each row execute function public.atualizar_atualizado_em();

drop trigger if exists votos_atualizado_em on public.votos;
create trigger votos_atualizado_em
before update on public.votos
for each row execute function public.atualizar_atualizado_em();

-- A API da Vercel usa a service role key no servidor. O acesso público direto fica bloqueado.
alter table public.dias enable row level security;
alter table public.votos enable row level security;

grant usage on schema public to service_role;
grant select, insert, update, delete on public.dias to service_role;
grant select, insert, update, delete on public.votos to service_role;
