"""
A very, very barebones asyncpg-backed ORM.

Shouldn't be vulnerable to SQL injection provided that
__schemaname__, __tablename__, __primary_key__, and _columns are not set to
arbitrary user input.

And that the keys of `properties=` arguments isn't arbitrary either apparently.

That would be really, really bad.

One can use the defualt orm instance or instantiate your own for other dbs.

"""
import json
import asyncio
import asyncpg

from .psqlt import Column

class class_or_instancemethod(classmethod):
    """cursed cursed cursed cursed cursed cursed cursed cursed cursed cursed cursed"""
    def __get__(self, instance, type_):
        descr_get = super().__get__ if instance is None else self.__func__.__get__
        return descr_get(instance, type_)

#pylint: disable=not-an-iterable,too-many-statements,too-many-locals
class ORM:
    """Wrapper class for everything I guess..."""
    pool: asyncpg.pool.Pool
    def __init__(self):
        self.ready_event = asyncio.Event()
        class Model:
            """Tables subclass this."""
            __schemaname__ = "public"
            __tablename__ = None
            __primary_key__ = None
            __addn_sql__ = None

            # kwargs are just a way to put in fields
            def __init__(self, conn=None, **kwargs):
                self.conn = conn
                self.__dict__.update({k:None for k in self._columns.keys()})
                self.__dict__.update(kwargs)

            def __repr__(self):
                return self.__class__.__name__ + "(" + ", ".join(f"{key}={val!r}" for key, val in \
                        {key: getattr(self, key) for key in self._columns.keys() if getattr(self, key) is not None}.items()) + ")"

            async def until_ready(self):
                """Blocks the current task until the ORM is up and running."""
                await self.ready_event.wait()

            @classmethod
            async def create_all_tables(cls):
                """Creates all the tables in Postgres and populates all subclasses with necessary runtime information."""
                async with self.pool.acquire() as conn:
                    for scls in Model.__subclasses__():
                        columns = {}
                        for field_name, field_type in scls.__annotations__.items():
                            if isinstance(field_type, Column):
                                columns[field_name] = field_type.sql
                        scls._columns = columns
                        scls._orm = self
                        if scls.__primary_key__:
                            if not isinstance(scls.__primary_key__, tuple):
                                raise TypeError(f"Primary key fields should be tuples, did you forget a comma in {scls.__name__}?")

                        async with conn.transaction():
                            db_columns = await conn.fetch("SELECT column_name from information_schema.columns "
                                                          "WHERE table_schema = $1 AND table_name = $2",
                                                          scls.__schemaname__, scls.__tablename__)

                            if db_columns:
                                db_column_names = set(map(lambda r: r["column_name"], db_columns))
                                column_names = set(columns.keys())
                                if column_names - db_column_names:
                                    raise TypeError(f"columns {column_names - db_column_names} are missing from "
                                                    f"the {scls.__schemaname__}.{scls.__tablename__} table!")
                            else:

                                query_params = ", ".join(map(" ".join, zip(columns.keys(), columns.values())))
                                if scls.__addn_sql__:
                                    query_params += ", " + scls.__addn_sql__
                                if scls.__primary_key__:
                                    query_params += f", PRIMARY KEY({', '.join(k for k in scls.__primary_key__)})"
                                # "but making sql like this is bad, you say." Yes. Yes it is. It is assumed, however, that this code
                                # is never fed user inputs, in which case you probably just want a real ORM anyway.
                                query_str = f"CREATE TABLE IF NOT EXISTS {scls.__schemaname__}.{scls.__tablename__}({query_params})"
                                await conn.fetch(query_str)
                self.ready_event.set()

            @classmethod
            def from_record(cls, record: asyncpg.Record):
                """Converts an asyncpg.Record into a Model object."""
                if record is None:
                    return None
                ret = cls()
                for field in cls._columns.keys():
                    setattr(ret, field, record[field])
                return ret

            @classmethod
            async def _fetch(cls, args, _one=False, conn=None):
                try:
                    f = 'fetchrow' if _one else 'fetch'
                    if conn is None:
                        async with cls._orm.pool.acquire() as conn:
                            async with conn.transaction():
                                return await getattr(conn, f)(*args)
                    else:
                        async with conn.transaction():
                            return await getattr(conn, f)(*args)
                except asyncpg.PostgresError:
                    print("query", args[0], "failed!")
                    raise

            @classmethod
            async def fetch(cls, *args, _conn=None):
                """Equivalent to mapping Model.from_record onto the results of asyncpg.fetch."""
                return [cls.from_record(r) for r in await cls._fetch(args, conn=_conn)]

            @classmethod
            async def fetchrow(cls, *args, _conn=None):
                """Equivalent to Model.from_record(await asyncpg.fetch(...))"""
                return cls.from_record(await cls._fetch(args, _one=True, conn=_conn))

            async def insert(self, _conn=None, _upsert="", _fields=None):
                """Inserts the model into the database. Use _upsert to specify an ON CONFLICT or other clause."""
                fields = _fields or self._columns.keys()
                qs = f"INSERT INTO {self.__schemaname__}.{self.__tablename__}({','.join(fields)}) VALUES(" + ",".join(
                    f"${i}" for i in range(1, len(fields) + 1)) + ")" + (_upsert if _upsert else "")
                args = [qs] + [getattr(self, f) for f in fields]
                await self.fetch(*args, _conn=_conn)

            @classmethod
            async def select(cls, _conn=None, _extra_sql="", **properties):
                """Queries for Models matching the specified properties. Returns a list of matching results."""
                if not properties:
                    return await cls.fetch(f"SELECT * FROM {cls.__schemaname__}.{cls.__tablename__}")
                else:
                    fields = properties.keys()
                    qs = f"SELECT * FROM {cls.__schemaname__}.{cls.__tablename__} WHERE " + " AND ".join(
                        f"{f}=${i}" for i, f in enumerate(fields, 1)) + _extra_sql
                    return await cls.fetch(*([qs] + list(properties.values())), _conn=_conn)

            @classmethod
            async def get_by(cls, *args, **kwargs):
                """Lazy attempt at frcdozer "orm" compat"""
                return await cls.select(*args, **kwargs)

            @classmethod
            async def select_one(cls, _conn=None, **properties):
                """Queries for a single Model matching the specified properties. Similar to .one_or_none() in sqlalchemy."""
                if not properties:
                    raise ValueError("bruh which one do i pick")
                fields = properties.keys()
                qs = f"SELECT * FROM {cls.__schemaname__}.{cls.__tablename__} WHERE " + " AND ".join(f"{f}=${i}" for i, f in enumerate(fields, 1))
                return await cls.fetchrow(*([qs] + list(properties.values())), _conn=_conn)
            
            async def update_or_add(self, *args, **kwargs):
                """frcdozer orm compat"""
                return await self.upsert(*args, **kwargs)

            async def update(self, _keys=None, _conn=None, **properties):
                """Updates Models matching the specified properties in the database to the values of the Model object.
                Typically does not require property arguments.
                 """
                pkeys = self.__primary_key__ or tuple()
                if _keys is None:
                    fields = [k for k in self._columns.keys() if k not in pkeys]
                else:
                    fields = [k for k in self._columns.keys() if k in _keys and k not in pkeys]

                if not properties:
                    if not pkeys:
                        raise ValueError("properties must be passed to update() if there is no primary key!")
                    else:
                        properties = {k: getattr(self, k) for k in self.__primary_key__}
                qs = f"UPDATE {self.__schemaname__}.{self.__tablename__} SET ({','.join(fields)}) = (" + ",".join(
                    f"${i}" for i in range(1, len(fields) + 1)) + ") " \
                         "WHERE " + " AND ".join(f"{f} = ${i}" for i, f in enumerate(properties.keys(), len(fields) + 1))
                # print(qs)

                return await self.fetchrow(*([qs] + [getattr(self, f) for f in fields] + list(properties.values())), _conn=_conn)

            @class_or_instancemethod
            async def delete(self_or_cls, _conn=None, **properties):
                """Deletes the matching Model from the database."""
                if isinstance(self_or_cls, type):
                    # this is used for frcdozer compat
                    return await self_or_cls.delete_all(_conn=_conn, **properties)
                else:
                    self = self_or_cls

                pkeys = self.__primary_key__ or tuple()
                if not properties:
                    if not pkeys:
                        raise ValueError("properties must be passed to delete() if there is no primary key!")
                    else:
                        properties = {k: getattr(self, k) for k in self.__primary_key__}
                qs = f"DELETE FROM {self.__schemaname__}.{self.__tablename__} WHERE " + " AND ".join(
                    f"{f}=${i}" for i, f in enumerate(properties.keys(), 1))
                return await self.fetch(*([qs] + list(properties.values())), _conn=_conn)

            @classmethod
            async def delete_all(cls, _conn=None, **properties):
                """Deletes all matching Models from the database."""
                if not properties:
                    raise ValueError("delete_all() requires at least one keyword argument!")
                qs = f"DELETE FROM {cls.__schemaname__}.{cls.__tablename__} WHERE " + " AND ".join(
                    f"{f}=${i}" for i, f in enumerate(properties.keys(), 1))
                return await cls.fetch(*([qs] + list(properties.values())), _conn=_conn)

            def primary_key(self):
                """Returns the primary key tuple of the table."""
                if not self.__primary_key__:
                    return None
                return tuple(getattr(self, k) for k in self.__primary_key__)

            @classmethod
            def table_name(cls):
                """Regurns the fully qualified table name of the Model."""
                return f"{cls.__schemaname__}.{cls.__tablename__}"

            async def upsert(self, conn=None, retry=5):
                """This performs an upsert by doing a select then an insert/update, this can be subject to race conditions
                and should be avoided if possible."""

                exc = None
                for i in range(retry):
                    try:
                        if not self.__primary_key__:
                            # ig i could implement a checker?
                            raise TypeError("upsert() requires a primary key on the table")
                        if await self.select_one(**{k: getattr(self, k) for k in self.__primary_key__}, _conn=conn):
                            await self.update(_conn=conn)
                        else:
                            await self.insert(_conn=conn)
                        return
                    except asyncpg.UniqueViolationError as e:
                        exc = e
                        # oops!
                raise exc

        self.Model = Model
        self.acquire = None
        self.pool: asyncpg.pool.Pool

    async def join(self, tables, tnames, join_on, where=None, addn_sql="", params=None, use_dict=True):
        """Performs black magic to perform a join. I don't even remember how this works anymore.
        tables, tnames, and on are NOT injection safe!
        """
        if len(tables) != (len(join_on) + 1) or len(tables) != len(tnames):
            raise TypeError("tables not same length as join_on")

        qs_tables = ",'' AS \".\",".join(f'{t}.*' for t in tnames)
        qs_joins = ""
        for table, tname, on in zip(tables[1:], tnames[1:], join_on):
            qs_joins += f"INNER JOIN {table.table_name()} AS {tname} ON ({on}) "

        qs_where = ""
        if where:
            qs_where = f"WHERE {where}"
        if not params:
            params = tuple()
        qs = f"SELECT {qs_tables} FROM {tables[0].table_name()} AS {tnames[0]} {qs_joins} {qs_where} {addn_sql}"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(qs, *params)

        ret = []
        for row in rows:
            t_idx = 0
            obj_data = {}
            ret_row = {} if use_dict else []
            for column_name, value in row.items():
                if column_name == '.':
                    if use_dict:
                        ret_row[tnames[t_idx]] = tables[t_idx].from_record(obj_data)
                    else:
                        ret_row.append(tables[t_idx].from_record(obj_data))
                    t_idx += 1
                    obj_data = {}
                else:
                    obj_data[column_name] = value

            if use_dict:
                ret_row[tnames[t_idx]] = tables[t_idx].from_record(obj_data)
            else:
                ret_row.append(tables[t_idx].from_record(obj_data))

            if use_dict:
                ret.append(ret_row)
            else:
                ret.append(tuple(ret_row))
        return ret


    async def connect(self, **kwargs):
        """Connects to the database and creates the internal asyncpg pool."""
        async def connection_initer(conn):
            await conn.set_type_codec(
                'json',
                encoder=json.dumps,
                decoder=json.loads,
                schema='pg_catalog'
            )

        kwargs["init"] = connection_initer
        self.pool = await asyncpg.create_pool(**kwargs)
        self.acquire = self.pool.acquire


    async def close(self):
        """Shuts down the asyncpg pool."""
        await self.pool.close()

orm = ORM()
