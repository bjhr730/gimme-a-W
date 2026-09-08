-- Search has to find "Almiron" when the stored name is "Almirón", and "Sao Paulo"
-- for "São Paulo". Nobody types the accents these leagues are full of, so the
-- query layer compares unaccent() on both sides.
CREATE EXTENSION IF NOT EXISTS unaccent;
