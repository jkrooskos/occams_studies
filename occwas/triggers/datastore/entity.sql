---
--- avrc_data/entity -> pirc/entity + pirc/state
---
--- Updates only entities that are not sub-objects,
--- all others are ignored
---

DROP FOREIGN TABLE IF EXISTS entity_ext;


CREATE FOREIGN TABLE entity_ext (
    id              SERIAL NOT NULL

  , name            VARCHAR NOT NULL
  , title           VARCHAR NOT NULL
  , description     TEXT

  , schema_id       INTEGER NOT NULL
  , state_id        INTEGER NOT NULL
  , collect_date    DATE NOT NULL
  , is_null         BOOLEAN NOT NULL

  , create_date     TIMESTAMP NOT NULL
  , create_user_id  INTEGER NOT NULL
  , modify_date     TIMESTAMP NOT NULL
  , modify_user_id  INTEGER NOT NULL
  , revision        INTEGER NOT NULL

  , old_db          VARCHAR NOT NULL
  , old_id          INTEGER NOT NULL
)
SERVER trigger_target
OPTIONS (table_name 'entity');


DROP FOREIGN TABLE IF EXISTS state_ext;


CREATE FOREIGN TABLE state_ext (
    id              SERIAL NOT NULL

  , name            VARCHAR NOT NULL
  , title           VARCHAR NOT NULL
  , description     TEXT

  , create_date     TIMESTAMP NOT NULL
  , create_user_id  INTEGER NOT NULL
  , modify_date     TIMESTAMP NOT NULL
  , modify_user_id  INTEGER NOT NULL
  , revision        INTEGER NOT NULL
)
SERVER trigger_target
OPTIONS (table_name 'entity');


--
-- Helper function to find the entity id in the new system using
-- the old system id number
--
CREATE OR REPLACE FUNCTION ext_entity_id(id INTEGER) RETURNS SETOF integer AS $$
  BEGIN
    RETURN QUERY
      -- Check if it's a sub-object first
      SELECT "entity_ext".id
      FROM "entity_ext"
      WHERE (old_db, old_id) = (  (SELECT current_database())
                                , COALESCE((SELECT "object"."entity_id"
                                           FROM "object"
                                           WHERE "object"."value" = $1)
                                          ,$1))
      ;
    END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION entity_mirror() RETURNS TRIGGER AS $$
  BEGIN
    CASE TG_OP
      WHEN 'INSERT' THEN

        IF NOT EXISTS(SELECT 1 FROM schema where id = NEW.schema_id AND is_inline) THEN

          INSERT INTO entity_ext (
              name
            , title
            , description
            , schema_id
            , collect_date
            , state_id
            , is_null
            , create_date
            , create_user_id
            , modify_date
            , modify_user_id
            , revision
            , old_db
            , old_id
          )
          VALUES (
              NEW.name
            , NEW.title
            , NEW.description
            , ext_schema_id(NEW.schema_id)
            , NEW.collect_date
            , (SELECT id FROM "state_ext" WHERE name = NEW.state::text)
            , FALSE
            , NEW.create_date
            , ext_user_id(NEW.create_user_id)
            , NEW.modify_date
            , ext_user_id(NEW.modify_user_id)
            , NEW.revision
            , (SELECT current_database())
            , NEW.id
            );

        END IF;

      WHEN 'DELETE' THEN
        DELETE FROM entity_ext
        WHERE (old_db, old_id) = (SELECT current_database(), OLD.id);
      WHEN 'UPDATE' THEN
        UPDATE entity_ext
        SET name = NEW.name
          , title = NEW.title
          , description = NEW.description
          , schema_id = ext_schema_id(NEW.schema_id)
          , collect_date = NEW.collect_date
          , state_id = (SELECT id FROM "state_ext" WHERE name = NEW.state::text)
          , is_null = FALSE
          , create_date = NEW.create_date
          , create_user_id = ext_user_id(NEW.create_user_id)
          , modify_date = NEW.modify_date
          , modify_user_id = ext_user_id(NEW.modify_user_id)
          , revision = NEW.revision
          , old_db = (SELECT current_database())
          , old_id = NEW.id
        WHERE (old_db, old_id) = (SELECT current_database(), OLD.id);

    END CASE;
    RETURN NULL;
  END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS entity_mirror ON entity;


CREATE TRIGGER entity_mirror AFTER INSERT OR UPDATE OR DELETE ON entity
  FOR EACH ROW EXECUTE PROCEDURE entity_mirror();