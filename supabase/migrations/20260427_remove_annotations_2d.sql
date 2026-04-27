-- Remove legacy 2D manual-annotation state from plans.
alter table public.plans
  drop column if exists annotations_2d;
